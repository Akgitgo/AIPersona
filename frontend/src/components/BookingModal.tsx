"use client";

import { useEffect, useState } from "react";
import { bookSlot, getSlots } from "@/lib/api";
import type { BookingResult, TimeSlot } from "@/types";

interface Props { onClose: () => void; }

type Step = "slots" | "form" | "done" | "error";

export default function BookingModal({ onClose }: Props) {
  const [step, setStep] = useState<Step>("slots");
  const [slots, setSlots] = useState<TimeSlot[]>([]);
  const [selected, setSelected] = useState<TimeSlot | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BookingResult | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState("");
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  useEffect(() => {
    getSlots(7, tz)
      .then(s => { setSlots(s); setLoading(false); })
      .catch(() => { setErr("Couldn't load slots."); setLoading(false); setStep("error"); });
  }, [tz]);

  // Close on Escape
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const handleBook = async () => {
    if (!selected || !name.trim() || !email.trim()) return;
    setSubmitting(true);
    try {
      const r = await bookSlot({ name, email, start_time: selected.start, notes, timezone: tz });
      setResult(r);
      setStep(r.success ? "done" : "error");
    } catch {
      setErr("Booking failed — please try again.");
      setStep("error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative w-full max-w-md bg-[var(--bg-secondary)] border border-[var(--border)] rounded-2xl shadow-2xl animate-slide-up overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Book a 30-min call</h2>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">Pick a slot · Confirm details · Done</p>
          </div>
          <button onClick={onClose} className="focus-ring w-7 h-7 rounded-full flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 max-h-[70vh] overflow-y-auto">

          {/* STEP: slots */}
          {step === "slots" && (
            <>
              {loading ? (
                <div className="py-8 flex flex-col items-center gap-3">
                  <div className="w-5 h-5 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                  <p className="text-xs text-[var(--text-secondary)]">Checking calendar…</p>
                </div>
              ) : slots.length === 0 ? (
                <p className="py-6 text-center text-sm text-[var(--text-secondary)]">No slots available in the next 7 days. Try the direct link below.</p>
              ) : (
                <div className="grid gap-2">
                  {slots.map(s => (
                    <button
                      key={s.start}
                      onClick={() => { setSelected(s); setStep("form"); }}
                      className="focus-ring w-full text-left px-4 py-3 rounded-xl border border-[var(--border)] hover:border-brand-500 hover:bg-[var(--brand-dim)] text-sm text-[var(--text-primary)] transition-all group"
                    >
                      <span className="mr-2 text-[var(--text-muted)] group-hover:text-brand-400">📅</span>
                      {s.formatted}
                    </button>
                  ))}
                </div>
              )}
              {process.env.NEXT_PUBLIC_CALCOM_URL && (
                <a href={process.env.NEXT_PUBLIC_CALCOM_URL} target="_blank" rel="noreferrer"
                  className="flex items-center justify-center gap-1.5 mt-4 text-xs text-[var(--text-secondary)] hover:text-brand-400 transition-colors">
                  Or open on Cal.com →
                </a>
              )}
            </>
          )}

          {/* STEP: form */}
          {step === "form" && selected && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-[var(--brand-dim)] border border-brand-500/20">
                <span className="text-base">📅</span>
                <div>
                  <p className="text-xs font-medium text-brand-300">{selected.formatted}</p>
                  <button onClick={() => setStep("slots")} className="text-[10px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] mt-0.5">← Change slot</button>
                </div>
              </div>
              {[
                { label: "Your name", value: name, set: setName, type: "text", placeholder: "Jane Smith" },
                { label: "Work email", value: email, set: setEmail, type: "email", placeholder: "jane@company.com" },
              ].map(f => (
                <div key={f.label}>
                  <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">{f.label}</label>
                  <input type={f.type} value={f.value} onChange={e => f.set(e.target.value)}
                    placeholder={f.placeholder}
                    className="w-full bg-[var(--bg-elevated)] border border-[var(--border)] focus:border-brand-500 rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none transition-colors" />
                </div>
              ))}
              <div>
                <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">Notes <span className="text-[var(--text-muted)]">(optional)</span></label>
                <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} placeholder="Anything you'd like to cover…"
                  className="w-full bg-[var(--bg-elevated)] border border-[var(--border)] focus:border-brand-500 rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none resize-none transition-colors" />
              </div>
              <button onClick={handleBook} disabled={submitting || !name.trim() || !email.trim()}
                className="focus-ring w-full py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium text-white transition-all flex items-center justify-center gap-2">
                {submitting ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Booking…</> : "Confirm booking"}
              </button>
            </div>
          )}

          {/* STEP: done */}
          {step === "done" && result && (
            <div className="py-4 text-center space-y-4">
              <div className="w-12 h-12 rounded-full bg-[var(--success)]/15 flex items-center justify-center mx-auto text-2xl">✓</div>
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">You're booked!</p>
                <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">{result.confirmation_message}</p>
              </div>
              {result.meeting_url && (
                <a href={result.meeting_url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-brand-400 hover:underline">📹 Join link</a>
              )}
              <button onClick={onClose} className="focus-ring w-full py-2 rounded-xl border border-[var(--border)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">Close</button>
            </div>
          )}

          {/* STEP: error */}
          {step === "error" && (
            <div className="py-4 text-center space-y-3">
              <p className="text-2xl">⚠️</p>
              <p className="text-sm text-[var(--text-secondary)]">{err || "Something went wrong."}</p>
              <button onClick={() => { setStep("slots"); setErr(""); setLoading(true); getSlots(7, tz).then(s => { setSlots(s); setLoading(false); }).catch(() => setLoading(false)); }}
                className="text-xs text-brand-400 hover:underline">Try again</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
