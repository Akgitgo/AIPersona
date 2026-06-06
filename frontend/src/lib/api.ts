import type { BookingPayload, BookingResult, StreamEvent, TimeSlot } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Chat (streaming SSE) ──────────────────────────────────────────────────────

export async function* streamChat(
  message: string,
  sessionId: string
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, stream: true }),
  });

  if (!res.ok) {
    const err = await res.text().catch(() => "Network error");
    throw new Error(err);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return;
        try {
          yield JSON.parse(raw) as StreamEvent;
        } catch {
          // Malformed chunk — skip
        }
      }
    }
  }
}

// ── Calendar ──────────────────────────────────────────────────────────────────

export async function getSlots(
  daysAhead: number = 7,
  timezone: string = Intl.DateTimeFormat().resolvedOptions().timeZone
): Promise<TimeSlot[]> {
  const res = await fetch(`${API_URL}/api/calendar/slots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ days_ahead: daysAhead, timezone }),
  });
  if (!res.ok) throw new Error("Failed to fetch slots");
  const data = await res.json();
  return data.slots as TimeSlot[];
}

export async function bookSlot(payload: BookingPayload): Promise<BookingResult> {
  const res = await fetch(`${API_URL}/api/calendar/book`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Booking request failed");
  return res.json() as Promise<BookingResult>;
}

// ── Session ───────────────────────────────────────────────────────────────────

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`${API_URL}/api/chat/session/${sessionId}`, { method: "DELETE" });
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}
