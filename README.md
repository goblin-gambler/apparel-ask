# 服装问数：Schema RAG 驱动的服装零售经营数据问答智能体

> 面向服装连锁零售场景的自然语言数据分析系统。业务人员用中文提出问题，系统完成 Schema 检索、指标口径对齐、SQL 生成、SQL 校验与修正、数仓执行，并通过 SSE 把分析过程和结果实时返回前端。
>
> 本文聚焦系统当前的技术实现，包括数仓建模、元数据知识库、LangGraph 工作流、混合检索、SQL 闭环、接口协议、前端实现、部署方式与验证结果。

---

## 1. 项目定位与设计目标

### 1.1 要解决的问题

服装连锁零售的分析需求集中在营收、商品、库存、会员、渠道和促销几个维度，但业务人员直接写 SQL 存在四个现实问题：

- 不熟悉 12 张表的表结构、字段含义和 Join 路径；
- 不理解 GMV、净销售额、连带率、售罄率、断码率等指标的准确口径；
- 大模型直接生成 SQL 时容易选错表、编造字段、漏掉订单状态过滤，或者把订单级金额和明细级金额混用；
- 服装特有的库存快照、退货事实表与订单表口径不同，模型很容易用订单状态“已退货”代替退货事实，或用当日库存代替月末库存。

本项目的核心思路不是“让大模型直接写 SQL”，而是先构建一个可检索的元数据知识库，把与问题相关的表、字段、指标和字段取值召回出来，再让模型在受约束的上下文中完成推理和 SQL 生成，最后通过数据库校验闭环保证 SQL 可执行。

### 1.2 设计原则

| 原则 | 落地方式 |
| --- | --- |
| 先检索，后生成 | 字段、指标、取值三路召回，避免把全量 Schema 塞进 Prompt |
| 结构化上下文 | 表、字段、指标、日期、数据库方言全部整理成稳定结构后再交给模型 |
| SQL 闭环 | 生成后先 `EXPLAIN` 校验，失败进入修正节点，修正后再次执行 |
| 过程可观测 | 每个节点通过 SSE 推送 `progress` 事件，前端实时展示执行步骤 |
| 口径可维护 | 指标定义、字段描述、别名和值域统一放在 `conf/meta_config.yaml` |

### 1.3 能力边界

当前系统支持单轮、只读、单条 SQL 的自然语言问数，覆盖单表查询、多表 Join、时间范围、维度分组、排序 TopN、占比和同环比类问题。暂不支持多轮上下文、图表生成、权限控制和多 SQL 联合分析。

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│                        React 前端                            │
│        聊天输入 / 执行步骤 / SQL 结果表格 / 新会话           │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /api/query (SSE)
┌──────────────────────────▼──────────────────────────────────┐
│                      FastAPI 后端                            │
│   QueryService → LangGraph 工作流 → SSE 事件流               │
└───────┬──────────────────┬──────────────────┬────────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
   Qdrant 向量库      Elasticsearch       MySQL
   ├ 字段向量          └ 字段取值全文索引   ├ meta：元数据
   └ 指标向量                              └ dw：分析数仓
        ▲                  ▲                  ▲
        └──────────────────┴──────────────────┘
                离线元数据知识库构建
