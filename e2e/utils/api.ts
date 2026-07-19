/** Thin typed client for the endpoints the E2E suite drives directly. */

import { API_BASE_URL } from "./env";
import type { ProspectPayload } from "../fixtures/prospects";

const V1 = `${API_BASE_URL}/api/v1`;

export interface RuntimeStatus {
  provider: "fake" | "openai";
  model: string;
  environment: string;
}

export interface AnalysisResponse {
  request_id: string;
  overall_status: string;
  company: { action: string; company_id: string | null; name: string };
  opportunity: {
    action: string;
    opportunity_id: string | null;
    score: number | null;
    confidence: number | null;
    data_completeness: number | null;
    qualification_decision: string | null;
    recommended_action: string | null;
    reasons: string[];
  };
  decision_maker: { action: string; selected_contact_id: string | null };
  email_draft: {
    action: string;
    outreach_id: string | null;
    version: number | null;
    subject: string | null;
    body: string | null;
    status: string | null;
  };
  warnings: string[];
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${V1}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} → HTTP ${response.status}: ${text}`);
  }
  return JSON.parse(text) as T;
}

export function getRuntimeStatus(): Promise<RuntimeStatus> {
  return json<RuntimeStatus>("/health/runtime");
}

export function analyze(payload: ProspectPayload): Promise<AnalysisResponse> {
  return json<AnalysisResponse>("/mvp/prospects/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProspect(companyId: string): Promise<Record<string, unknown>> {
  return json(`/mvp/prospects/${encodeURIComponent(companyId)}`);
}
