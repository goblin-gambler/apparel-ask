/**
 * 聊天输入区组件
 * 处理问题输入、发送和停止当前流式请求
 */
import { ArrowUp, Square } from "lucide-react";
import { FormEvent, KeyboardEvent, useRef } from "react";
import { cn } from "../lib/format";

type ComposerProps = {
    value: string;
    disabled: boolean;
    isStreaming: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
    onStop: () => void;
};

export function Composer({
    value,
    disabled,
    isStreaming,
    onChange,
    onSubmit,
    onStop,
}: ComposerProps) {
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (!disabled) onSubmit();
    };

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) onSubmit();
        }
    };

    return (
        <form
            onSubmit={submit}
            className="border-t border-ink/10 bg-paper/85 px-4 pb-4 pt-3 backdrop-blur lg:px-8"
        >
            <div className="mx-auto max-w-5xl">
                <div className="flex items-end gap-3 border-b border-ink/20 pb-2 transition focus-within:border-cinnabar/60">
                    <span className="mb-3 hidden font-serif text-sm text-cinnabar/70 sm:block">
                        问
                    </span>
                    <textarea
                        ref={textareaRef}
                        value={value}
                        onChange={(event) => onChange(event.target.value)}
                        onKeyDown={onKeyDown}
                        rows={1}
                        placeholder="写下你的经营问题，例如：2025 年第一季度各大区 GMV..."
                        className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-1 py-3 text-[15px] leading-6 text-ink outline-none placeholder:text-ink/35"
                    />
                    <button
                        type={isStreaming ? "button" : "submit"}
                        onClick={isStreaming ? onStop : undefined}
                        disabled={!isStreaming && disabled}
                        className={cn(
                            "mb-0.5 grid h-10 w-10 shrink-0 place-items-center text-paper transition focus:outline-none focus:ring-1 focus:ring-cinnabar/50 focus:ring-offset-2 focus:ring-offset-paper",
                            isStreaming
                                ? "bg-cinnabar hover:bg-cinnabar/90"
                                : "bg-ink hover:bg-soot disabled:cursor-not-allowed disabled:bg-ink/25",
                        )}
                        title={isStreaming ? "停止" : "发送"}
                        aria-label={isStreaming ? "停止" : "发送"}
                    >
                        {isStreaming ? (
                            <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
                        ) : (
                            <ArrowUp className="h-4 w-4" aria-hidden="true" />
                        )}
                    </button>
                </div>
                <div className="mt-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-ink/35">
                    <span>Enter 发送 · Shift + Enter 换行</span>
                    <span>只读 · 单条 SQL</span>
                </div>
            </div>
        </form>
    );
}
