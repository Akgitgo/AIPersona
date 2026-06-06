"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { format } from "date-fns";
import type { Message } from "@/types";

const PERSONA_NAME = process.env.NEXT_PUBLIC_PERSONA_NAME || "AI";

interface Props {
  message: Message;
  isLast: boolean;
}

function SourceBadge({ source }: { source: string }) {
  const label = source.startsWith("github:")
    ? `⌥ ${source.replace("github:", "")}`
    : source === "resume"
    ? "📄 resume"
    : "✦ persona";

  return (
    <span className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-muted)] font-medium">
      {label}
    </span>
  );
}

function ConfidencePip({ score }: { score: number }) {
  const color =
    score >= 0.7 ? "bg-[var(--success)]" :
    score >= 0.45 ? "bg-[var(--warning)]" :
    "bg-[var(--error)]";
  const label =
    score >= 0.7 ? "High confidence" :
    score >= 0.45 ? "Medium confidence" :
    "Low confidence";

  return (
    <span title={`${label} (${(score * 100).toFixed(0)}%)`} className="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      {(score * 100).toFixed(0)}%
    </span>
  );
}

export default function ChatMessage({ message, isLast }: Props) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="max-w-[80%]">
          <div className="bg-brand-600 text-white text-sm px-4 py-2.5 rounded-2xl rounded-br-sm leading-relaxed">
            {message.content}
          </div>
          <p className="text-right text-[10px] text-[var(--text-muted)] mt-1 pr-1">
            {format(message.timestamp, "HH:mm")}
          </p>
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex gap-3 animate-slide-up">
      {/* Avatar */}
      <div className="shrink-0 mt-1">
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-400 to-brand-700 flex items-center justify-center text-xs font-bold text-white">
          {PERSONA_NAME.charAt(0).toUpperCase()}
        </div>
      </div>

      {/* Bubble */}
      <div className="flex-1 min-w-0">
        <div className="bg-[var(--bg-surface)] border border-[var(--border)] rounded-2xl rounded-tl-sm px-4 py-3">
          {message.content ? (
            <div className={`prose-chat text-[var(--text-primary)] ${message.isStreaming ? "streaming-cursor" : ""}`}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          ) : (
            /* Typing indicator while waiting for first token */
            <div className="flex items-center gap-1.5 py-1">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          )}
        </div>

        {/* Meta row: timestamp + sources + confidence */}
        {!message.isStreaming && message.content && (
          <div className="flex items-center gap-2 mt-1.5 px-1 flex-wrap">
            <span className="text-[10px] text-[var(--text-muted)]">
              {format(message.timestamp, "HH:mm")}
            </span>
            {(message.sources ?? []).length > 0 && (
              <div className="flex items-center gap-1 flex-wrap">
                {(message.sources ?? []).map(s => (
                  <SourceBadge key={s} source={s} />
                ))}
              </div>
            )}
            {message.confidence !== undefined && message.confidence > 0 && (
              <ConfidencePip score={message.confidence} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