```

系统由两条链路组成：

| 链路 | 输入 | 处理 | 输出 |
| --- | --- | --- | --- |
| 离线知识库构建 | `conf/meta_config.yaml` + 数仓真实结构 | 表字段入库、字段/指标向量化、字段取值全文索引 | Meta MySQL、Qdrant、Elasticsearch |
| 在线自然语言问数 | 用户中文问题 | 关键词抽取、三路召回、上下文合并过滤、SQL 生成校验执行 | SSE 进度事件 + 查询结果 |

### 2.1 技术栈

| 模块 | 技术 | 职责 |
| --- | --- | --- |
| 分析数仓 | MySQL 8.0 | 8 张维度表 + 4 张事实表 |
| 元数据库 | MySQL + SQLAlchemy | 表、字段、指标、字段指标关系 |
| 向量检索 | Qdrant | 字段和指标的语义召回 |
| 全文检索 | Elasticsearch 8.19 + IK | 字段真实取值的中文检索 |
| Embedding | TEI + `BAAI/bge-large-zh-v1.5` | 1024 维文本向量 |
| Agent 编排 | LangGraph | 12 节点工作流与条件分支 |
| 模型接入 | LangChain + DeepSeek | 关键词扩展、过滤、SQL 生成与修正 |
| 后端 | FastAPI | 查询接口、依赖注入、生命周期管理 |
| 流式协议 | SSE | 节点进度、结果和错误推送 |
| 前端 | React 19 + Vite 6 + TypeScript + Tailwind CSS | 聊天式问数界面与流程展示 |
| 日志 | loguru + ContextVar | request_id 链路追踪 |

---

## 3. 数据仓库设计

### 3.1 星型模型

数仓共 12 张表、87 个字段，采用星型模型：

| 表 | 类型 | 粒度 | 字段数 | 主要职责 |
| --- | --- | --- | --- | --- |
| `dim_region` | 维度 | 城市 | 5 | 省份、城市、城市等级、大区 |
| `dim_store` | 维度 | 门店 | 7 | 门店名称、所属区域、经营类型、开业日期、营业状态 |
| `dim_product` | 维度 | 款（SPU） | 10 | 款名、品类、产品线、季节、吊牌价、成本、上市日期 |
| `dim_sku` | 维度 | SKU（颜色×尺码） | 5 | 所属款、颜色、尺码、条码 |
| `dim_member` | 维度 | 会员 | 7 | 性别、年龄段、会员等级、注册日期、注册门店 |
| `dim_channel` | 维度 | 渠道 | 4 | 门店 POS、微信小程序、第三方电商、直播电商、导购私域 |
| `dim_promotion` | 维度 | 活动 | 8 | 满减、折扣、会员日、季末清仓、赠品 |
| `dim_date` | 维度 | 日期 | 9 | 年、季度、月、星期、是否周末 |
| `fact_order` | 事实 | 订单 | 12 | 门店、会员、日期、渠道、活动、原价、优惠、实收、件数、状态 |
| `fact_order_item` | 事实 | 订单明细（SKU） | 7 | 订单、SKU、件数、成交单价、明细金额、明细优惠 |
| `fact_return` | 事实 | 退货记录 | 8 | 原订单、SKU、退货日期、退货件数、退货金额、类型、原因 |
| `fact_inventory` | 事实 | 门店 SKU 月末快照 | 5 | 快照日期、门店、SKU、在库数量、可售数量 |

### 3.2 多粒度事实表

`fact_order` 一行一个订单，`fact_order_item` 一行一个 SKU，`fact_return` 一行一条退货记录，`fact_inventory` 一行一个“月末 × 门店 × SKU”快照。四张事实表承担不同的分析职责：

- **订单粒度**：GMV、订单量、客单价、折扣金额、折扣率、会员订单占比、会员复购率等；
- **明细粒度**：销售额、销量、件单价、连带率、新品销售占比、毛利率等；
- **退货粒度**：退货金额、退货率、净销售额，按退货日期统计；
- **库存粒度**：售罄率、断码率，按月末快照统计。

这个设计带来的关键约束有三个：

1. **订单表与明细表 Join 后，不能对订单级金额字段求和**。一个订单包含多条明细时，订单级金额会在 Join 结果中重复出现。因此订单维度的营收使用 `fact_order.actual_amount`，商品、品类等明细维度的销售额使用 `fact_order_item.item_amount`；
2. **退货表与明细表不能按 SKU 直接 Join**。同一个 SKU 会出现在很多订单明细里，退货金额会被放大。退货金额和销售金额必须分别聚合后再按款号相除；
3. **库存是快照而不是流水**。售罄率、断码率只取统计期末的月末快照，不能对全年 12 个快照求和。

### 3.3 业务语义建模

数仓直接使用服装连锁的业务口径，而不是通用零售字段：

| 维度 | 取值设计 |
| --- | --- |
| 品类 | 女装、男装、童装、鞋履、配饰 |
| 产品线 | 休闲、基础、通勤、运动、户外、度假、童趣 |
| 季节 | 2023 秋冬、2024 春夏、2024 秋冬 |
| 尺码 | XS、S、M、L、XL、XXL，鞋履 36–44，配饰均码 |
| 会员等级 | 普通会员、银卡会员、金卡会员、黑卡会员 |
| 门店类型 | 直营店、加盟店 |
| 渠道 | 门店 POS、微信小程序、第三方电商、直播电商、导购私域 |
| 促销活动 | 双11 大促、618 大促、季末清仓、会员日、满减、满额赠礼 |
| 退货原因 | 尺码不合适、不喜欢、质量问题、发错货 |
| 大区 | 华东、华南、华中、西南、华北 |

这些取值同时写入维度表、字段描述、字段别名和 ES 值域索引，保证用户说“均码”“金卡会员”“导购私域”“尺码不合适”时，系统能定位到正确的字段和值。

### 3.4 模拟数据规模

数据生成脚本为 `app/scripts/seed_apparel_dw.py`，固定随机种子 `20240101`，时间范围 2024-01-01 至 2024-12-31：

| 数据 | 规模 |
| --- | --- |
| 大区 / 城市 | 5 个大区，28 个城市 |
| 门店 | 50 家（直营店 2、加盟店 48） |
| 款（SPU） | 300 款（女装 120、男装 80、童装 50、鞋履 30、配饰 20） |
| SKU | 3,879（颜色 × 尺码） |
| 会员 | 60,000 人（普通 55%、银卡 28%、金卡 13%、黑卡 4%） |
| 渠道 | 5 个 |
| 促销活动 | 12 个 |
| 日期 | 366 天 |
| 订单 | 177,018 |
| 订单明细 | 309,414 |
| 退货记录 | 22,626 |
| 库存快照 | 876,504（12 个月末 × 门店 × SKU） |

生成逻辑包含门店热度差异、周末与月度波动（双11、12 月为峰值）、会员金字塔分布、商品季节折价、尺码偏好和退货概率，使查询结果具有业务含义，而不是纯随机噪声。

### 3.5 指标口径

`conf/meta_config.yaml` 定义了 21 个指标：

| 指标 | 口径 |
| --- | --- |
| GMV | 已完成订单的 `actual_amount` 合计 |
| 净销售额 | GMV − 退货金额 |
| 销售额 | 已完成订单的 `fact_order_item.item_amount` 合计，明细维度使用 |
| 订单量 | 已完成订单的 `order_id` 去重计数 |
| 客单价 | GMV / 订单量 |
| 销量 | 已完成订单的 `fact_order_item.quantity` 合计（件） |
| 件单价 | 销售额 / 销量 |
| 连带率 | 销量 / 订单量，即 UPT |
| 折扣金额 | 吊牌价金额 − 实收金额 |
| 折扣率 | 折扣金额 / 吊牌价金额 |
| 毛利率 | (GMV − 商品成本) / GMV |
| 退货金额 | `fact_return.return_amount` 合计，按 `return_date_id` |
| 退货率 | 退货金额 / 已完成订单明细金额 |
| 售罄率 | 期间销量 / (期间销量 + 期末可售库存) |
| 断码率 | 可售尺码数 < 2 的款×门店组合数 / 全部款×门店组合数 |
| 会员订单占比 | 会员订单数 / 全部已完成订单数 |
| 会员复购率 | 下单 ≥2 次的会员数 / 有下单的会员数 |
| 新品销售占比 | 新品销量 / 全部销量 |
| 单店日均营收 | GMV / 产生订单的门店数 / 统计天数 |
| 营业门店数 | 统计期内产生已完成订单的门店去重数 |
| 消费会员数 | 统计期内产生已完成订单的会员去重数 |

指标不仅包含名称，还包含描述、别名和依赖字段。依赖字段用于在召回阶段补齐“指标怎么算”所需的真实列，避免模型知道指标名却不知道用哪一列。服装业务中容易算错的售罄率、断码率、退货率，口径全部写进指标描述，例如断码率明确要求排除配饰等单尺码款，否则均码款恒为 100%。

---

## 4. 元数据知识库

元数据知识库是 Schema RAG 的数据基础，分布在三类存储中。

### 4.1 Meta MySQL：结构化元数据

| 表 | 行数 | 内容 |
| --- | --- | --- |
| `table_info` | 12 | 表名、表角色（dim/fact）、表描述 |
| `column_info` | 87 | 字段名、类型、角色、示例值、描述、别名、所属表 |
| `metric_info` | 21 | 指标名、描述、别名、依赖字段 |
| `column_metric` | 63 | 指标与字段的多对多依赖关系 |

字段 ID 统一使用 `表名.字段名` 的形式，例如 `fact_order.actual_amount`。这个 ID 同时贯穿 Meta MySQL、Qdrant payload 和 ES 文档，保证三路召回结果可以按同一主键合并。

### 4.2 Qdrant：字段与指标向量

| Collection | 向量数 | 内容 |
| --- | --- | --- |
| `column_info_collection` | 439 | 字段名、字段描述、字段别名 |
| `metric_info_collection` | 121 | 指标名、指标描述、指标别名 |

向量维度 1024，距离度量 Cosine。一个字段不会只生成一个向量点，而是把名称、描述和每个别名分别作为一个语义入口：

```text
fact_order.actual_amount
├── "actual_amount"        → 字段名向量
├── "实收金额，订单实际..." → 描述向量
├── "实收金额"              → 别名向量
├── "实付金额"              → 别名向量
└── "成交金额"              → 别名向量
```

这样用户说“成交额”“实收”“收入”时，都有机会命中同一个字段。指标采用相同的拆分策略。

检索时使用 `score_threshold=0.6`、`limit=20`，每个扩展关键词单独检索，再按字段 ID 或指标 ID 去重。

### 4.3 Elasticsearch：字段取值

低基数业务字段的真实取值写入 ES `value_index`：

- 索引字段：`id`、`value`、`column_id`；
- `value` 使用 `ik_max_word` 分词，适合中文地区、门店名、会员等级、品类、尺码等取值；
- 查询使用 `match`，`min_score=0.6`，`size=20`；
- 当前写入 512 条取值文档，覆盖 28 个允许同步的字段。

字段是否同步由 `meta_config.yaml` 中每个字段的 `sync: true/false` 控制。高基数、无枚举意义的字段（如订单号、SKU 条码、金额）不进入值域索引，避免索引膨胀。

### 4.4 知识库构建流程

构建入口：

```bash
uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

