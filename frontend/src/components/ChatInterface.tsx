"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { nanoid } from "nanoid";
import { clearSession, streamChat } from "@/lib/api";
import type { Message, SuggestedPrompt } from "@/types";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import BookingModal from "./BookingModal";

const PERSONA_NAME = process.env.NEXT_PUBLIC_PERSONA_NAME || "AI Persona";

const SUGGESTED_PROMPTS: SuggestedPrompt[] = [
  { label: "Background", message: "Tell me about yourself and your background.", icon: "👤" },
  { label: "Best fit", message: "Why are you the right person for this AI Engineer role?", icon: "🎯" },
  { label: "Key project", message: "Walk me through your most complex AI project end to end.", icon: "🔧" },
  { label: "RAG expertise", message: "What's your experience building RAG systems in production?", icon: "🔍" },
  { label: "GitHub repos", message: "Tell me about your best GitHub repositories.", icon: "💻" },
  { label: "Book a call", message: "Can we schedule an interview? What times are you available?", icon: "📅" },
];

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content: `Hi there 👋 I'm the AI representative for **${PERSONA_NAME}**.

Ask me anything about their background, experience, technical skills, or GitHub projects — I'm grounded on their actual resume and repos, so every answer is specific and verifiable.

You can also **book an interview** directly from this chat. What would you like to know?`,
  timestamp: new Date(),
};

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [showBooking, setShowBooking] = useState(false);
  const [sessionId] = useState(() => nanoid());
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);

  // Auto-scroll on new tokens
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (isStreaming || !text.trim()) return;

    // Detect booking intent
    const bookingTriggers = ["schedule", "book", "availability", "interview", "call", "calendar", "slot", "meeting"];
    const isBookingIntent = bookingTriggers.some(t => text.toLowerCase().includes(t));

    const userMsg: Message = {
      id: nanoid(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    const assistantMsg: Message = {
      id: nanoid(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
      sources: [],
      confidence: undefined,
      isStreaming: true,
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    let aborted = false;
    abortRef.current = () => { aborted = true; };

    try {
      const gen = streamChat(text, sessionId);

      for await (const event of gen) {
        if (aborted) break;

        if (event.type === "sources") {
          const sources = event.data as string[];
          const confidence = event.confidence as number | undefined;
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantMsg.id ? { ...m, sources, confidence } : m
            )
          );
        } else if (event.type === "token") {
          const token = event.data as string;
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content + token }
                : m
            )
          );
        } else if (event.type === "done") {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
            )
          );
          // Show booking modal if booking-related
          if (isBookingIntent) {
            setTimeout(() => setShowBooking(true), 600);
          }
        } else if (event.type === "error") {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantMsg.id
                ? { ...m, content: "Sorry, something went wrong. Please try again.", isStreaming: false }
                : m
            )
          );
        }
      }
    } catch (err) {
      if (!aborted) {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsg.id
              ? {
                  ...m,
                  content: "Connection error — please check your network and try again.",
                  isStreaming: false,
                }
              : m
          )
        );
      }
    } finally {
      setIsStreaming(false);
    }
  }, [isStreaming, sessionId]);

  const handleSuggestedPrompt = (prompt: SuggestedPrompt) => {
    if (prompt.label === "Book a call") {
      setShowBooking(true);
      return;
    }
    sendMessage(prompt.message);
  };

  const handleReset = async () => {
    await clearSession(sessionId);
    setMessages([WELCOME_MESSAGE]);
  };

  const handleStop = () => {
    abortRef.current?.();
    setIsStreaming(false);
    setMessages(prev =>
      prev.map(m => m.isStreaming ? { ...m, isStreaming: false } : m)
    );
  };

  const showSuggestions = messages.length <= 1;

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto w-full px-4">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between py-4 border-b border-[var(--border)] shrink-0">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-brand-400 to-brand-700 flex items-center justify-center text-sm font-bold text-white">
              {PERSONA_NAME.charAt(0).toUpperCase()}
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-[var(--success)] rounded-full border-2 border-[var(--bg-primary)]" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)] leading-none">
              {PERSONA_NAME}
            </p>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">AI Representative · Online</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowBooking(true)}
            className="focus-ring hidden sm:flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-colors"
          >
            <span>📅</span> Book a call
          </button>
          <button
            onClick={handleReset}
            title="New conversation"
            className="focus-ring w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M2 8A6 6 0 0 1 14 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M14 4v4h-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </header>

      {/* ── Messages ───────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-6 space-y-2">
        {messages.map((msg, i) => (
          <ChatMessage key={msg.id} message={msg} isLast={i === messages.length - 1} />
        ))}

        {/* Suggested prompts — shown only at conversation start */}
        {showSuggestions && (
          <div className="pt-4 animate-fade-in">
            <p className="text-xs text-[var(--text-muted)] mb-3 px-1">Suggested questions</p>
            <div className="grid grid-cols-2 gap-2">
              {SUGGESTED_PROMPTS.map((p) => (
                <button
                  key={p.label}
                  onClick={() => handleSuggestedPrompt(p)}
                  className="focus-ring text-left px-3 py-2.5 rounded-xl border border-[var(--border)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-surface)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-all group"
                >
                  <span className="mr-1.5">{p.icon}</span>
                  <span className="group-hover:underline underline-offset-2">{p.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input ──────────────────────────────────────────────────────────── */}
      <div className="shrink-0 pb-4">
        <ChatInput
          onSend={sendMessage}
          onStop={handleStop}
          isStreaming={isStreaming}
        />
        <p className="text-center text-[10px] text-[var(--text-muted)] mt-2">
          AI representative · Grounded on resume + GitHub · May not know everything
        </p>
      </div>

      {/* ── Booking modal ──────────────────────────────────────────────────── */}
      {showBooking && <BookingModal onClose={() => setShowBooking(false)} />}
    </div>
  );
}
