"""
SQL 生成节点

负责根据用户问题和前面整理出的表结构 指标 日期 数据库环境生成候选 SQL。
本节点只生成 SQL，不做校验和执行，后续会交给 validate_sql 和 run_sql 继续处理。
"""

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import (
    ColumnInfoState,
    DataAgentState,
    MetricInfoState,
    TableInfoState,
)
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository


async def _ensure_metric_columns(
    table_infos: list[TableInfoState],
    metric_infos: list[MetricInfoState],
    meta_mysql_repository: MetaMySQLRepository,
) -> list[TableInfoState]:
    """确保指标依赖字段出现在表上下文中

    过滤表信息时模型可能只保留问题字面提到的字段，把指标口径依赖的字段裁掉，
    例如按渠道问折扣率时丢掉 dim_product.list_price。
    这里在生成 SQL 前按指标依赖字段兜底补齐，避免上下文缺少算指标所需的列。
    """

    existing = {
        (table_info["name"], column_info["name"])
        for table_info in table_infos
        for column_info in table_info["columns"]
    }
    table_map = {table_info["name"]: table_info for table_info in table_infos}
    added: list[str] = []

    for metric_info in metric_infos:
        for column_id in metric_info["relevant_columns"]:
            table_id, _, column_name = column_id.partition(".")
            if (table_id, column_name) in existing:
                continue

            column_info = await meta_mysql_repository.get_column_info_by_id(column_id)
            if column_info is None:
                continue

            table_info = table_map.get(table_id)
            if table_info is None:
                table_entity = await meta_mysql_repository.get_table_info_by_id(table_id)
                if table_entity is None:
                    continue
                table_info = TableInfoState(
                    name=table_entity.name,
                    role=table_entity.role,
                    description=table_entity.description,
                    columns=[],
                )
                table_infos.append(table_info)
                table_map[table_id] = table_info

            table_info["columns"].append(
                ColumnInfoState(
                    name=column_info.name,
                    type=column_info.type,
                    role=column_info.role,
                    examples=column_info.examples,
                    description=column_info.description,
                    alias=column_info.alias,
                )
            )
            existing.add((table_id, column_name))
            added.append(column_id)

    if added:
        logger.info(f"补齐指标依赖字段：{added}")

    return table_infos


async def generate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """基于已检索和过滤的上下文生成 SQL"""

    writer = runtime.stream_writer
    step = "生成SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 这些上下文都由前置节点准备完成，模型只在给定表 字段 指标口径范围内生成 SQL
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        date_info = state["date_info"]
        db_info = state["db_info"]
        query = state["query"]

        # 过滤节点可能裁掉指标依赖字段，这里补齐后再交给模型，同时写回状态供修正节点复用
        table_infos = await _ensure_metric_columns(
            table_infos,
            metric_infos,
            runtime.context["meta_mysql_repository"],
        )

        prompt = PromptTemplate(
            template=load_prompt("generate_sql"),
            input_variables=[
                "table_infos",
                "metric_infos",
                "date_info",
                "db_info",
                "query",
            ],
        )
        # SQL 生成节点只需要纯文本 SQL，不能要求模型输出 JSON 或 Markdown 代码块
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {
                # YAML 更适合放进提示词：保留嵌套结构 顺序和中文说明，方便模型理解表字段关系
                "table_infos": yaml.dump(
                    table_infos, allow_unicode=True, sort_keys=False
                ),
                "metric_infos": yaml.dump(
                    metric_infos, allow_unicode=True, sort_keys=False
                ),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
                "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
                "query": query,
            }
        )
        logger.info(f"生成的SQL：{result}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"sql": result, "table_infos": table_infos}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