流程：

1. 读取 `meta_config.yaml`，解析表、字段、指标和同步开关；
2. 到数仓读取字段真实类型和少量示例值，写入 `table_info`、`column_info`；
3. 字段按名称、描述、别名拆成向量点，分批调用 Embedding 服务写入 Qdrant；
4. 对 `sync` 字段读取真实值全集，写入 ES `value_index`；
5. 指标及字段依赖写入 `metric_info`、`column_metric`，再向量化写入 Qdrant。

Embedding 按 20 条一批调用，Qdrant 按 10 条一批 upsert，ES 按 20 条一批 bulk，避免单次请求过大。

**构建是追加写，不是幂等重建**。修改配置或重建数仓后，必须先清空四类存储，再执行构建：

```bash
# Meta MySQL
DELETE FROM column_metric;
DELETE FROM column_info;
DELETE FROM metric_info;
DELETE FROM table_info;

# Qdrant
curl -X DELETE http://localhost:6333/collections/column_info_collection
curl -X DELETE http://localhost:6333/collections/metric_info_collection

# Elasticsearch
curl -X DELETE http://localhost:9200/value_index
```

### 4.5 为什么使用混合检索

| 信息类型 | 检索方式 | 原因 |
| --- | --- | --- |
| 字段 | Qdrant 向量 | 用户说“成交额”，字段名可能是 `actual_amount`，需要语义匹配 |
| 指标 | Qdrant 向量 | “平均每单多少钱”需要映射到“客单价” |
| 字段取值 | Elasticsearch 全文 | “华东”“金卡会员”“尺码不合适”是精确业务值，关键词命中更可靠 |

