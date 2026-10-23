/**
 * 聊天消息气泡组件
 * 组合展示用户问题、智能体回复、执行流程和结果表格
 */
import { Copy } from "lucide-react";
import { ResultTable } from "./ResultTable";
import { StepRail } from "./StepRail";
import { cn, formatTime, toClipboardText } from "../lib/format";
import type { ChatMessage } from "../types/agent";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  const copy = async () => {
    const text = message.result ? toClipboardText(message.result) : message.content;
    await navigator.clipboard.writeText(text);
  };

  return (
    <article className={cn("group flex gap-4", isUser && "justify-end")}>
      {!isUser && (
        <div className="mt-1 hidden h-9 w-9 shrink-0 place-items-center border border-ink/20 font-serif text-sm text-ink/60 sm:grid">
          茗
        </div>
      )}

      <div className={cn("min-w-0 max-w-[900px] flex-1", isUser && "flex max-w-[720px] flex-col items-end")}>
        {!isUser && (
          <div className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-ink/40">
            <span className="h-1 w-1 bg-cinnabar" />
            Agent · 经营数据智能体
          </div>
        )}

        <div
          className={cn(
            "relative border px-5 py-4",
            isUser
              ? "w-auto max-w-full border-ink bg-ink text-paper"
              : "w-full border-ink/10 bg-[#fbf7ef]/85 text-ink backdrop-blur",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <p className={cn("whitespace-pre-wrap text-[15px] leading-7", isUser ? "tracking-[0.01em]" : "")}>
              {message.content}
            </p>
            {!isUser && message.status !== "streaming" && (
              <button
                type="button"
                onClick={copy}
                className="shrink-0 border border-transparent p-1.5 text-ink/40 opacity-0 outline-none transition hover:border-ink/15 hover:text-cinnabar focus:opacity-100 focus:ring-1 focus:ring-cinnabar/40 group-hover:opacity-100"
                title="复制"
                aria-label="复制"
              >
                <Copy className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>

          {message.error && (
            <div className="mt-3 border-l-2 border-cinnabar bg-cinnabar/5 px-3 py-2 text-sm text-cinnabar">
              {message.error}
            </div>
          )}

          {!isUser && <StepRail steps={message.steps} />}
          {!isUser && message.result !== undefined && <ResultTable data={message.result} />}

          <div
            className={cn(
              "mt-3 font-mono text-[10px] tracking-[0.08em]",
              isUser ? "text-paper/50" : "text-ink/40",
            )}
          >
            {formatTime(message.createdAt)}
          </div>
        </div>
      </div>

      {isUser && (
        <div className="mt-1 hidden h-9 w-9 shrink-0 place-items-center border border-ink font-serif text-sm text-ink sm:grid">
          问
        </div>
      )}
    </article>
  );
}
