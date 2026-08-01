"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import {
  CheckCircle2,
  ExternalLink,
  FlaskConical,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import {
  senderProfileServerSnapshot,
  senderProfileSnapshot,
  subscribeSenderProfile,
} from "@/features/mvp-analysis/sender-profile";
import type { ProspectSender } from "@/features/mvp-analysis/prospect-state";
import {
  createCalibrationRun,
  createProspectBatch,
  getClientErrorDetails,
  getProspectBatch,
  getProspectBatchCompanyBlockers,
  getProspectBatchCompanies,
  getProspectBatchExecution,
  resumeProspectBatchCompany,
  retryProspectBatchCompany,
  type DiscoveryCompanyResponse,
  type DiscoveryTaskResponse,
  type ProspectBatchCompanyResponse,
  type ProspectBatchCompanyStatus,
  type ProspectBatchExecutionResponse,
  type ProspectBatchResponse,
  type ProspectBatchSender,
  type ProspectCompanyBlockersResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { CalibrationReportPanel } from "./calibration-report-panel";

interface ProspectBatchPanelProps {
  task: DiscoveryTaskResponse;
  companies: DiscoveryCompanyResponse[];
  initialBatchId?: string;
  initialCalibrationId?: string;
}

type BatchFilter = "all" | "completed" | "needs_review" | "failed";

const RETRYABLE_BATCH_ERRORS = new Set([
  "WEBSITE_MISSING",
  "WEBSITE_INVALID",
  "RESEARCH_FAILED",
  "RESEARCH_INCOMPLETE",
  "SCORING_FAILED",
  "SCORING_UNAVAILABLE",
  "CONTACT_DISCOVERY_FAILED",
  "CONTACT_NOT_FOUND",
  "CONTACT_UNUSABLE",
  "DECISION_MAKER_NOT_SELECTED",
  "SENDER_PROFILE_MISSING",
  "DRAFT_GENERATION_FAILED",
  "DRAFT_NOT_GENERATED",
  "PIPELINE_UNEXPECTED_ERROR",
]);

function toBatchSender(stored: ProspectSender | null): ProspectBatchSender | undefined {
  if (
    !stored ||
    !stored.name.trim() ||
    !stored.company.trim() ||
    !stored.valueProposition.trim()
  ) {
    return undefined;
  }
  return {
    name: stored.name,
    company: stored.company,
    value_proposition: stored.valueProposition,
  };
}

function statusTone(status: ProspectBatchCompanyStatus): string {
  if (status === "completed") return "bg-emerald-100 text-emerald-800";
  if (status === "needs_review") return "bg-amber-100 text-amber-800";
  if (status === "failed") return "bg-rose-100 text-rose-800";
  return "bg-sky-100 text-sky-800";
}

async function fetchBlockers(
  batchId: string,
  companies: ProspectBatchCompanyResponse[],
): Promise<Record<string, ProspectCompanyBlockersResponse>> {
  const awaiting = companies.filter(
    (company) =>
      company.current_stage === "awaiting_evidence_review" && company.research_id !== null,
  );
  const loaded = await Promise.all(
    awaiting.map(async (company) => {
      try {
        return [
          company.company_id,
          await getProspectBatchCompanyBlockers(batchId, company.company_id),
        ] as const;
      } catch {
        return null;
      }
    }),
  );
  return Object.fromEntries(loaded.filter((item) => item !== null));
}

export function ProspectBatchPanel({
  task,
  companies,
  initialBatchId,
  initialCalibrationId,
}: ProspectBatchPanelProps) {
  const { t } = useI18n();
  const eligible = useMemo(
    () => companies.filter((company) => company.company_id !== null),
    [companies],
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [batch, setBatch] = useState<ProspectBatchResponse | null>(null);
  const [execution, setExecution] = useState<ProspectBatchExecutionResponse | null>(null);
  const [results, setResults] = useState<ProspectBatchCompanyResponse[]>([]);
  const [filter, setFilter] = useState<BatchFilter>("all");
  const [blockers, setBlockers] = useState<
    Record<string, ProspectCompanyBlockersResponse>
  >({});
  const [busy, setBusy] = useState(Boolean(initialBatchId));
  const [error, setError] = useState<string | null>(null);
  const [creationMessage, setCreationMessage] = useState<string | null>(null);
  const [calibrationId, setCalibrationId] = useState<string | null>(
    initialCalibrationId ?? null,
  );
  const storedSender = useSyncExternalStore(
    subscribeSenderProfile,
    senderProfileSnapshot,
    senderProfileServerSnapshot,
  );

  useEffect(() => {
    if (!initialBatchId) return;
    let active = true;
    async function restore() {
      try {
        const [savedBatch, savedResults, savedExecution] = await Promise.all([
          getProspectBatch(initialBatchId as string),
          getProspectBatchCompanies(initialBatchId as string),
          getProspectBatchExecution(initialBatchId as string),
        ]);
        if (!active) return;
        setBatch(savedBatch);
        setResults(savedResults.companies);
        setExecution(savedExecution);
        setBlockers(await fetchBlockers(initialBatchId as string, savedResults.companies));
      } catch (caught: unknown) {
        if (active) setError(getClientErrorDetails(caught).message);
      } finally {
        if (active) setBusy(false);
      }
    }
    void restore();
    return () => {
      active = false;
    };
  }, [initialBatchId]);

  function persistBatchId(batchId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("batch_id", batchId);
    window.history.replaceState(null, "", currentUrl);
  }

  function persistCalibration(calibration: string, batchId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("batch_id", batchId);
    currentUrl.searchParams.set("calibration_id", calibration);
    window.history.replaceState(null, "", currentUrl);
  }

  function toggleCompany(companyId: string) {
    setSelected((current) => {
      if (current.includes(companyId)) {
        return current.filter((value) => value !== companyId);
      }
      if (current.length >= 5) return current;
      return [...current, companyId];
    });
  }

  const loadResults = useCallback(async (batchId: string) => {
    const [savedBatch, savedResults, savedExecution] = await Promise.all([
      getProspectBatch(batchId),
      getProspectBatchCompanies(batchId),
      getProspectBatchExecution(batchId),
    ]);
    setBatch(savedBatch);
    setResults(savedResults.companies);
    setExecution(savedExecution);
    setBlockers(await fetchBlockers(batchId, savedResults.companies));
  }, []);

  useEffect(() => {
    if (
      !batch ||
      !execution ||
      !["pending", "leased", "running"].includes(execution.status)
    ) {
      return;
    }
    const batchId = batch.batch_id;
    const timer = window.setInterval(() => {
      void loadResults(batchId).catch((caught: unknown) => {
        setError(getClientErrorDetails(caught).message);
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [batch, execution, loadResults]);

  async function startBatch() {
    if (busy || selected.length === 0) return;
    setBusy(true);
    setError(null);
    setCreationMessage(null);
    try {
      const created = await createProspectBatch(
        task.task_id,
        selected,
        toBatchSender(storedSender),
        crypto.randomUUID(),
      );
      persistBatchId(created.batch_id);
      setCreationMessage(
        created.reused ? t("batch.reused") : t("batch.createdBackground"),
      );
      await loadResults(created.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function startCalibration() {
    if (busy || selected.length < 3 || selected.length > 5) return;
    setBusy(true);
    setError(null);
    setCreationMessage(null);
    try {
      const created = await createCalibrationRun(
        task.task_id,
        selected,
        toBatchSender(storedSender),
        crypto.randomUUID(),
      );
      setCalibrationId(created.calibration_id);
      persistCalibration(created.calibration_id, created.batch_id);
      setCreationMessage(
        created.reused ? t("batch.reused") : t("calibration.created"),
      );
      await loadResults(created.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function retryCompany(companyId: string) {
    if (!batch || busy) return;
    setBusy(true);
    setError(null);
    try {
      await retryProspectBatchCompany(
        batch.batch_id,
        companyId,
        toBatchSender(storedSender),
      );
      setCreationMessage(t("batch.createdBackground"));
      await loadResults(batch.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function resumeCompany(companyId: string) {
    if (!batch || busy) return;
    setBusy(true);
    setError(null);
    try {
      await resumeProspectBatchCompany(
        batch.batch_id,
        companyId,
        toBatchSender(storedSender),
      );
      setCreationMessage(t("batch.createdBackground"));
      await loadResults(batch.batch_id);
    } catch (caught: unknown) {
      const details = getClientErrorDetails(caught);
      setError(
        details.code === "EVIDENCE_REVIEW_INCOMPLETE"
          ? t("batch.reviewIncomplete", {
              count:
                details.pending_claim_count ??
                blockers[companyId]?.pending_claim_count ??
                1,
            })
          : details.message,
      );
    } finally {
      setBusy(false);
    }
  }

  const terminalCount = batch
    ? batch.completed_count + batch.needs_review_count + batch.failed_count
    : 0;
  const progress = batch
    ? Math.round((terminalCount / Math.max(1, batch.effective_count)) * 100)
    : 0;
  const visibleResults = results.filter(
    (company) => filter === "all" || company.status === filter,
  );
  const executionActive =
    execution !== null && ["pending", "leased", "running"].includes(execution.status);
  const executionLabel = execution
    ? t(`batch.execution.${execution.status}`)
    : batch
      ? t("batch.execution.legacy")
      : t("batch.execution.pending");
  const lastUpdated = execution?.updated_at ?? batch?.completed_at ?? batch?.started_at;
  const canStart =
    task.provider === "manual_csv" &&
    (task.status === "completed" || task.status === "partial_failed");

  if (!canStart) return null;

  return (
    <div
      className="mt-6 rounded-3xl border border-indigo-200 bg-indigo-50/40 p-4 sm:p-5"
      data-testid="prospect-batch-panel"
      id="prospect-batch-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-700">
            {t("batch.kicker")}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">
            {t("batch.title")}
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
            {t("batch.intro")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-indigo-300 bg-white px-4 text-sm font-semibold text-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="start-prospect-batch"
            disabled={busy || executionActive || selected.length === 0}
            onClick={startBatch}
            type="button"
          >
            <Play className="size-4" />
            {busy || executionActive ? t("batch.running") : t("batch.start")}
          </button>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-violet-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="start-calibration-run"
            disabled={
              busy || executionActive || selected.length < 3 || selected.length > 5
            }
            onClick={startCalibration}
            type="button"
          >
            <FlaskConical className="size-4" /> {t("calibration.start")}
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <button
          className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-medium text-indigo-800"
          data-testid="batch-select-all"
          onClick={() =>
            setSelected(
              eligible
                .map((company) => company.company_id)
                .filter((value): value is string => value !== null)
                .slice(0, 5),
            )
          }
          type="button"
        >
          {t("batch.selectAll")}
        </button>
        <span className="text-slate-600">
          {t("batch.selected", { count: selected.length })}
        </span>
        <span className="font-medium text-amber-700">{t("batch.limit")}</span>
        <span className="font-medium text-violet-700">
          {t("calibration.selectionHint")}
        </span>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {eligible.map((company) => {
          const companyId = company.company_id as string;
          const checked = selected.includes(companyId);
          return (
            <label
              className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 bg-white p-3"
              key={company.candidate_id}
            >
              <input
                checked={checked}
                className="mt-1 size-4 accent-indigo-700"
                data-testid="batch-company-checkbox"
                disabled={!checked && selected.length >= 5}
                onChange={() => toggleCompany(companyId)}
                type="checkbox"
              />
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-slate-900">
                  {company.company_name}
                </span>
                <span className="block truncate text-xs text-slate-500">
                  {company.website ?? t("common.notAvailable")}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      {!toBatchSender(storedSender) ? (
        <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {t("batch.senderMissing")}
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {creationMessage ? (
        <p className="mt-4 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
          {creationMessage}
        </p>
      ) : null}

      {batch ? (
        <div className="mt-6" data-testid="prospect-batch-result">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900">
                {t(`batch.status.${batch.status}`)} · {progress}%
              </p>
              <p className="mt-1 text-xs font-medium text-indigo-700" data-testid="batch-execution-status">
                {executionLabel}
              </p>
              <p className="mt-1 font-mono text-xs text-slate-500">
                {batch.batch_id}
              </p>
            </div>
            <div className="text-xs text-slate-600">
              {t("batch.counts", {
                completed: batch.completed_count,
                review: batch.needs_review_count,
                failed: batch.failed_count,
              })}
              {lastUpdated ? (
                <p className="mt-1 text-right">
                  {t("batch.lastUpdated", {
                    time: new Date(lastUpdated).toLocaleString(),
                  })}
                </p>
              ) : null}
            </div>
          </div>
          {execution?.recovery_count ? (
            <p className="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800">
              {t("batch.recovered")}
            </p>
          ) : null}
          {execution?.status === "failed" ? (
            <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800">
              {t("batch.executionFailed")}
            </p>
          ) : null}
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-indigo-600 transition-[width]"
              data-testid="batch-progress"
              style={{ width: `${progress}%` }}
            />
          </div>
          {batch.requested_count > batch.effective_count ? (
            <p className="mt-2 text-xs text-amber-700">
              {t("batch.capped", {
                requested: batch.requested_count,
                effective: batch.effective_count,
              })}
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-2">
            {(["all", "completed", "needs_review", "failed"] as const).map(
              (value) => (
                <button
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    filter === value
                      ? "bg-slate-900 text-white"
                      : "bg-white text-slate-600"
                  }`}
                  key={value}
                  onClick={() => setFilter(value)}
                  type="button"
                >
                  {t(`batch.filter.${value}`)}
                </button>
              ),
            )}
          </div>

          <div className="mt-4 space-y-3">
            {visibleResults.map((company) => (
              <article
                className="rounded-2xl border border-slate-200 bg-white p-4"
                data-testid={`batch-company-${company.status}`}
                key={company.company_id}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h4 className="font-semibold text-slate-950">
                      {company.company_name}
                    </h4>
                    <p className="mt-1 text-xs text-slate-500">
                      {t(`batch.stage.${company.current_stage}`)}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone(company.status)}`}
                  >
                    {t(`batch.companyStatus.${company.status}`)}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
                  <p>
                    <span className="font-medium text-slate-800">Research：</span>
                    {company.research_id ? t("batch.saved") : t("common.notAvailable")}
                  </p>
                  <p>
                    <span className="font-medium text-slate-800">Score：</span>
                    {company.score ?? t("common.notAvailable")}
                  </p>
                  <p>
                    <span className="font-medium text-slate-800">Contact：</span>
                    {company.contact_name ?? company.contact_email ?? t("common.notAvailable")}
                  </p>
                  <p>
                    <span className="font-medium text-slate-800">Draft：</span>
                    {company.draft_subject ?? t("common.notAvailable")}
                  </p>
                </div>
                {company.error_code ? (
                  <div className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                    <p className="font-mono text-xs">{company.error_code}</p>
                    <p className="mt-1">
                      {company.error_code === "EVIDENCE_REVIEW_REQUIRED"
                        ? t("batch.evidenceRequired")
                        : company.error_summary}
                    </p>
                  </div>
                ) : null}
                {company.current_stage === "awaiting_evidence_review" ? (
                  <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
                    <p className="font-semibold">{t("batch.evidenceRequired")}</p>
                    <p className="mt-1 text-xs">
                      {t("batch.blockingClaims", {
                        count:
                          blockers[company.company_id]?.pending_claim_count ??
                          company.blocking_claim_count,
                      })}
                    </p>
                  </div>
                ) : null}
                {company.status === "completed" ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium">
                    <span className="rounded-full bg-amber-100 px-2.5 py-1 text-amber-900">
                      {t("batch.draftAwaitingReview")}
                    </span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">
                      {t("batch.emailNotSent")}
                    </span>
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-3">
                  <a
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-700"
                    href={`/?company_id=${encodeURIComponent(company.company_id)}`}
                  >
                    {t("batch.openWorkspace")} <ExternalLink className="size-3.5" />
                  </a>
                  {company.contact_source_url ? (
                    <a
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-teal-700"
                      href={company.contact_source_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {t("batch.contactSource")} <ExternalLink className="size-3.5" />
                    </a>
                  ) : null}
                  {company.current_stage === "awaiting_evidence_review" &&
                  company.research_id ? (
                    <>
                      <a
                        className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-800"
                        data-testid="review-batch-evidence"
                        href={`/?${new URLSearchParams({
                          task_id: task.task_id,
                          batch_id: batch.batch_id,
                          company_id: company.company_id,
                          research_id: company.research_id,
                        }).toString()}#research-panel`}
                      >
                        <ShieldCheck className="size-3.5" /> {t("batch.reviewEvidence")}
                      </a>
                      <button
                        className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-800 disabled:opacity-50"
                        data-testid="resume-batch-company"
                        disabled={busy || executionActive}
                        onClick={() => resumeCompany(company.company_id)}
                        type="button"
                      >
                        <CheckCircle2 className="size-3.5" /> {t("batch.resume")}
                      </button>
                    </>
                  ) : null}
                  {(company.status === "failed" ||
                    company.status === "needs_review") &&
                  company.error_code !== null &&
                  RETRYABLE_BATCH_ERRORS.has(company.error_code) ? (
                    <button
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
                      disabled={busy || executionActive}
                      onClick={() => retryCompany(company.company_id)}
                      type="button"
                    >
                      <RefreshCw className="size-3.5" /> {t("batch.retry")}
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
      {calibrationId ? (
        <CalibrationReportPanel
          calibrationId={calibrationId}
          refreshToken={execution?.updated_at ?? batch?.completed_at}
        />
      ) : null}
    </div>
  );
}