三类信息协同召回，比只做表级检索更接近真实分析流程：模型既知道“有哪些字段”，也知道“指标怎么算”，还知道“条件值怎么写”。

---

## 5. LangGraph 工作流

### 5.1 State 与 Context 分离

工作流使用两个结构：

- `DataAgentState`：节点之间传递的业务数据，包括问题、关键词、三路召回结果、表上下文、指标上下文、日期、数据库信息、SQL 和错误信息；
- `DataAgentContext`：本次执行复用的外部依赖，包括 MySQL 仓储、Qdrant 仓储、ES 仓储和 Embedding 客户端。

这样 State 只保留可序列化的业务数据，客户端和连接池不进入图状态，便于调试和扩展。

### 5.2 12 个节点

| 节点 | 输入 | 输出 | 职责 |
| --- | --- | --- | --- |
| `extract_keywords` | 用户问题 | `keywords` | Jieba TF-IDF + 词性过滤抽取关键词，并保留原问题兜底 |
| `recall_column` | 关键词 | `retrieved_column_infos` | LLM 扩展字段语义词 → Embedding → Qdrant 检索 → 按字段 ID 去重 |
| `recall_value` | 关键词 | `retrieved_value_infos` | LLM 扩展值域词 → ES 全文检索 → 按取值 ID 去重 |
| `recall_metric` | 关键词 | `retrieved_metric_infos` | LLM 扩展指标概念 → Embedding → Qdrant 检索 → 按指标 ID 去重 |
| `merge_retrieved_info` | 三路召回结果 | `table_infos`、`metric_infos` | 补齐指标依赖字段、字段取值、主外键，按表组织上下文 |
| `filter_table` | 表上下文 | 裁剪后的 `table_infos` | LLM 选择保留的表和字段，程序按选择结果裁剪 |
| `filter_metric` | 指标上下文 | 裁剪后的 `metric_infos` | LLM 选择当前问题需要的指标 |
| `add_extra_context` | 数仓连接 | `date_info`、`db_info` | 补充当前日期、星期、季度、数据库方言和版本 |
| `generate_sql` | 全部上下文 | `sql` | 按 Prompt 约束生成一条只读 SQL |
| `validate_sql` | `sql` | `error` | 使用 `EXPLAIN` 校验 SQL 是否可被数据库解析 |
| `correct_sql` | 原问题、SQL、错误、上下文 | 修正后的 `sql` | 结合完整上下文做最小必要修正 |
| `run_sql` | `sql` | SSE `result` | 执行 SQL，输出查询结果 |

### 5.3 图拓扑

```text
START
  │
extract_keywords
  ├──────────────┬──────────────┐
  ▼              ▼              ▼
recall_column  recall_value   recall_metric
  └──────────────┴──────────────┘
                 ▼
        merge_retrieved_info
          ├──────────────┐
          ▼              ▼
     filter_table   filter_metric
          └──────────────┘
                 ▼
        add_extra_context
                 ▼
           generate_sql
                 ▼
           validate_sql
          ┌──────┴──────┐
      error 为空      error 非空
          ▼             ▼
       run_sql      correct_sql
          │             │
          │             ▼
          │          run_sql
          └─────────────┘
                 ▼
                END
```

三路召回并行执行，表过滤和指标过滤并行执行；`validate_sql` 通过条件边决定直接执行还是进入修正节点。

### 5.4 节点可观测性

每个节点执行时通过 `runtime.stream_writer` 写出：

```json
{"type": "progress", "step": "召回字段信息", "status": "running"}
{"type": "progress", "step": "召回字段信息", "status": "success"}
```

节点失败时写出 `status: "error"` 并抛出异常，由 `QueryService` 统一包装成 SSE 错误事件。前端据此展示完整的执行步骤。

---

## 6. 检索与上下文组装

### 6.1 关键词抽取

`extract_keywords` 使用 Jieba 的 TF-IDF 关键词抽取，并通过词性白名单过滤噪声：

- 保留名词、地名、机构名、专有名词、动词、名动词、形容词、英文和固定短语；
- 过滤“的、帮我、一下”等无检索价值的词；
- 把原始问题本身加入关键词列表，防止分词错误导致语义丢失。

### 6.2 三路语义扩展

每个召回节点都会先用 LLM 把用户问法扩展成该路检索更适合的词：

| 节点 | 扩展目标 | 示例 |
| --- | --- | --- |
| 字段召回 | 字段语义 | “卖了多少件” → “销量”“quantity” |
| 取值召回 | 真实值表达 | “华东大区” → “华东” |
| 指标召回 | 指标概念 | “平均每单买几件” → “连带率”“UPT” |

扩展结果与原关键词合并去重后，再逐词检索。

### 6.3 召回结果合并

`merge_retrieved_info` 是上下文组装的核心节点，执行 7 个步骤：

