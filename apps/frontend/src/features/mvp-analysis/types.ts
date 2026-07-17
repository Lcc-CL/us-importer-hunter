import type { ProspectContactRequest } from "@/lib/api";

export type MvpPageState =
  | "idle"
  | "submitting"
  | "success"
  | "partial"
  | "rejected"
  | "error"
  | "refreshing"
  | "approving";

export interface SubmittedProspectContext {
  contact: ProspectContactRequest | null;
  senderName: string;
}
