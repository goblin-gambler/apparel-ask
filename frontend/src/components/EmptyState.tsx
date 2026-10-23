/**
 * 首页空状态组件
 * 展示产品定位、执行链路和可点击的示例问数问题
 */
import { Layers, Search, Table2, Terminal } from "lucide-react";

type EmptyStateProps = {
  examples: string[];
  onUseExample: (example: string) => void;
};

const pipeline = [
  {
    index: "壹",
    title: "语义解析",
    detail: "抽取指标、维度、时间范围与过滤条件",
    icon: Search,
  },
  {
    index: "贰",
    title: "三路召回",
    detail: "字段、指标、取值分别检索，给出候选 Schema",
    icon: Layers,
  },
  {
    index: "叁",
    title: "SQL 闭环",
    detail: "生成后 EXPLAIN 校验，失败自动带错误上下文校正",
    icon: Terminal,
  },
  {
    index: "肆",
    title: "结果交付",
    detail: "只读执行，返回结果表格与执行流程",
    icon: Table2,
  },
];

const footprint = [
  ["12", "张表"],
  ["87", "个字段"],
  ["21", "个指标"],
  ["2024", "全年"],
];

export function EmptyState({ examples, onUseExample }: EmptyStateProps) {
  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center px-5 py-14 lg:px-8">
      <div className="mb-12">
        <div className="mb-5 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.3em] text-cinnabar">
          <span className="hairline w-10" />
          Schema RAG · NL2SQL
        </div>

        <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
          <h1 className="font-serif text-5xl leading-none tracking-[0.08em] text-ink sm:text-6xl">
            服装问数
          </h1>
          <div className="mb-1 font-mono text-[11px] uppercase tracking-[0.24em] text-ink/40">
            Apparel Ask · 经营数据智能体
          </div>
        </div>

        <p className="mt-6 max-w-2xl text-[15px] leading-8 text-ink/60">
          用一句中文描述经营问题，系统完成关键词抽取、三路 Schema 召回、SQL 生成与校验，
          最后以表格回答。字段和指标来自知识库，不靠模型记忆。
        </p>
      </div>

      <div className="grid gap-px border border-ink/10 bg-ink/10 sm:grid-cols-2 lg:grid-cols-4">
        {pipeline.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.title} className="bg-[#f8f3ea]/90 px-5 py-6">
              <div className="mb-5 flex items-center justify-between">
                <span className="font-serif text-lg text-cinnabar/80">{item.index}</span>
                <Icon className="h-4 w-4 text-ink/35" aria-hidden="true" />
              </div>
              <div className="font-serif text-base tracking-[0.08em] text-ink">{item.title}</div>
              <p className="mt-2 text-xs leading-6 text-ink/55">{item.detail}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-baseline gap-x-8 gap-y-3 border-y border-ink/10 py-4">
        {footprint.map(([value, label]) => (
          <div key={label} className="flex items-baseline gap-2">
            <span className="font-serif text-xl text-ink">{value}</span>
            <span className="text-[11px] tracking-[0.08em] text-ink/45">{label}</span>
          </div>
        ))}
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-ink/35">
          2024 全年 · 服装零售数仓
        </span>
      </div>

      <div className="mt-8">
        <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.24em] text-ink/40">
          从一个问题开始
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {examples.map((example, index) => (
            <button
              key={example}
              type="button"
              onClick={() => onUseExample(example)}
              className="group flex min-h-[76px] items-start gap-3 border border-ink/10 bg-[#fbf7ef]/70 px-4 py-4 text-left transition hover:border-cinnabar/35 hover:bg-[#fffdf8] focus:outline-none focus:ring-1 focus:ring-cinnabar/40"
            >
              <span className="pt-0.5 font-mono text-[10px] text-cinnabar/60">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="text-[15px] leading-6 text-ink/75 transition group-hover:text-ink">
                {example}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
