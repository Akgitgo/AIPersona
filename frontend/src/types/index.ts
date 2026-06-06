export type Role = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: Date;
  sources?: string[];
  confidence?: number;
  isStreaming?: boolean;
}

export interface TimeSlot {
  start: string;
  end: string;
  formatted: string;
}

export interface BookingPayload {
  name: string;
  email: string;
  start_time: string;
  notes?: string;
  timezone: string;
}

export interface BookingResult {
  success: boolean;
  booking_id?: string;
  meeting_url?: string;
  calendar_link?: string;
  confirmation_message: string;
}

export interface StreamEvent {
  type: "sources" | "token" | "done" | "error";
  data: unknown;
  confidence?: number;
}

export interface SuggestedPrompt {
  label: string;
  message: string;
  icon: string;
}
