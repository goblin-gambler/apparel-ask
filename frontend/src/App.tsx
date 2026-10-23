/**
 * 前端应用主组件
 * 负责聊天会话状态、SSE 事件消费和整体页面布局
 */
import {
  Activity,
  BarChart3,
  Eraser,
  MessageSquarePlus,
  Server,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { MessageBubble } from "./components/MessageBubble";
import { streamQuery } from "./lib/agentApi";
import { cn, summarizeResult } from "./lib/format";
import type { AgentEvent, ChatMessage, StepState } from "./types/agent";

const examples = [
  "统计 2024 年各大区的 GMV，并按 GMV 从高到低排序",
  "统计 2024 年 11 月各品类的销量和销售额",
  "查询华东地区 2024 年销售额最高的前 5 家门店",
  "按会员等级统计 2024 年的订单量和客单价",
  "统计 2024 年各渠道的订单量和 GMV 占比",
  "2024 年第四季度哪些款断码最严重？",
];

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "Vite /api proxy";

function makeId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertStep(steps: StepState[] = [], event: Extract<AgentEvent, { type: "progress" }>) {
  const next = steps.filter((item) => item.step !== event.step);
  next.push({
    step: event.step,
    status: event.status,
    updatedAt: Date.now(),
  });
  return next;
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [activeController, setActiveController] = useState<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const isStreaming = Boolean(activeController);
  const canSubmit = draft.trim().length > 0 && !isStreaming;

  const completedCount = useMemo(
    () => messages.filter((message) => message.role === "assistant" && message.status === "done").length,
    [messages],
  );

  useEffect(() => {
    // 空状态下保持顶部，避免首次挂载就把英雄区滚出视野
    if (messages.length === 0) return;
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const startQuery = async (rawQuery = draft) => {
    const query = rawQuery.trim();
    if (!query || isStreaming) return;

    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      content: query,
      createdAt: Date.now(),
    };

    const assistantId = makeId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "正在解析问题并召回 Schema...",
      createdAt: Date.now(),
      status: "streaming",
      steps: [],
    };

    const controller = new AbortController();
    setActiveController(controller);
    setDraft("");
    setMessages((current) => [...current, userMessage, assistantMessage]);

    const onEvent = (event: AgentEvent) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message;

          if (event.type === "progress") {
            return {
              ...message,
              content: event.status === "running" ? `正在执行：${event.step}` : message.content,
              steps: upsertStep(message.steps, event),
            };
          }

          if (event.type === "result") {
            return {
              ...message,
              status: "done",
              content: summarizeResult(event.data),
              result: event.data,
            };
          }

          return {
            ...message,
            status: "error",
            content: "这次查询没有成功。",
            error: event.message,
          };
        }),
      );
    };

    try {
      await streamQuery(query, { signal: controller.signal, onEvent });
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId && message.status === "streaming"
            ? { ...message, status: "done", content: "流程已结束，后端未返回查询结果。" }
            : message,
        ),
      );
    } catch (error) {
      const isAbort = error instanceof DOMException && error.name === "AbortError";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                status: isAbort ? "done" : "error",
                content: isAbort ? "已停止本次查询。" : "无法连接分析接口。",
                error: isAbort ? undefined : error instanceof Error ? error.message : String(error),
              }
            : message,
        ),
      );
    } finally {
      setActiveController(null);
    }
  };

  const stopQuery = () => {
    activeController?.abort();
  };

  const clearConversation = () => {
    if (isStreaming) return;
    setMessages([]);
    setDraft("");
  };

  return (
    <div className="h-dvh overflow-hidden bg-paper font-sans text-ink">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(90deg,rgba(27,26,23,0.035)_1px,transparent_1px)] bg-[size:96px_100%]" />
      <div className="pointer-events-none fixed inset-0 grain" />

      <div className="relative grid h-full min-h-0 overflow-hidden lg:grid-cols-[292px_minmax(0,1fr)]">
        <aside className="hidden min-h-0 border-r border-ink/10 bg-[#efe8db]/55 backdrop-blur lg:flex lg:flex-col">
          <div className="border-b border-ink/10 px-5 pb-5 pt-6">
            <div className="flex items-center gap-3">
              <div className="seal h-11 w-11 text-lg">衣</div>
              <div>
                <div className="font-serif text-lg tracking-[0.16em] text-ink">服装问数</div>
                <div className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.22em] text-ink/45">
                  Apparel Ask
                </div>
              </div>
            </div>
            <p className="mt-5 text-xs leading-6 text-ink/55">
              以 Schema RAG 为底，把一句中文问题写成可执行 SQL。
            </p>
          </div>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-5">
            <button
              type="button"
              onClick={clearConversation}
              disabled={isStreaming}
              className="flex h-11 w-full items-center justify-center gap-2 border border-ink/20 bg-transparent text-sm font-semibold tracking-[0.06em] text-ink transition hover:border-cinnabar/50 hover:text-cinnabar disabled:cursor-not-allowed disabled:opacity-40"
            >
              <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
              新建会话
            </button>

            <section>
              <div className="mb-1 flex items-center gap-2 px-1 font-mono text-[10px] uppercase tracking-[0.24em] text-ink/40">
                <span className="h-1 w-1 bg-cinnabar" />
                示例问法
              </div>
              <div>
                {examples.map((example, index) => (
                  <button
                    key={example}
                    type="button"
                    disabled={isStreaming}
                    onClick={() => startQuery(example)}
                    className="group flex w-full gap-3 border-b border-ink/10 py-3 text-left transition last:border-b-0 hover:bg-white/35 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span className="pt-1 font-mono text-[10px] text-cinnabar/65">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="text-sm leading-6 text-ink/70 transition group-hover:text-ink">
                      {example}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          </div>

          <div className="border-t border-ink/10 px-5 py-4">
            <div className="grid gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-ink/45">
              <div className="flex items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2">
                  <Server className="h-3 w-3" aria-hidden="true" />
                  API
                </span>
                <span className="truncate normal-case tracking-normal">{API_BASE_URL}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-2">
                  <Activity className="h-3 w-3" aria-hidden="true" />
                  完成问答
                </span>
                <span>{completedCount}</span>
              </div>
            </div>
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-ink/10 bg-paper/75 px-4 backdrop-blur lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center border border-ink/20 text-ink lg:hidden">
                <BarChart3 className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <div className="truncate font-serif text-base tracking-[0.1em] text-ink">
                  经营数据智能体
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-ink/40">
                  Schema RAG · NL2SQL · LangGraph
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <span className="hidden items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-ink/45 sm:inline-flex">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    isStreaming ? "animate-pulse bg-cinnabar" : "bg-moss",
                  )}
                />
                {isStreaming ? "Running" : "Ready"}
              </span>
              <button
                type="button"
                onClick={clearConversation}
                disabled={messages.length === 0 || isStreaming}
                className="grid h-9 w-9 place-items-center border border-transparent text-ink/50 transition hover:border-ink/15 hover:text-cinnabar disabled:cursor-not-allowed disabled:opacity-30"
                title="清空会话"
                aria-label="清空会话"
              >
                <Eraser className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </header>

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            {messages.length === 0 ? (
              <EmptyState examples={examples} onUseExample={(example) => setDraft(example)} />
            ) : (
              <div className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 lg:px-8">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
              </div>
            )}
          </div>

          <Composer
            value={draft}
            disabled={!canSubmit}
            isStreaming={isStreaming}
            onChange={setDraft}
            onSubmit={() => startQuery()}
            onStop={stopQuery}
          />
        </main>
      </div>
    </div>
  );
}