1. 以 `column_id` 为键合并字段召回结果；
2. 遍历指标依赖字段，缺失的从 Meta MySQL 按 ID 补齐；
3. 把取值召回结果写入对应字段的 `examples`，帮助模型写出真实条件值；
4. 按 `table_id` 把字段归到各自表下；
5. 为每张候选表补齐主外键字段，保证 Join 路径完整；
6. 把字段实体转换成面向 Prompt 的 `TableInfoState`；
7. 把指标实体转换成 `MetricInfoState`，保留名称、描述、别名和依赖字段。

主外键通常不会出现在用户问题里，单靠向量召回容易漏掉，因此在合并阶段统一兜底补齐。

### 6.4 两阶段过滤

召回阶段追求“不漏”，过滤阶段追求“不噪”：

- `filter_table`：把候选表结构转成 YAML 交给 LLM，模型只返回“保留哪些表、每张表保留哪些字段”的 JSON；
- `filter_metric`：模型只返回需要保留的指标名称；
- 程序根据模型的选择结果从原始结构中裁剪，**不让模型重写复杂结构**，避免 JSON 结构漂移或字段丢失。

### 6.5 额外上下文

`add_extra_context` 补充两类模型必须知道、但不来自召回的信息：

- 当前日期、星期、季度：支持“今天”“本月”“本季度”“最近 30 天”等相对时间；
- 数据库方言和版本：影响日期函数、`LIMIT` 语法和函数名。

---

## 7. SQL 生成与执行闭环

### 7.1 Prompt 约束

`prompts/generate_sql.prompt` 把生成约束写成 16 条硬规则，其中与服装数仓直接相关的是：

| 规则 | 约束 | 对应的业务陷阱 |
| --- | --- | --- |
| 7 | 明细维度统计金额必须使用明细级金额 | 订单 Join 明细后订单金额被放大 |
| 8 | 默认只统计已完成订单 | 已退货、已取消订单混入营收 |
| 9 | 退货必须使用 `fact_return`，按 `return_date_id` | 用订单状态“已退货”代替退货事实 |
| 10 | 售罄率、断码率必须使用 `fact_inventory` 月末快照 | 把库存当流水求和，或取错月份 |
| 11 | 比率类指标乘以 100 后保留两位小数 | 同一个问题有时返回 0.14、有时返回 27.54 |
| 12 | 退货金额与销售金额必须分别聚合后再相除 | 按 SKU 直接 Join 导致退货金额被放大 |
| 13 | 断码率排除单尺码款 | 配饰均码款恒为 100% 断码 |
| 14 | 订单明细按时间过滤必须经过 `fact_order` | 明细表没有日期列，模型编造 `order_date_id` |
| 15 | `date_id` 是 yyyyMMdd 整数，不能与日期字符串比较 | `date_id >= '2024-01-01'` 被截断成 2024，结果为空 |
| 16 | 只输出纯 SQL | 输出 Markdown 代码块或解释性文字导致执行失败 |

这些规则分别对应实际踩过的错误类型：编造字段、口径偏离、扇出重复计数、未过滤退货订单、库存快照误用、日期格式错配、百分比单位不一致和输出格式不稳定。

规则之外还有一道程序兜底：`generate_sql` 节点在调用模型前会按指标依赖字段补齐表上下文。过滤节点可能只保留问题字面提到的字段，把指标口径依赖的列裁掉（例如按渠道问折扣率时丢掉 `dim_product.list_price`），此时会按字段 ID 从 Meta MySQL 查回并写回状态，校正节点也能复用同一份上下文。

### 7.2 校验与修正

`validate_sql` 调用数仓仓储的 `validate()`，内部执行 `EXPLAIN <sql>`。校验只关心数据库能否解析这条 SQL，不执行真实查询。

- 校验通过：`error = None`，条件边进入 `run_sql`；
- 校验失败：错误信息写入 `state["error"]`，条件边进入 `correct_sql`；
- 修正节点拿到原问题、原 SQL、数据库错误和完整表/指标上下文，做最小必要修正；
- 修正后的 SQL 直接进入 `run_sql`，不再二次校验。

### 7.3 扇出重复计数问题

这是多粒度事实表最容易出错的地方。假设一个订单有 3 条明细：

```text
fact_order.actual_amount = 30 元
fact_order_item.item_amount = 10 + 10 + 10 元
```

如果按品类统计时写成：

```sql
SELECT p.category, SUM(o.actual_amount)
FROM fact_order o
JOIN fact_order_item i ON o.order_id = i.order_id
JOIN dim_sku s ON i.sku_id = s.sku_id
JOIN dim_product p ON s.product_id = p.product_id
GROUP BY p.category;
```

订单的 30 元会在 Join 后重复 3 次，结果被放大。正确写法是使用明细金额：

```sql
SELECT p.category, SUM(i.item_amount)
FROM fact_order o
JOIN fact_order_item i ON o.order_id = i.order_id
JOIN dim_sku s ON i.sku_id = s.sku_id
JOIN dim_product p ON s.product_id = p.product_id
WHERE o.order_status = '已完成'
GROUP BY p.category;
```

退货场景的扇出更隐蔽：退货表只有 `order_id + sku_id`，如果直接按 `sku_id` 关联订单明细，同一个 SKU 在所有订单里的行数都会乘到退货金额上，退货率会算出 100% 以上。正确做法是分子分母分别聚合：

