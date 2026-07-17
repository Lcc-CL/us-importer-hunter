/** Typed client for the three browser-facing MVP endpoints (ADR-0024). */

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const API_V1_URL = `${API_BASE_URL}/api/v1`;

export type OverallStatus = "COMPLETED" | "PARTIAL" | "REJECTED" | "FAILED";

export type StageStatus =
  | "CREATED"
  | "MERGED"
  | "QUALIFIED"
  | "REVIEW"
  | "RESEARCH_MORE"
  | "SELECTED"
  | "GENERATED"
  | "SKIPPED"
  | "REJECTED"
  | "FAILED";

export type ApprovalStatus = "generated" | "approved" | "rejected";

export interface ProspectSourceRequest {
  source: string;
  reference: string;
  retrieved_at?: string | null;
}

export interface ProspectSignalRequest {
  kind: string;
  detail: string;
}

export interface ProspectContactRequest {
  name: string;
  source: string;
  title?: string | null;
  email?: string | null;
  linkedin_url?: string | null;
  phone?: string | null;
}

export interface ProspectAnalysisRequest {
  company: {
    name: string;
    website?: string | null;
    sources: ProspectSourceRequest[];
    signals?: ProspectSignalRequest[];
  };
  contact?: ProspectContactRequest | null;
  sender: {
    name: string;
    company: string;
    value_proposition: string;
  };
  options?: {
    generate_email: boolean;
  };
}

export interface CompanyAnalysisResponse {
  action: StageStatus;
  company_id: string | null;
  name: string;
  notes: string[];
}

export interface OpportunityAnalysisResponse {
  action: StageStatus;
  opportunity_id: string | null;
  score: number | null;
  confidence: number | null;
  data_completeness: number | null;
  qualification_decision: string | null;
  recommended_action: string | null;
  reasons: string[];
}

export interface ContactAnalysisResponse {
  action: StageStatus;
  contact_id: string | null;
  notes: string[];
}

export interface DecisionMakerAnalysisResponse {
  action: StageStatus;
  selected_contact_id: string | null;
  recommended_channel: string | null;
  confidence: number | null;
  reasons: string[];
}

export interface EmailDraftAnalysisResponse {
  action: StageStatus;
  outreach_id: string | null;
  version: number | null;
  subject: string | null;
  body: string | null;
  status: string | null;
  notes: string[];
}

export interface ProspectAnalysisResponse {
  request_id: string;
  overall_status: OverallStatus;
  company: CompanyAnalysisResponse;
  opportunity: OpportunityAnalysisResponse;
  contact: ContactAnalysisResponse;
  decision_maker: DecisionMakerAnalysisResponse;
  email_draft: EmailDraftAnalysisResponse;
  warnings: string[];
  created_at: string;
}

export interface CompanyDetailResponse {
  company_id: string;
  name: string;
  website: string | null;
  verified: boolean;
  sources: string[];
  signals: string[];
}

export interface AssessmentDetailResponse {
  opportunity_id: string;
  score: number;
  confidence: number;
  data_completeness: number | null;
  qualification_decision: string | null;
  recommended_action: string | null;
  reasons: string[];
  scoring_version: string;
  policy_version: string;
  assessed_at: string;
}

export interface ContactDetailResponse {
  contact_id: string;
  name: string;
  title: string | null;
  department: string;
  seniority: string;
  status: string;
  channels: Array<{
    type: string;
    value: string;
    verification_status: string;
  }>;
}

export interface DecisionMakerRankingResponse {
  contact_id: string;
  total_score: number;
  confidence: number;
  recommended_channel: string | null;
  reasons: string[];
}

export interface EmailDraftDetailResponse {
  outreach_id: string;
  version: number;
  subject: string;
  body: string;
  status: string;
  approval_status: ApprovalStatus;
  approved_at: string | null;
  approved_by_name: string | null;
  provider: string;
  model: string;
  prompt_version: string;
  generated_at: string;
}

export interface EmailDraftSummaryResponse {
  outreach_id: string;
  version: number;
  subject: string;
  status: string;
  approval_status: ApprovalStatus;
  approved_at: string | null;
  approved_by_name: string | null;
  generated_at: string;
}

export interface ProspectDetailResponse {
  company: CompanyDetailResponse;
  latest_assessment: AssessmentDetailResponse | null;
  qualification_decision: string | null;
  contacts: ContactDetailResponse[];
  decision_maker: {
    selected_contact_id: string | null;
    rankings: DecisionMakerRankingResponse[];
  };
  latest_email_draft: EmailDraftDetailResponse | null;
  draft_history: EmailDraftSummaryResponse[];
}

export interface DraftApprovalRequest {
  approver_name: string;
}

export interface DraftApprovalResponse {
  outreach_id: string;
  version: number;
  status: string;
  approval_status: ApprovalStatus;
  approved_at: string;
  approved_by: string;
  approved_by_name: string;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  request_id: string;
}

export interface ClientErrorDetails {
  code: string;
  message: string;
  request_id: string | null;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: ApiErrorPayload,
  ) {
    super(payload.message);
    this.name = "ApiError";
  }
}

export class ApiNetworkError extends Error {
  readonly code = "network_error";

  constructor(message: string) {
    super(message);
    this.name = "ApiNetworkError";
  }
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

export function getClientErrorDetails(error: unknown): ClientErrorDetails {
  if (error instanceof ApiError) {
    return error.payload;
  }
  if (error instanceof ApiNetworkError) {
    return { code: error.code, message: error.message, request_id: null };
  }
  return {
    code: "unexpected_client_error",
    message: "Something unexpected happened while processing the request.",
    request_id: null,
  };
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_V1_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
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
    const fallback: ApiErrorPayload = {
      code: "unexpected_api_response",
      message: `The API returned HTTP ${response.status}.`,
      request_id: response.headers.get("X-Request-ID") ?? "not_available",
    };
    throw new ApiError(
      response.status,
      isApiErrorPayload(payload) ? payload : fallback,
    );
  }

  return payload as T;
}

export function analyzeProspect(
  request: ProspectAnalysisRequest,
): Promise<ProspectAnalysisResponse> {
  return requestJson<ProspectAnalysisResponse>("/mvp/prospects/analyze", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getProspect(companyId: string): Promise<ProspectDetailResponse> {
  return requestJson<ProspectDetailResponse>(
    `/mvp/prospects/${encodeURIComponent(companyId)}`,
  );
}

export function approveDraft(
  outreachId: string,
  version: number,
  request: DraftApprovalRequest,
): Promise<DraftApprovalResponse> {
  return requestJson<DraftApprovalResponse>(
    `/mvp/outreaches/${encodeURIComponent(outreachId)}/drafts/${version}/approve`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}
