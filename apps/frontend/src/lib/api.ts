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

export type DiscoveryTaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "partial_failed"
  | "failed";

export interface DiscoveryTaskResponse {
  task_id: string;
  original_prompt: string;
  requested_count: number;
  effective_count: number;
  parsed_region: string;
  parsed_category: string;
  parsed_keywords: string[];
  provider: string;
  status: DiscoveryTaskStatus;
  discovered_count: number;
  ingested_count: number;
  duplicate_count: number;
  failed_count: number;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DiscoveryCompanyResponse {
  candidate_id: string;
  position: number;
  company_id: string | null;
  company_name: string;
  website: string | null;
  domain: string | null;
  address: string | null;
  region: string | null;
  product_description: string | null;
  import_evidence: string | null;
  source: string;
  source_url: string | null;
  external_id: string | null;
  status: "discovered" | "ingested" | "duplicate" | "failed";
  is_duplicate: boolean;
  failure_reason: string | null;
  created_at: string;
}

export interface DiscoveryCompanyListResponse {
  task_id: string;
  companies: DiscoveryCompanyResponse[];
}

export type ProspectBatchStatus =
  | "pending"
  | "running"
  | "completed"
  | "partial_failed"
  | "failed";

export type ProspectBatchCompanyStatus =
  | "queued"
  | "running"
  | "completed"
  | "needs_review"
  | "failed";

export interface ProspectBatchResponse {
  batch_id: string;
  discovery_task_id: string;
  requested_count: number;
  effective_count: number;
  status: ProspectBatchStatus;
  queued_count: number;
  running_count: number;
  completed_count: number;
  needs_review_count: number;
  failed_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_summary: string | null;
}

export type ProspectJobStatus =
  | "pending"
  | "leased"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface ProspectBatchCreateResponse {
  batch_id: string;
  job_id: string;
  status: ProspectJobStatus;
  reused: boolean;
}

export interface ProspectBatchExecutionResponse {
  job_id: string;
  batch_id: string;
  status: ProspectJobStatus;
  available_at: string;
  attempt_count: number;
  max_attempts: number;
  heartbeat_at: string | null;
  last_error_code: string | null;
  last_error_summary: string | null;
  recovery_count: number;
  last_recovered_at: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface ProspectBatchCompanyResponse {
  company_id: string;
  company_name: string;
  position: number;
  pipeline_version: string;
  current_stage:
    | "queued"
    | "validating"
    | "researching"
    | "awaiting_evidence_review"
    | "scoring"
    | "discovering_contact"
    | "generating_draft"
    | "completed"
    | "needs_review"
    | "failed";
  status: ProspectBatchCompanyStatus;
  research_id: string | null;
  opportunity_id: string | null;
  selected_contact_id: string | null;
  outreach_id: string | null;
  draft_version: number | null;
  draft_id: string | null;
  score: number | null;
  qualification_decision: string | null;
  reasons: string[];
  contact_name: string | null;
  contact_email: string | null;
  contact_source_url: string | null;
  draft_subject: string | null;
  draft_status: string | null;
  error_code: string | null;
  error_summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  blocking_claim_count: number;
  resumed_at: string | null;
  resumed_from_stage: string | null;
  resume_count: number;
}

export interface ProspectBatchCompanyListResponse {
  batch_id: string;
  companies: ProspectBatchCompanyResponse[];
}

export interface EvidenceBlockerResponse {
  claim_position: number;
  status: "pending" | "accepted" | "rejected";
  decision: "accepted" | "edited" | "rejected" | null;
  kind: string;
  detail: string;
  evidence_snippet: string;
  source_url: string;
  fetched_at: string;
  confidence: number;
}

export interface ProspectCompanyBlockersResponse {
  batch_id: string;
  company_id: string;
  research_id: string;
  blocking_claim_count: number;
  pending_claim_count: number;
  claims: EvidenceBlockerResponse[];
}

export interface ProspectBatchSender {
  name: string;
  company: string;
  value_proposition: string;
}

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
  contact_mode?: "FULL_CONTACT" | "DEPARTMENT_CONTACT";
  /** null in DEPARTMENT_CONTACT mode — no person is asserted. */
  name: string | null;
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

export interface CompanySourceSummary {
  source: string;
  /** How many stored references carry this source name. */
  reference_count: number;
}

export interface CompanyDetailResponse {
  company_id: string;
  name: string;
  website: string | null;
  verified: boolean;
  sources: CompanySourceSummary[];
  signals: string[];
}

export interface DimensionExplanation {
  dimension: string;
  status: string;
  weight: number;
  earned_score: number;
  score_contribution: number;
  evidence_status: string;
  unknown_reason: string | null;
  needs_import_evidence: boolean;
  reasons: string[];
}

export interface QualificationExplanation {
  dimensions: DimensionExplanation[];
  evidence_obtained: string[];
  missing_key_evidence: string[];
  import_evidence_missing: string[];
  unreachable_weight: number;
  hard_gate_hits: string[];
  next_action: string | null;
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
  explanation: QualificationExplanation | null;
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
  roles: string[];
  taxonomy_version: string | null;
  score_breakdown: Record<string, number>;
  selection_status: string | null;
  scoring_version: string | null;
  selection_reasons: string[];
}

export interface CandidateScoreResponse {
  contact_id: string;
  original_title: string | null;
  normalized_title: string | null;
  roles: string[];
  overall_score: number;
  score_breakdown: Record<string, number>;
  classification_confidence: number;
  selection_status: string | null;
  selection_reasons: string[];
  rejection_reasons: string[];
}

export interface DecisionMakerSelectionResponse {
  status: string;
  review_required: boolean;
  review_reasons: string[];
  primary_contact: CandidateScoreResponse | null;
  alternative_contacts: CandidateScoreResponse[];
  supporting_contacts: CandidateScoreResponse[];
  rejected_contacts: CandidateScoreResponse[];
  scoring_version: string | null;
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
    selection: DecisionMakerSelectionResponse | null;
  };
  latest_email_draft: EmailDraftDetailResponse | null;
  draft_history: EmailDraftSummaryResponse[];
}

export interface RuntimeStatusResponse {
  provider: "fake" | "openai";
  model: string;
  /** The research extractor, configured independently of the draft provider. */
  research_provider: "fake" | "openai" | "deepseek";
  research_model: string;
  environment: string;
}

export type EvidenceFlowStatus = "completed" | "partial" | "needs_review";

export interface EvidenceUploadResponse {
  status: EvidenceFlowStatus;
  company_id: string;
  import_job_id: string | null;
  aggregate_id: string | null;
  records_received: number;
  records_normalized: number;
  shipments_matched: number;
  quality_status: string | null;
  quality_score: number | null;
  promoted_signals: string[];
  previous_qualification_score: number | null;
  qualification_score: number | null;
  qualification_status: string | null;
  qualification_reasons: string[];
  draft_status: string;
  warnings: string[];
}

export interface EvidenceSender {
  name: string;
  company: string;
  value_proposition: string;
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
  pending_claim_count?: number;
}

export interface ClientErrorDetails {
  code: string;
  message: string;
  request_id: string | null;
  pending_claim_count?: number;
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

async function requestForm<T>(
  path: string,
  form: FormData,
  errorCode = "form_upload_failed",
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_V1_URL}${path}`, {
      method: "POST",
      body: form,
      cache: "no-store",
    });
  } catch {
    throw new ApiNetworkError(
      "Unable to reach the API. Confirm the backend is running on the configured URL.",
    );
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback: ApiErrorPayload = {
      code: errorCode,
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

export function getRuntimeStatus(): Promise<RuntimeStatusResponse> {
  return requestJson<RuntimeStatusResponse>("/health/runtime");
}

export function createDiscoveryTask(prompt: string): Promise<DiscoveryTaskResponse> {
  return requestJson<DiscoveryTaskResponse>("/discovery-tasks", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export function createManualCsvDiscoveryTask(
  prompt: string,
  file: File,
): Promise<DiscoveryTaskResponse> {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("file", file);
  return requestForm<DiscoveryTaskResponse>(
    "/discovery-tasks/manual-csv",
    form,
    "discovery_csv_upload_failed",
  );
}

export function getDiscoveryTask(taskId: string): Promise<DiscoveryTaskResponse> {
  return requestJson<DiscoveryTaskResponse>(
    `/discovery-tasks/${encodeURIComponent(taskId)}`,
  );
}

export function getDiscoveryTaskCompanies(
  taskId: string,
): Promise<DiscoveryCompanyListResponse> {
  return requestJson<DiscoveryCompanyListResponse>(
    `/discovery-tasks/${encodeURIComponent(taskId)}/companies`,
  );
}

export function createProspectBatch(
  taskId: string,
  companyIds: string[],
  sender?: ProspectBatchSender,
  idempotencyKey?: string,
): Promise<ProspectBatchCreateResponse> {
  return requestJson<ProspectBatchCreateResponse>(
    `/discovery-tasks/${encodeURIComponent(taskId)}/batch-process`,
    {
      method: "POST",
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      body: JSON.stringify({ company_ids: companyIds, limit: 5, sender }),
    },
  );
}

export function getProspectBatchExecution(
  batchId: string,
): Promise<ProspectBatchExecutionResponse | null> {
  return requestJson<ProspectBatchExecutionResponse | null>(
    `/prospect-batches/${encodeURIComponent(batchId)}/execution`,
  );
}

export function getProspectBatch(batchId: string): Promise<ProspectBatchResponse> {
  return requestJson<ProspectBatchResponse>(
    `/prospect-batches/${encodeURIComponent(batchId)}`,
  );
}

export function getProspectBatchCompanies(
  batchId: string,
): Promise<ProspectBatchCompanyListResponse> {
  return requestJson<ProspectBatchCompanyListResponse>(
    `/prospect-batches/${encodeURIComponent(batchId)}/companies`,
  );
}

export function retryProspectBatchCompany(
  batchId: string,
  companyId: string,
  sender?: ProspectBatchSender,
): Promise<ProspectBatchCreateResponse> {
  return requestJson<ProspectBatchCreateResponse>(
    `/prospect-batches/${encodeURIComponent(batchId)}/companies/${encodeURIComponent(companyId)}/retry`,
    {
      method: "POST",
      body: JSON.stringify({ sender }),
    },
  );
}

export function getProspectBatchCompanyBlockers(
  batchId: string,
  companyId: string,
): Promise<ProspectCompanyBlockersResponse> {
  return requestJson<ProspectCompanyBlockersResponse>(
    `/prospect-batches/${encodeURIComponent(batchId)}/companies/${encodeURIComponent(companyId)}/blockers`,
  );
}

export function resumeProspectBatchCompany(
  batchId: string,
  companyId: string,
  sender?: ProspectBatchSender,
): Promise<ProspectBatchCreateResponse> {
  return requestJson<ProspectBatchCreateResponse>(
    `/prospect-batches/${encodeURIComponent(batchId)}/companies/${encodeURIComponent(companyId)}/resume`,
    {
      method: "POST",
      body: JSON.stringify({ sender }),
    },
  );
}

export interface DecisionMakerConfirmRequest {
  contact_id: string;
  reviewer_name?: string | null;
  reason?: string | null;
  regenerate_draft?: boolean;
}

export async function confirmDecisionMaker(
  companyId: string,
  confirm: DecisionMakerConfirmRequest,
): Promise<ProspectDetailResponse> {
  return requestJson<ProspectDetailResponse>(
    `/mvp/prospects/${encodeURIComponent(companyId)}/decision-maker/confirm`,
    {
      method: "POST",
      body: JSON.stringify(confirm),
    },
  );
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

export function getImportEvidence(companyId: string): Promise<EvidenceUploadResponse> {
  return requestJson<EvidenceUploadResponse>(
    `/companies/${encodeURIComponent(companyId)}/import-evidence`,
  );
}

export function uploadImportEvidence(
  companyId: string,
  file: File,
  sender?: EvidenceSender,
): Promise<EvidenceUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("provider", "csv");
  if (sender) {
    form.append("sender_name", sender.name);
    form.append("sender_company", sender.company);
    form.append("sender_value_proposition", sender.value_proposition);
  }
  return requestForm<EvidenceUploadResponse>(
    `/companies/${encodeURIComponent(companyId)}/import-evidence/upload`,
    form,
    "import_evidence_upload_failed",
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