```sql
SELECT r.product_id,
       ROUND(r.return_amount / s.sale_amount * 100, 2) AS 退货率
FROM (
    SELECT sk.product_id, SUM(fr.return_amount) AS return_amount
    FROM fact_return fr
    JOIN dim_sku sk ON fr.sku_id = sk.sku_id
    WHERE fr.return_date_id BETWEEN 20240101 AND 20241231
    GROUP BY sk.product_id
) r
JOIN (
    SELECT sk.product_id, SUM(fi.item_amount) AS sale_amount
    FROM fact_order_item fi
    JOIN fact_order fo ON fi.order_id = fo.order_id
    JOIN dim_sku sk ON fi.sku_id = sk.sku_id
    WHERE fo.order_status = '已完成'
    GROUP BY sk.product_id
) s ON r.product_id = s.product_id;
```

系统通过三层机制控制这个问题：指标层拆分“GMV”和“销售额”、Prompt 显式约束、字段描述和别名中说明两个金额字段的适用粒度。

### 7.4 结果序列化

MySQL 返回的 `date`、`datetime`、`Decimal` 不能直接被 JSON 序列化。数仓仓储在返回结果前统一调用 `_to_json_value` 转换，保证 SSE 的 `result` 事件可以稳定输出。

---

## 8. API 与流式协议

### 8.1 查询接口

```http
POST /api/query
Content-Type: application/json

{"query": "2024 年各大区的 GMV 分别是多少？"}
```

响应类型为 `text/event-stream`。`QueryService` 创建初始 State 和 Context，消费 `graph.astream(..., stream_mode="custom")`，把每个 chunk 包装成 SSE 消息。

### 8.2 事件类型

| 事件 | 结构 | 用途 |
| --- | --- | --- |
| `progress` | `{"type":"progress","step":"生成SQL","status":"running"}` | 节点执行进度 |
| `result` | `{"type":"result","data":[...]}` | 最终查询结果 |
| `error` | `{"type":"error","message":"..."}` | 工作流异常 |

SSE 格式：

```text
data: {"type": "progress", "step": "抽取关键词", "status": "running"}

data: {"type": "progress", "step": "抽取关键词", "status": "success"}

...

data: {"type": "result", "data": [{"大区": "华东", "GMV": "64765242.75"}]}

```

流式响应一旦开始，HTTP 状态码不能再修改，因此工作流异常也被包装成 `error` 事件返回，而不是抛出 500。

### 8.3 前端流式解析

前端没有使用 `EventSource`，因为 `EventSource` 只支持 GET，而查询接口需要 POST JSON。实际实现使用 `fetch` + `ReadableStream`：

1. 读取 `response.body.getReader()`；
2. 用 `TextDecoder` 按 UTF-8 流式解码；
3. 以 `\n\n` 切分 SSE 消息；
4. 提取 `data:` 行并 `JSON.parse`；
5. 根据事件类型更新消息状态。

---

## 9. 前端实现

前端位于 `frontend/`，技术栈为 React 19、Vite 6、TypeScript 和 Tailwind CSS。

### 9.1 组件划分

| 组件 | 职责 |
| --- | --- |
| `App.tsx` | 会话状态、SSE 事件消费、消息列表和整体布局 |
| `Composer.tsx` | 输入框、发送、停止生成 |
| `EmptyState.tsx` | 空会话状态和 6 个示例问题 |
| `MessageBubble.tsx` | 用户/助手消息、错误展示、结果表格 |
| `StepRail.tsx` | LangGraph 节点执行步骤和时间线 |
| `ResultTable.tsx` | 查询结果表格渲染 |
| `lib/agentApi.ts` | SSE 请求与解析 |
| `lib/format.ts` | 结果摘要和格式化 |

空会话页展示数仓基础信息（12 张表、87 个字段、21 个指标、2024 全年），并提供 6 个服装业务示例问题，降低首次使用成本。

### 9.2 状态管理

每条助手消息包含：

```ts
type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "done" | "error";
  steps?: StepState[];
  result?: unknown;
  error?: string;
};
```

收到 `progress` 事件时，按 `step` 更新步骤状态，同一节点重复执行时覆盖旧状态；收到 `result` 时把消息标记为完成并保存结果；收到 `error` 时展示错误信息。请求通过 `AbortController` 支持用户主动停止。

### 9.3 接口代理

开发环境通过 Vite 的 `/api` 代理转发到后端 8000 端口，前端代码不需要写死后端地址。部署时可通过 `VITE_API_BASE_URL` 指向独立的后端域名。

---

## 10. 部署与配置

### 10.1 依赖服务

`docker/docker-compose.yaml` 启动 5 个服务：

| 服务 | 镜像 | 宿主端口 | 用途 |
| --- | --- | --- | --- |
| MySQL | `mysql:8.0` | 3307 → 3306 | 元数据库 + 分析数仓 |
| Elasticsearch | 基于 8.19.10 构建，安装 IK | 9200 | 字段取值全文索引 |
| Kibana | `kibana:8.19.10` | 5601 | ES 可视化 |
| Qdrant | `qdrant/qdrant:v1.16` | 6333 / 6334 | 字段和指标向量 |
| Embedding | `text-embeddings-inference:cpu-1.8` | 8081 → 80 | bge-large-zh-v1.5 推理 |

