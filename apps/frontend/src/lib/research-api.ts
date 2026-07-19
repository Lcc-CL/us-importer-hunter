/**
 * Typed client for the internal research API (v0.2).
 *
 * These endpoints are an internal development surface: the backend refuses to
 * be deployed anonymously until connection-level IP pinning lands, and the
 * panel that uses this client is behind NEXT_PUBLIC_ENABLE_RESEARCH.
 *
 * Nothing here reads or forwards credentials — the API never returns them.
 */

import { API_BASE_URL, ApiError, ApiNetworkError, type ApiErrorPayload } from "./api";

const V1 = `${API_BASE_URL}/api/v1`;

export type ResearchStatus = "completed" | "partial" | "failed";

export type ResearchFailureCode =
  | "unreachable"
  | "robots_denied"
  | "needs_browser"
  | "budget_exceeded"
  | "extraction_failed"
  | "invalid_url";

/** The eight canonical kinds — identical to the scorer's and the form's. */
export type ClaimKind =
  | "import_activity"
  | "china_dependency"
  | "shipping_fit"
  | "cargo_value_potential"
  | "company_scale"
  | "growth_signal"
  | "logistics_complexity"
  | "pain_point";

export interface ResearchPage {
  position: number;
  url: string;
  final_url: string;
  http_status: number;
  content_type: string;
  fetched_at: string;
  content_chars: number;
  truncated: boolean;
  discovery_reason: string;
}

export interface ResearchClaim {
  position: number;
  kind: ClaimKind;
  detail: string;
  evidence_snippet: string;
  source_url: string;
  confidence: number;
}

export interface RejectedClaim {
  reason: string;
  kind: string;
  detail: string;
  warning: string;
}

export interface ResearchProfile {
  summary: string | null;
  industry: string | null;
  products: string[];
  locations: string[];
  size_hint: string | null;
  year_founded: string | null;
  mentions_importing: boolean | null;
}

export interface ResearchExtractorInfo {
  provider: string;
  model: string;
  prompt_version: string;
}

export interface ResearchRun {
  research_id: string;
  company_id: string | null;
  company_name: string;
  website: string;
  status: ResearchStatus;
  failure_code: ResearchFailureCode | null;
  started_at: string;
  completed_at: string | null;
  pages_fetched: number;
  pages_failed: number;
  claims_extracted: number;
  claims_validated: number;
  extractor: ResearchExtractorInfo | null;
  profile: ResearchProfile;
  pages: ResearchPage[];
  claims: ResearchClaim[];
  rejected_claims: RejectedClaim[];
  warnings: string[];
  /** Dimensions with no reliable evidence. Never a negative signal. */
  unknown_dimensions: string[];
  /** Language the conclusions were written in. Evidence keeps the page's own. */
  output_language: string;
}

export interface ResearchRunCreated extends ResearchRun {
  action: string;
}

export interface ResearchRunSummary {
  research_id: string;
  website: string;
  status: ResearchStatus;
  failure_code: ResearchFailureCode | null;
  started_at: string;
  completed_at: string | null;
  pages_fetched: number;
  claims_validated: number;
}

export interface ResearchRunList {
  company_id: string;
  runs: ResearchRunSummary[];
}

export type ReviewDecision = "accepted" | "edited" | "rejected";

export interface ClaimDecisionInput {
  claim_position: number;
  decision: ReviewDecision;
  edited_detail?: string;
  edited_kind?: ClaimKind;
}

export interface PromotionResult {
  claim_position: number;
  decision: ReviewDecision;
  kind: string;
  detail: string;
  company_source_position: number | null;
  company_signal_position: number | null;
  source_reused: boolean;
  idempotent: boolean;
}

/** Exactly the shape the existing prospect form needs. */
export interface ApplicationPayload {
  company_name: string;
  website: string;
  sources: Array<{ source: string; reference: string }>;
  signals: Array<{ kind: string; detail: string }>;
}

export interface ConfirmResponse {
  research_id: string;
  action: "applied" | "recorded" | "unchanged";
  company_id: string | null;
  summary: { accepted: number; edited: number; rejected: number; total: number };
  promotions: PromotionResult[];
  application_payload: ApplicationPayload | null;
  warnings: string[];
}

export interface StartResearchInput {
  company_id?: string;
  company_name?: string;
  website?: string;
  /** Conclusions are written in this language; evidence never is. */
  output_language?: "zh-CN" | "en-US";
}

export interface ConfirmResearchInput {
  reviewer_name: string;
  target_company_id?: string;
  decisions: ClaimDecisionInput[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isApiErrorPayload(value: unknown): value is ApiErrorPayload {
  return (
    isRecord(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    typeof value.request_id === "string"
  );
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${V1}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiNetworkError(
      "Unable to reach the API. Confirm the backend is running on the configured URL.",
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    // FastAPI's HTTPException uses {detail}; the app's own errors use the
    // typed envelope. Normalize both so callers see one shape.
    const detail =
      isRecord(payload) && typeof payload.detail === "string" ? payload.detail : null;
    const fallback: ApiErrorPayload = {
      code: `http_${response.status}`,
      message: detail ?? `The API returned HTTP ${response.status}.`,
      request_id: response.headers.get("X-Request-ID") ?? "not_available",
    };
    throw new ApiError(response.status, isApiErrorPayload(payload) ? payload : fallback);
  }

  return payload as T;
}

export function startResearch(input: StartResearchInput): Promise<ResearchRunCreated> {
  return requestJson<ResearchRunCreated>("/research/runs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getResearchRun(runId: string): Promise<ResearchRun> {
  return requestJson<ResearchRun>(`/research/runs/${encodeURIComponent(runId)}`);
}

export function listCompanyResearchRuns(companyId: string): Promise<ResearchRunList> {
  return requestJson<ResearchRunList>(
    `/companies/${encodeURIComponent(companyId)}/research-runs`,
  );
}

export function confirmResearchRun(
  runId: string,
  input: ConfirmResearchInput,
): Promise<ConfirmResponse> {
  return requestJson<ConfirmResponse>(
    `/research/runs/${encodeURIComponent(runId)}/confirm`,
    { method: "POST", body: JSON.stringify(input) },
  );
}
