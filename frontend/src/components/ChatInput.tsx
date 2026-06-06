"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}

export default function ChatInput({ onSend, onStop, isStreaming }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  // Refocus after streaming ends
  useEffect(() => {
    if (!isStreaming) textareaRef.current?.focus();
  }, [isStreaming]);

  const handleSubmit = () => {
    const text = value.trim();
    if (!text || isStreaming) return;
    setValue("");
    onSend(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (isStreaming) { onStop(); return; }
      handleSubmit();
    }
  };

  return (
    <div className="relative flex items-end gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 focus-within:border-[var(--brand)] transition-colors">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about background, skills, projects, or book a call…"
        disabled={false}
        className="flex-1 resize-none bg-transparent text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none leading-relaxed min-h-[24px] max-h-[160px]"
      />

      {/* Send / Stop button */}
      {isStreaming ? (
        <button
          onClick={onStop}
          title="Stop generating"
          className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--error)] hover:bg-red-500/10 transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
            <rect x="2" y="2" width="8" height="8" rx="1" />
          </svg>
        </button>
      ) : (
        <button
          onClick={handleSubmit}
          disabled={!value.trim()}
          title="Send (Enter)"
          className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-brand-600 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-brand-500 active:scale-95 transition-all"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      )}

      {/* Keyboard hint */}
      {value && !isStreaming && (
        <div className="absolute -top-6 right-0 text-[10px] text-[var(--text-muted)]">
          ↵ to send · ⇧↵ for newline
        </div>
      )}
    </div>
  );
}