MySQL 使用命名卷 `mysql_data` 持久化，首次启动执行 `docker/mysql/*.sql` 建库建表并授权。宿主 3307 是为了避开本机已有 MySQL 服务。

`docker/embedding/bge-large-zh-v1.5` 模型文件约 1.3GB，未纳入 Git；首次运行前需从 Hugging Face 下载 `BAAI/bge-large-zh-v1.5` 到该目录。

### 10.2 配置文件

| 文件 | 内容 |
| --- | --- |
| `conf/app_config.yaml` | MySQL、Qdrant、ES、Embedding、LLM 连接配置 |
| `conf/meta_config.yaml` | 表、字段、指标、别名、描述、值域同步开关 |
| `.env` | `LLM_API_KEY`、`DB_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`MYSQL_PASSWORD`（不入库） |
| `docker/docker-compose.yaml` | 依赖服务和端口 |
| `prompts/*.prompt` | 关键词扩展、过滤、SQL 生成与修正模板 |

数据库业务账号通过 `docker-compose.yaml` 的 `MYSQL_USER` / `MYSQL_PASSWORD` 初始化，并同步配置到 `app_config.yaml`。密码不写入仓库：`.env.example` 只保留占位符，首次部署时复制为 `.env` 并填入实际密码。`app_config.yaml` 通过 `${oc.env:DB_PASSWORD}` 读取，`docker-compose.yaml` 通过 `${MYSQL_PASSWORD}` 读取，因此启动 Compose 时需要显式指定 `--env-file .env`。

### 10.3 启动顺序

```bash
# 1. 启动依赖服务
docker compose -p shopkeeper --env-file .env -f docker/docker-compose.yaml up -d

# 2. 生成模拟数仓数据（首次或重建时执行）
uv run python -m app.scripts.seed_apparel_dw

# 3. 构建元数据知识库（首次或修改元数据后执行）
uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml

# 4. 启动后端
uv run fastapi dev main.py --port 8000

# 5. 启动前端
cd frontend
pnpm dev --host 127.0.0.1
```

前端默认运行在 `http://127.0.0.1:5173`，后端运行在 `http://127.0.0.1:8000`。

Compose 项目名固定为 `shopkeeper`，数据卷名因此是 `shopkeeper_mysql_data` 等；迁移或重启时不要省略 `-p shopkeeper`，否则会创建一套新的空卷。

---

## 11. 工程问题与处理方式

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| 扇出重复计数 | 订单表 Join 明细表后 `SUM(actual_amount)` 被放大 | 拆分 GMV 和销售额指标；Prompt 强制明细维度使用 `item_amount` |
| 退货率被放大 | 按款统计退货率超过 100% | 退货金额与销售金额分别聚合为子查询再相除；Prompt 增加专项规则 |
| 单尺码款断码 | 配饰等均码款断码率恒为 100% | 指标口径与 Prompt 同时要求排除单尺码款 |
| 库存快照误用 | 把 12 个月末快照求和当作库存 | 指标定义明确只取统计期末快照 |
| 百分比单位不一致 | 同一指标有时返回 0.14、有时返回 27.54 | Prompt 统一比率类指标乘 100 后保留两位小数 |
| 召回上下文过长 | 三路召回结果直接拼给模型，Prompt 过大且噪声多 | 召回后增加表过滤和指标过滤，模型只做选择，程序负责裁剪 |
| SQL 幻觉 | 编造字段、选错表、语法错误 | 只提供候选 Schema；`EXPLAIN` 校验；失败进入修正节点 |
| 中文值域匹配 | “华东”“金卡会员”用向量检索不稳定 | 低基数字段写入 ES，使用 IK 分词和 `match` 查询 |
| 知识库重复构建 | 追加写导致向量点和元数据重复 | 重建前清空 Meta MySQL、Qdrant、ES 四类存储 |
| 日期/金额序列化 | `date`、`Decimal` 无法直接 JSON 序列化 | 仓储层统一转换为字符串/数值 |
| 中文分词噪声 | “的、帮我、一下”进入检索关键词 | Jieba 词性白名单 + 原始问题兜底 |
| 数据不可复现 | 随机数据每次不同，无法对比实验结果 | 固定随机种子 `20240101`，脚本先 TRUNCATE 再插入 |
| 造数内存溢出 | 一次性生成全年订单导致 `MemoryError` | 改为按天流式生成并分批插入 |
| 并发日志追踪 | 多请求日志混在一起 | `ContextVar` 注入 request_id，loguru 统一输出 |

---

## 12. 验证结果

### 12.1 知识库与数据基线

| 检查项 | 结果 |
| --- | --- |
| Meta MySQL | 12 张表 / 87 个字段 / 21 个指标 / 63 条字段指标关系 |
| Qdrant `column_info_collection` | 439 个向量点 |
| Qdrant `metric_info_collection` | 123 个向量点 |
| Elasticsearch `value_index` | 512 条取值文档 |
| 数仓订单 | 177,018 |
| 数仓订单明细 | 309,414 |
| 数仓退货记录 | 22,626 |
| 库存快照 | 876,504 |
| 全量 GMV | 135,514,414.14 元 |
| 全量销售额（明细口径） | 136,905,954.01 元 |
| 退货金额 | 10,545,872.62 元 |

核心指标的直算结果：

| 指标 | 结果 |
| --- | --- |
| 客单价 | 814.44 元/单 |
| 连带率 | 1.92 件/单 |
| 折扣率（吊牌价口径） | 17.74% |
| 退货率 | 7.70% |
| 金卡会员复购率 | 70.44% |

### 12.2 查询验证

**2024 年各大区 GMV**

| 大区 | GMV（元） |
| --- | --- |
| 华东 | 64,765,242.75 |
| 华南 | 42,455,234.57 |
| 华中 | 15,056,736.44 |
| 西南 | 9,757,487.32 |
| 华北 | 3,479,713.06 |

**各渠道订单量与 GMV**

| 渠道 | 订单量 | GMV（元） |
| --- | --- | --- |
| 门店 POS | 91,393 | 74,356,251.96 |
| 微信小程序 | 30,283 | 24,576,935.66 |
| 第三方电商 | 19,738 | 16,141,268.95 |
| 直播电商 | 13,358 | 10,921,731.46 |
| 导购私域 | 11,618 | 9,518,226.11 |

**2024 年女装退货率 Top5（按款号）**

| 款号 | 退货率 |
| --- | --- |
| P105 | 11.88% |
| P120 | 11.78% |
| P118 | 11.42% |
| P092 | 11.20% |
| P112 | 10.85% |

**其他口径验证**

| 问题 | 结果 |
| --- | --- |
| 2024 年双11 大促期间各品类销售额 | 女装 367,766.36 / 男装 275,560.19 / 鞋履 170,599.37 / 童装 91,415.86 / 配饰 2,049.25 元 |
| 2024 年华东区连带率 Top5 门店 | 宁波鄞州万达 1.96、杭州钱江新城 1.95、宁波东部银泰 1.95、台州温岭银泰 1.94、台州椒江万达 1.94 |
| 2024 年第四季度断码率 Top5 款号 | P142 23.91%、P100 21.28%、P051 17.78%、P141 17.39%、P036 17.39% |
| 2024 年第四季度新品销售占比 | 10.64% |
| 2024 年线下门店 / 微信小程序折扣率 | 17.74% / 17.72% |
| 2024 年金卡会员复购率 | 70.44% |
| 2024 年 12 月羽绒服销售额 | 500,793.78 元 |

以上结果同时验证了区域/渠道/商品维度的 Join 路径、金额口径、订单状态过滤、退货事实表口径、库存快照口径、百分比单位和两位小数处理。

### 12.3 构建与前端验证

- 知识库构建耗时约 40 秒；
- 前端 `pnpm build` 通过，产物约 222 KB（gzip 70 KB）；
- 页面可正常展示执行步骤、SQL 结果表格和错误信息；
- 后端 `/docs` 可访问，`/api/query` 返回标准 SSE 事件流。

---

## 13. 局限与后续扩展

### 13.1 当前局限

- 只支持单轮问数，不保留会话上下文；
- 只生成一条只读 SQL，不支持多语句和写入；
- 结果是表格，没有图表和导出；
- 指标数量固定为 21 个，新增指标需要更新配置并重建知识库；
- 数仓结构变化后必须重新构建元数据知识库；
- 没有用户权限、数据脱敏和 SQL 审计；
- LLM 调用带来额外延迟和成本。

### 13.2 可扩展方向

| 方向 | 做法 |
| --- | --- |
| 多轮追问 | 在 State 中增加会话历史和指代消解节点 |
| 结果可视化 | 根据结果列类型自动选择折线图、柱状图或饼图 |
| SQL 安全 | 增加 SQL 审计、行数限制、超时和敏感字段脱敏 |
| 查询缓存 | 对相同问题和相同时间范围缓存 SQL 与结果 |
| 权限控制 | 按用户角色裁剪可访问的表、字段和行 |
| 指标平台 | 把指标定义抽成独立语义层，支持版本管理 |
| 反馈闭环 | 记录用户对 SQL 和结果的反馈，用于召回和 Prompt 优化 |

---

## 附录：目录结构

```text
apparel-ask/
├── app/
│   ├── agent/            # LangGraph 图、State、Context 和 12 个节点
│   ├── api/              # FastAPI 路由、依赖注入、请求/响应结构
│   ├── clients/          # MySQL、Qdrant、ES、Embedding 客户端管理
│   ├── conf/             # 配置 dataclass 与加载逻辑
│   ├── core/             # 日志、request_id 上下文
│   ├── entities/         # 业务实体
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── prompt/           # Prompt 模板加载工具
│   ├── repositories/     # MySQL、Qdrant、ES 数据访问层
│   ├── scripts/          # 数仓生成、知识库构建脚本
│   └── services/         # 知识库构建与问数查询服务
├── conf/                 # app_config.yaml、meta_config.yaml
├── docker/               # Compose、MySQL 初始化 SQL、ES IK、Embedding 模型
├── frontend/             # React + Vite + TypeScript + Tailwind CSS
├── prompts/              # 关键词扩展、过滤、SQL 生成与修正模板
├── main.py               # FastAPI 入口
└── pyproject.toml        # Python 依赖与工具配置
```

---

## 许可

本项目代码采用 MIT 许可证，版权与许可声明见 [LICENSE](LICENSE)。
