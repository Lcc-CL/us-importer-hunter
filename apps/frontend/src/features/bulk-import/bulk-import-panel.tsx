"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Ban, CheckCircle2, ExternalLink, FileCheck2, GitMerge, Play, RefreshCw, Route, ShieldCheck, Upload } from "lucide-react";

import {
  senderProfileServerSnapshot,
  senderProfileSnapshot,
  subscribeSenderProfile,
} from "@/features/mvp-analysis/sender-profile";
import type { ProspectSender } from "@/features/mvp-analysis/prospect-state";

import {
  createBulkImportSession,
  createProspectRoutingRun,
  createRoutedProspectBatch,
  ApiError,
  getBulkImportRows,
  getBulkImportSession,
  getClientErrorDetails,
  getImportEntityDecisions,
  getImportResolution,
  getProspectRoutes,
  getProspectBatch,
  getProspectBatchCompanies,
  getProspectBatchExecution,
  getProspectRoutingRun,
  resumeProspectBatchCompany,
  retryProspectBatchCompany,
  reviewImportEntityDecision,
  reviewProspectRoute,
  startImportResolution,
  startRoutedProspectBatch,
  type ImportEntityDecisionResponse,
  type ImportResolutionResponse,
  type ImportReviewAction,
  type ImportSessionResponse,
  type ProspectRouteResponse,
  type ProspectBatchCompanyResponse,
  type ProspectBatchExecutionResponse,
  type ProspectBatchResponse,
  type ProspectBatchSender,
  type ProspectRoutingRunResponse,
  type ProspectTier,
  type RawImportRowResponse,
  type RawImportRowStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { UmailExportPanel } from "./umail-export-panel";

const DEFAULT_SOURCE = "netease_foreign_trade";
const PAGE_SIZE = 20;
const ROUTING_RETRYABLE_ERRORS = new Set([
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

interface BulkImportPanelProps {
  initialSessionId?: string;
  initialRoutingRunId?: string;
  initialBatchId?: string;
  initialUmailExportBatchId?: string;
}

export function BulkImportPanel({
  initialSessionId,
  initialRoutingRunId,
  initialBatchId,
  initialUmailExportBatchId,
}: BulkImportPanelProps) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [mappingText, setMappingText] = useState("");
  const [session, setSession] = useState<ImportSessionResponse | null>(null);
  const [rows, setRows] = useState<RawImportRowResponse[]>([]);
  const [rowTotal, setRowTotal] = useState(0);
  const [rowStatus, setRowStatus] = useState<RawImportRowStatus | "">("");
  const [page, setPage] = useState(1);
  const [resolution, setResolution] = useState<ImportResolutionResponse | null>(null);
  const [decisions, setDecisions] = useState<ImportEntityDecisionResponse[]>([]);
  const [resolving, setResolving] = useState(false);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [routingRun, setRoutingRun] = useState<ProspectRoutingRunResponse | null>(null);
  const [routes, setRoutes] = useState<ProspectRouteResponse[]>([]);
  const [productKeywords, setProductKeywords] = useState("");
  const [hsCodes, setHsCodes] = useState("");
  const [originCountries, setOriginCountries] = useState("");
  const [preferredPol, setPreferredPol] = useState("");
  const [preferredPod, setPreferredPod] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [routingBusy, setRoutingBusy] = useState(false);
  const [reviewingRouteId, setReviewingRouteId] = useState<string | null>(null);
  const [routeTiers, setRouteTiers] = useState<Record<string, ProspectTier>>({});
  const [routeReasons, setRouteReasons] = useState<Record<string, string>>({});
  const [selectedACompanies, setSelectedACompanies] = useState<string[]>([]);
  const [createdBatchId, setCreatedBatchId] = useState<string | null>(
    initialRoutingRunId ? (initialBatchId ?? null) : null,
  );
  const [routedBatch, setRoutedBatch] = useState<ProspectBatchResponse | null>(null);
  const [batchExecution, setBatchExecution] =
    useState<ProspectBatchExecutionResponse | null>(null);
  const [batchCompanies, setBatchCompanies] = useState<ProspectBatchCompanyResponse[]>([]);
  const [batchBusy, setBatchBusy] = useState(Boolean(initialRoutingRunId && initialBatchId));
  const [busy, setBusy] = useState(Boolean(initialSessionId));
  const [error, setError] = useState<string | null>(null);
  const storedSender = useSyncExternalStore(
    subscribeSenderProfile,
    senderProfileSnapshot,
    senderProfileServerSnapshot,
  );

  const loadRows = useCallback(
    async (sessionId: string, nextPage: number, status: RawImportRowStatus | "") => {
      const result = await getBulkImportRows(sessionId, {
        page: nextPage,
        limit: PAGE_SIZE,
        status: status || undefined,
      });
      setRows(result.rows);
      setRowTotal(result.total);
    },
    [],
  );

  const restore = useCallback(
    async (sessionId: string, nextPage = 1, status: RawImportRowStatus | "" = "") => {
      const saved = await getBulkImportSession(sessionId);
      setSession(saved);
      await loadRows(sessionId, nextPage, status);
      return saved;
    },
    [loadRows],
  );

  const loadResolutionState = useCallback(
    async (sessionId: string, tolerateMissing = false) => {
      try {
        const saved = await getImportResolution(sessionId);
        setResolution(saved);
        const pending = await getImportEntityDecisions(sessionId, {
          reviewStatus: "pending",
          limit: 100,
        });
        setDecisions(pending.decisions);
        return saved;
      } catch (caught: unknown) {
        if (tolerateMissing && caught instanceof ApiError && caught.status === 404) {
          setResolution(null);
          setDecisions([]);
          return null;
        }
        throw caught;
      }
    },
    [],
  );

  const loadRoutingState = useCallback(async (routingRunId: string) => {
    const saved = await getProspectRoutingRun(routingRunId);
    setRoutingRun(saved);
    setProductKeywords(stringList(saved.criteria.target_product_keywords).join(", "));
    setHsCodes(stringList(saved.criteria.target_hs_codes).join(", "));
    setOriginCountries(stringList(saved.criteria.preferred_origin_countries).join(", "));
    setPreferredPol(stringList(saved.criteria.preferred_pol).join(", "));
    setPreferredPod(stringList(saved.criteria.preferred_pod).join(", "));
    setCampaignName(
      typeof saved.criteria.campaign_name === "string"
        ? saved.criteria.campaign_name
        : "",
    );
    if (["completed", "partial_completed"].includes(saved.status)) {
      const page = await getProspectRoutes(routingRunId);
      setRoutes(page.routes);
      const eligible = new Set(
        page.routes
          .filter(
            (route) =>
              route.effective_tier === "A" &&
              ["confirmed", "overridden"].includes(route.review_status),
          )
          .map((route) => route.company_id),
      );
      setSelectedACompanies((current) => current.filter((value) => eligible.has(value)));
      setRouteTiers((current) => {
        const next = { ...current };
        for (const route of page.routes) {
          if (route.effective_tier) next[route.route_id] = route.effective_tier;
        }
        return next;
      });
    }
    return saved;
  }, []);

  const loadRoutedBatchState = useCallback(async (batchId: string) => {
    const [savedBatch, savedCompanies, savedExecution] = await Promise.all([
      getProspectBatch(batchId),
      getProspectBatchCompanies(batchId),
      getProspectBatchExecution(batchId),
    ]);
    if (savedBatch.source_kind !== "prospect_routing") {
      throw new Error("batch is not sourced from sales routing");
    }
    setCreatedBatchId(batchId);
    setRoutedBatch(savedBatch);
    setBatchCompanies(savedCompanies.companies);
    setBatchExecution(savedExecution);
    return savedExecution;
  }, []);

  useEffect(() => {
    if (!initialSessionId) return;
    let active = true;
    async function load() {
      try {
        await restore(initialSessionId as string);
        await loadResolutionState(initialSessionId as string, true);
        if (initialRoutingRunId) {
          await loadRoutingState(initialRoutingRunId);
          if (initialBatchId) {
            await loadRoutedBatchState(initialBatchId);
          }
        }
      } catch (caught: unknown) {
        if (active) setError(getClientErrorDetails(caught).message);
      } finally {
        if (active) {
          setBusy(false);
          setBatchBusy(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [
    initialBatchId,
    initialRoutingRunId,
    initialSessionId,
    loadResolutionState,
    loadRoutedBatchState,
    loadRoutingState,
    restore,
  ]);

  useEffect(() => {
    if (!session || !["receiving", "processing"].includes(session.status)) return;
    const timer = window.setInterval(() => {
      void restore(session.session_id, page, rowStatus).catch((caught: unknown) => {
        setError(getClientErrorDetails(caught).message);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [page, restore, rowStatus, session]);

  useEffect(() => {
    if (!session || !resolution) return;
    if (!resolution.processing_status || !["pending", "leased", "running"].includes(resolution.processing_status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadResolutionState(session.session_id).catch((caught: unknown) => {
        setError(getClientErrorDetails(caught).message);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [loadResolutionState, resolution, session]);

  useEffect(() => {
    if (
      !routingRun?.processing_status ||
      !["pending", "leased", "running"].includes(routingRun.processing_status)
    ) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadRoutingState(routingRun.routing_run_id).catch((caught: unknown) => {
        setError(getClientErrorDetails(caught).message);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [loadRoutingState, routingRun]);

  useEffect(() => {
    if (
      !createdBatchId ||
      !batchExecution ||
      !["pending", "leased", "running"].includes(batchExecution.status)
    ) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadRoutedBatchState(createdBatchId).catch((caught: unknown) => {
        setError(getClientErrorDetails(caught).message);
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [batchExecution, createdBatchId, loadRoutedBatchState]);

  function persistSessionId(sessionId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("import_session_id", sessionId);
    currentUrl.searchParams.delete("routing_run_id");
    currentUrl.searchParams.delete("batch_id");
    currentUrl.searchParams.delete("umail_export_batch_id");
    window.history.replaceState(null, "", currentUrl);
  }

  function persistRoutingRunId(routingRunId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("routing_run_id", routingRunId);
    currentUrl.searchParams.delete("batch_id");
    currentUrl.searchParams.delete("umail_export_batch_id");
    window.history.replaceState(null, "", currentUrl);
  }

  function persistBatchExecution(batchId: string, jobId?: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("batch_id", batchId);
    if (jobId) currentUrl.searchParams.set("job_id", jobId);
    window.history.replaceState(null, "", currentUrl);
  }

  async function handleUpload() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    let mapping: Record<string, string> | undefined;
    if (mappingText.trim()) {
      try {
        const decoded: unknown = JSON.parse(mappingText);
        if (
          typeof decoded !== "object" ||
          decoded === null ||
          Array.isArray(decoded) ||
          !Object.entries(decoded).every(
            ([key, value]) => key.trim() && typeof value === "string" && value.trim(),
          )
        ) {
          throw new Error("invalid mapping");
        }
        mapping = decoded as Record<string, string>;
      } catch {
        setError(t("bulk.mappingInvalid"));
        setBusy(false);
        return;
      }
    }
    try {
      const created = await createBulkImportSession(file, DEFAULT_SOURCE, mapping);
      setSession(created);
      setPage(1);
      setRowStatus("");
      setResolution(null);
      setDecisions([]);
      setRoutingRun(null);
      setRoutes([]);
      setSelectedACompanies([]);
      setCreatedBatchId(null);
      setRoutedBatch(null);
      setBatchCompanies([]);
      setBatchExecution(null);
      persistSessionId(created.session_id);
      await loadRows(created.session_id, 1, "");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStartResolution() {
    if (!session || resolving) return;
    setResolving(true);
    setError(null);
    try {
      await startImportResolution(session.session_id);
      await loadResolutionState(session.session_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setResolving(false);
    }
  }

  async function handleReview(decisionId: string, action: ImportReviewAction) {
    if (!session || reviewingId) return;
    setReviewingId(decisionId);
    setError(null);
    try {
      await reviewImportEntityDecision(decisionId, action);
      await loadResolutionState(session.session_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setReviewingId(null);
    }
  }

  async function handleStartRouting() {
    if (!session || routingBusy) return;
    const products = splitList(productKeywords);
    const hs = splitList(hsCodes);
    if (!products.length && !hs.length) {
      setError(t("bulk.routingTargetRequired"));
      return;
    }
    setRoutingBusy(true);
    setError(null);
    setCreatedBatchId(null);
    setRoutedBatch(null);
    setBatchCompanies([]);
    setBatchExecution(null);
    try {
      const created = await createProspectRoutingRun(
        session.session_id,
        {
          target_product_keywords: products,
          target_hs_codes: hs,
          preferred_origin_countries: splitList(originCountries),
          preferred_pol: splitList(preferredPol),
          preferred_pod: splitList(preferredPod),
        },
        campaignName,
      );
      persistRoutingRunId(created.routing_run_id);
      setSelectedACompanies([]);
      await loadRoutingState(created.routing_run_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setRoutingBusy(false);
    }
  }

  async function handleRouteReview(
    route: ProspectRouteResponse,
    action: "confirm" | "override" | "exclude",
  ) {
    if (reviewingRouteId) return;
    const reason = routeReasons[route.route_id]?.trim();
    if (action !== "confirm" && !reason) {
      setError(t("bulk.routingReasonRequired"));
      return;
    }
    setReviewingRouteId(route.route_id);
    setError(null);
    try {
      await reviewProspectRoute(route.route_id, action, {
        effectiveTier:
          action === "override"
            ? (routeTiers[route.route_id] ?? route.effective_tier ?? "C")
            : undefined,
        overrideReason: reason,
      });
      if (routingRun) await loadRoutingState(routingRun.routing_run_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setReviewingRouteId(null);
    }
  }

  function toggleACompany(companyId: string) {
    setSelectedACompanies((current) => {
      if (current.includes(companyId)) return current.filter((value) => value !== companyId);
      if (current.length >= 5) return current;
      return [...current, companyId];
    });
  }

  async function handleCreateRoutingBatch() {
    if (!routingRun || routingBusy || !selectedACompanies.length) return;
    setRoutingBusy(true);
    setError(null);
    try {
      const created = await createRoutedProspectBatch(
        routingRun.routing_run_id,
        selectedACompanies,
      );
      setCreatedBatchId(created.batch_id);
      persistBatchExecution(created.batch_id);
      await loadRoutedBatchState(created.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setRoutingBusy(false);
    }
  }

  async function handleStartRoutedBatch() {
    if (!createdBatchId || batchBusy) return;
    if (!window.confirm(t("bulk.routingBatchStartConfirmation"))) return;
    setBatchBusy(true);
    setError(null);
    try {
      const started = await startRoutedProspectBatch(createdBatchId, {
        confirmation: true,
        sender: toBatchSender(storedSender),
      });
      persistBatchExecution(started.batch_id, started.job_id);
      await loadRoutedBatchState(started.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBatchBusy(false);
    }
  }

  async function handleResumeRoutedCompany(companyId: string) {
    if (!createdBatchId || batchBusy) return;
    setBatchBusy(true);
    setError(null);
    try {
      const resumed = await resumeProspectBatchCompany(
        createdBatchId,
        companyId,
        toBatchSender(storedSender),
      );
      persistBatchExecution(resumed.batch_id, resumed.job_id);
      await loadRoutedBatchState(resumed.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBatchBusy(false);
    }
  }

  async function handleRetryRoutedCompany(companyId: string) {
    if (!createdBatchId || batchBusy) return;
    setBatchBusy(true);
    setError(null);
    try {
      const retried = await retryProspectBatchCompany(
        createdBatchId,
        companyId,
        toBatchSender(storedSender),
      );
      persistBatchExecution(retried.batch_id, retried.job_id);
      await loadRoutedBatchState(retried.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBatchBusy(false);
    }
  }

  async function changeFilter(status: RawImportRowStatus | "") {
    setRowStatus(status);
    setPage(1);
    if (session) {
      setBusy(true);
      try {
        await loadRows(session.session_id, 1, status);
      } catch (caught: unknown) {
        setError(getClientErrorDetails(caught).message);
      } finally {
        setBusy(false);
      }
    }
  }

  async function changePage(nextPage: number) {
    if (!session || nextPage < 1) return;
    setBusy(true);
    try {
      await loadRows(session.session_id, nextPage, rowStatus);
      setPage(nextPage);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  const pageCount = Math.max(1, Math.ceil(rowTotal / PAGE_SIZE));
  const selectableACompanyIds = new Set(
    routes
      .filter(
        (route) =>
          route.effective_tier === "A" &&
          ["confirmed", "overridden"].includes(route.review_status),
      )
      .map((route) => route.company_id),
  );
  const routedBatchStatus = getRoutedBatchStatus(
    routedBatch,
    batchExecution,
    batchCompanies,
  );
  const batchExecutionActive = Boolean(
    batchExecution && ["pending", "leased", "running"].includes(batchExecution.status),
  );
  const draftCount = batchCompanies.filter((company) => company.draft_id !== null).length;

  return (
    <section
      className="mb-8 overflow-hidden rounded-3xl border border-indigo-200 bg-white shadow-sm"
      data-testid="bulk-import-panel"
    >
      <div className="border-b border-indigo-100 bg-indigo-50/70 px-5 py-5 sm:px-7">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-700">
          {t("bulk.kicker")}
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
          {t("bulk.title")}
        </h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          {t("bulk.intro")}
        </p>
      </div>

      <div className="grid gap-4 p-5 sm:p-7 lg:grid-cols-2">
        <label className="block text-sm font-medium text-slate-800">
          {t("bulk.file")}
          <input
            accept=".csv,text/csv"
            className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-100 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-indigo-900"
            data-testid="bulk-import-file"
            disabled={busy}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        <label className="block text-sm font-medium text-slate-800">
          {t("bulk.source")}
          <input
            className="mt-2 block w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-600"
            disabled
            value={DEFAULT_SOURCE}
          />
        </label>
        <label className="block text-sm font-medium text-slate-800 lg:col-span-2">
          {t("bulk.mapping")}
          <textarea
            className="mt-2 min-h-24 w-full rounded-xl border border-slate-300 px-3 py-2 font-mono text-xs leading-5 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
            data-testid="bulk-import-mapping"
            disabled={busy}
            onChange={(event) => setMappingText(event.target.value)}
            placeholder={'{"company_name":"公司名称","contact_email":"邮箱"}'}
            value={mappingText}
          />
        </label>
        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          <button
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-indigo-700 px-5 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="bulk-import-upload"
            disabled={busy || !file}
            onClick={handleUpload}
            type="button"
          >
            <Upload className="size-4" />
            {busy ? t("bulk.processing") : t("bulk.upload")}
          </button>
          <span className="text-xs text-slate-500">{t("bulk.limits")}</span>
        </div>
      </div>

      <p className="mx-5 mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900 sm:mx-7">
        {t("bulk.boundary")}
      </p>

      {error ? (
        <p className="mx-5 mb-6 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 sm:mx-7">
          {error}
        </p>
      ) : null}

      {session ? (
        <div className="border-t border-slate-200 px-5 py-6 sm:px-7" data-testid="bulk-import-result">
          <div className="flex flex-wrap items-center gap-3">
            <FileCheck2 className="size-5 text-indigo-700" />
            <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-800">
              {t(`bulk.status.${session.status}`)}
            </span>
            <span className="font-mono text-xs text-slate-500">{session.session_id}</span>
            <span className="text-xs text-slate-500">
              {session.encoding} · {(session.file_size_bytes / 1024).toFixed(1)} KB
            </span>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              [t("bulk.total"), session.total_rows],
              [t("bulk.accepted"), session.accepted_rows],
              [t("bulk.invalid"), session.invalid_rows],
              [t("bulk.duplicate"), session.duplicate_rows],
            ].map(([label, value]) => (
              <div className="rounded-2xl bg-slate-50 p-3" key={String(label)}>
                <p className="text-xs text-slate-500">{label}</p>
                <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
              </div>
            ))}
          </div>

          <div
            className="mt-6 rounded-2xl border border-cyan-200 bg-cyan-50/60 p-4"
            data-testid="import-resolution-panel"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-800">
                  {t("bulk.resolutionKicker")}
                </p>
                <h3 className="mt-1 text-base font-semibold text-slate-950">
                  {t("bulk.resolutionTitle")}
                </h3>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  {t("bulk.resolutionIntro")}
                </p>
              </div>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-cyan-800 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="import-resolution-start"
                disabled={
                  resolving ||
                  !["completed", "partial_failed"].includes(session.status) ||
                  Boolean(
                    resolution?.processing_status &&
                      ["pending", "leased", "running"].includes(
                        resolution.processing_status,
                      ),
                  ) ||
                  ["completed", "partial_failed"].includes(
                    resolution?.resolution_status ?? "",
                  )
                }
                onClick={() => void handleStartResolution()}
                type="button"
              >
                {resolution ? <GitMerge className="size-4" /> : <Play className="size-4" />}
                {resolving ? t("bulk.resolutionStarting") : t("bulk.resolutionStart")}
              </button>
            </div>

            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              {t("bulk.resolutionBoundary")}
            </p>

            {resolution ? (
              <div className="mt-4" data-testid="import-resolution-result">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                  <span className="rounded-full bg-cyan-100 px-3 py-1 font-semibold text-cyan-900">
                    {t(`bulk.resolutionStatus.${resolution.resolution_status}`)}
                  </span>
                  <span>
                    {t("bulk.resolutionProgress", {
                      processed: resolution.processed_rows,
                      total: resolution.total_rows,
                    })}
                  </span>
                  <span>
                    {t("bulk.resolutionAttempts", {
                      attempts: resolution.attempt_count,
                      max: resolution.max_attempts,
                    })}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                  {[
                    [t("bulk.companiesCreated"), resolution.companies_created],
                    [t("bulk.companiesReused"), resolution.companies_reused],
                    [t("bulk.companyReviews"), resolution.company_reviews_required],
                    [t("bulk.contactsCreated"), resolution.contacts_created],
                    [t("bulk.contactsReused"), resolution.contacts_reused],
                    [t("bulk.companyContacts"), resolution.company_contacts_created],
                    [t("bulk.failedRows"), resolution.failed_rows],
                  ].map(([label, value]) => (
                    <div className="rounded-xl bg-white p-3" key={String(label)}>
                      <p className="text-[11px] leading-4 text-slate-500">{label}</p>
                      <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="mt-4">
                  <div className="flex items-center justify-between gap-3">
                    <h4 className="text-sm font-semibold text-slate-900">
                      {t("bulk.pendingReviews")}
                    </h4>
                    <span className="text-xs text-slate-500">{decisions.length}</span>
                  </div>
                  {decisions.length ? (
                    <div className="mt-2 space-y-2" data-testid="import-resolution-reviews">
                      {decisions.map((decision) => (
                        <div
                          className="rounded-xl border border-slate-200 bg-white p-3"
                          key={decision.decision_id}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="text-sm text-slate-800">
                              <span className="font-semibold">
                                {decision.entity_type === "company"
                                  ? t("bulk.entityCompany")
                                  : t("bulk.entityContact")}
                              </span>
                              <span className="ml-2 text-xs text-slate-500">
                                #{decision.row_number ?? "—"} · {decision.candidate_label ?? "—"}
                              </span>
                            </div>
                            <span className="text-xs text-slate-500">
                              {(decision.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-slate-600">
                            {decision.reason_codes.join(" · ")}
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {(
                              [
                                ["merge", t("bulk.reviewMerge")],
                                ["keep_separate", t("bulk.reviewSeparate")],
                                ["reject", t("bulk.reviewReject")],
                              ] as const
                            ).map(([action, label]) => (
                              <button
                                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-40"
                                disabled={Boolean(reviewingId)}
                                key={action}
                                onClick={() => void handleReview(decision.decision_id, action)}
                                type="button"
                              >
                                {reviewingId === decision.decision_id
                                  ? t("bulk.reviewing")
                                  : label}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-slate-500">{t("bulk.noPendingReviews")}</p>
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <div
            className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4"
            data-testid="prospect-routing-panel"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-800">
                  {t("bulk.routingKicker")}
                </p>
                <h3 className="mt-1 text-base font-semibold text-slate-950">
                  {t("bulk.routingTitle")}
                </h3>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  {t("bulk.routingIntro")}
                </p>
              </div>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="prospect-routing-start"
                disabled={
                  routingBusy ||
                  !resolution ||
                  !["completed", "partial_failed"].includes(resolution.resolution_status) ||
                  Boolean(
                    routingRun?.processing_status &&
                      ["pending", "leased", "running"].includes(
                        routingRun.processing_status,
                      ),
                  )
                }
                onClick={() => void handleStartRouting()}
                type="button"
              >
                <Route className="size-4" />
                {routingBusy ? t("bulk.routingStarting") : t("bulk.routingStart")}
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[
                [
                  t("bulk.routingProducts"),
                  productKeywords,
                  setProductKeywords,
                  "hardware, tools",
                  "prospect-routing-products",
                ],
                [
                  t("bulk.routingHsCodes"),
                  hsCodes,
                  setHsCodes,
                  "8205, 7318",
                  "prospect-routing-hs",
                ],
                [
                  t("bulk.routingOrigins"),
                  originCountries,
                  setOriginCountries,
                  "China, Vietnam",
                  "prospect-routing-origins",
                ],
                [
                  t("bulk.routingPol"),
                  preferredPol,
                  setPreferredPol,
                  "Shanghai",
                  "prospect-routing-pol",
                ],
                [
                  t("bulk.routingPod"),
                  preferredPod,
                  setPreferredPod,
                  "Los Angeles",
                  "prospect-routing-pod",
                ],
                [
                  t("bulk.routingCampaign"),
                  campaignName,
                  setCampaignName,
                  t("bulk.routingCampaignPlaceholder"),
                  "prospect-routing-campaign",
                ],
              ].map(([label, value, setter, placeholder, testId]) => (
                <label className="text-xs font-medium text-slate-700" key={String(testId)}>
                  {String(label)}
                  <input
                    className="mt-1 block w-full rounded-xl border border-emerald-200 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-500"
                    data-testid={String(testId)}
                    onChange={(event) =>
                      (setter as (next: string) => void)(event.target.value)
                    }
                    placeholder={String(placeholder)}
                    value={String(value)}
                  />
                </label>
              ))}
            </div>

            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              {t("bulk.routingBoundary")}
            </p>

            {routingRun ? (
              <div className="mt-4" data-testid="prospect-routing-result">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                  <span className="rounded-full bg-emerald-100 px-3 py-1 font-semibold text-emerald-900">
                    {t(`bulk.routingStatus.${routingRun.status}`)}
                  </span>
                  <span>{routingRun.rules_version}</span>
                  <span>
                    {t("bulk.routingAttempts", {
                      attempts: routingRun.attempt_count,
                      max: routingRun.max_attempts,
                    })}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
                  {[
                    ["A", routingRun.tier_a_count],
                    ["B", routingRun.tier_b_count],
                    ["C", routingRun.tier_c_count],
                    ["D", routingRun.tier_d_count],
                    [t("bulk.routingBlocked"), routingRun.blocked_companies],
                    [t("bulk.routingTotal"), routingRun.total_companies],
                  ].map(([label, value]) => (
                    <div className="rounded-xl bg-white p-3" key={String(label)}>
                      <p className="text-[11px] text-slate-500">{label}</p>
                      <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
                    </div>
                  ))}
                </div>

                {routes.length ? (
                  <div
                    className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white"
                    data-testid="prospect-routing-routes"
                  >
                    <table className="min-w-[1100px] divide-y divide-slate-200 text-left text-xs">
                      <thead className="bg-slate-50 text-slate-600">
                        <tr>
                          <th className="px-3 py-2">{t("bulk.routingSelect")}</th>
                          <th className="px-3 py-2">{t("bulk.routingCompany")}</th>
                          <th className="px-3 py-2">{t("bulk.routingScoreTier")}</th>
                          <th className="px-3 py-2">{t("bulk.routingContacts")}</th>
                          <th className="px-3 py-2">{t("bulk.routingReasons")}</th>
                          <th className="px-3 py-2">{t("bulk.routingReview")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {routes.map((route) => {
                          const selectable = selectableACompanyIds.has(route.company_id);
                          return (
                            <tr key={route.route_id}>
                              <td className="px-3 py-3 align-top">
                                <input
                                  aria-label={`${t("bulk.routingSelect")} ${route.company_name}`}
                                  checked={selectedACompanies.includes(route.company_id)}
                                  disabled={!selectable}
                                  onChange={() => toggleACompany(route.company_id)}
                                  type="checkbox"
                                />
                              </td>
                              <td className="px-3 py-3 align-top">
                                <p className="font-semibold text-slate-900">
                                  {route.company_name}
                                </p>
                                <p className="mt-1 font-mono text-[10px] text-slate-400">
                                  {route.company_id}
                                </p>
                              </td>
                              <td className="px-3 py-3 align-top">
                                <p className="text-lg font-semibold text-slate-950">
                                  {route.pre_score.toFixed(1)}
                                </p>
                                <p className="mt-1 text-slate-600">
                                  {route.recommended_tier ?? "blocked"} → {route.effective_tier ?? "—"}
                                </p>
                              </td>
                              <td className="px-3 py-3 align-top text-slate-600">
                                <p>{t("bulk.routingContactCount", { count: route.contact_count })}</p>
                                <p>{route.preferred_role_category ?? "—"}</p>
                                <p>{route.has_usable_email ? t("bulk.routingHasEmail") : t("bulk.routingNoEmail")}</p>
                              </td>
                              <td className="max-w-sm px-3 py-3 align-top text-slate-600">
                                <p>{route.reason_codes.join(" · ")}</p>
                                {route.warning_codes.length ? (
                                  <p className="mt-1 text-amber-700">
                                    {route.warning_codes.join(" · ")}
                                  </p>
                                ) : null}
                              </td>
                              <td className="min-w-72 px-3 py-3 align-top">
                                {route.review_status === "suggested" ? (
                                  <div className="space-y-2">
                                    <div className="flex gap-2">
                                      <button
                                        className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 px-2 py-1 font-semibold text-emerald-800 disabled:opacity-40"
                                        disabled={Boolean(reviewingRouteId)}
                                        onClick={() => void handleRouteReview(route, "confirm")}
                                        type="button"
                                      >
                                        <CheckCircle2 className="size-3" />
                                        {t("bulk.routingConfirm")}
                                      </button>
                                      <select
                                        className="rounded-lg border border-slate-300 px-2 py-1"
                                        onChange={(event) =>
                                          setRouteTiers((current) => ({
                                            ...current,
                                            [route.route_id]: event.target.value as ProspectTier,
                                          }))
                                        }
                                        value={routeTiers[route.route_id] ?? route.effective_tier ?? "C"}
                                      >
                                        {(["A", "B", "C", "D"] as const).map((tier) => (
                                          <option key={tier} value={tier}>{tier}</option>
                                        ))}
                                      </select>
                                    </div>
                                    <input
                                      className="block w-full rounded-lg border border-slate-300 px-2 py-1.5"
                                      onChange={(event) =>
                                        setRouteReasons((current) => ({
                                          ...current,
                                          [route.route_id]: event.target.value,
                                        }))
                                      }
                                      placeholder={t("bulk.routingReasonPlaceholder")}
                                      value={routeReasons[route.route_id] ?? ""}
                                    />
                                    <div className="flex gap-2">
                                      <button
                                        className="rounded-lg border border-slate-300 px-2 py-1 font-semibold text-slate-700 disabled:opacity-40"
                                        disabled={Boolean(reviewingRouteId)}
                                        onClick={() => void handleRouteReview(route, "override")}
                                        type="button"
                                      >
                                        {t("bulk.routingOverride")}
                                      </button>
                                      <button
                                        className="inline-flex items-center gap-1 rounded-lg border border-rose-300 px-2 py-1 font-semibold text-rose-700 disabled:opacity-40"
                                        disabled={Boolean(reviewingRouteId)}
                                        onClick={() => void handleRouteReview(route, "exclude")}
                                        type="button"
                                      >
                                        <Ban className="size-3" />
                                        {t("bulk.routingExclude")}
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div>
                                    <p className="font-semibold text-slate-800">
                                      {t(`bulk.routingReviewStatus.${route.review_status}`)}
                                    </p>
                                    <p className="mt-1 text-slate-500">
                                      {route.override_reason ?? route.reviewed_by ?? "—"}
                                    </p>
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}

                <UmailExportPanel
                  campaign={campaignName}
                  initialBatchId={initialUmailExportBatchId}
                  key={routingRun.routing_run_id}
                  routes={routes}
                  routingRunId={routingRun.routing_run_id}
                />

                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button
                    className="rounded-xl bg-emerald-800 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="prospect-routing-create-batch"
                    disabled={
                      routingBusy ||
                      selectedACompanies.length === 0 ||
                      selectedACompanies.length > 5
                    }
                    onClick={() => void handleCreateRoutingBatch()}
                    type="button"
                  >
                    {t("bulk.routingCreateBatch", { count: selectedACompanies.length })}
                  </button>
                  <span className="text-xs text-slate-500">
                    {t("bulk.routingBatchLimit")}
                  </span>
                </div>
                {createdBatchId && routedBatch ? (
                  <div
                    className="mt-4 rounded-2xl border border-emerald-200 bg-white p-4"
                    data-testid="prospect-routing-batch-created"
                    id="prospect-routing-batch"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-800">
                          {t("bulk.routingBatchSource")} · generation {routedBatch.routing_execution_generation}
                        </p>
                        <p className="mt-1 font-mono text-xs text-slate-500">
                          {createdBatchId}
                        </p>
                        <p className="mt-2 text-sm font-semibold text-slate-900" data-testid="prospect-routing-batch-status">
                          {t(`bulk.routingBatchStatus.${routedBatchStatus}`)}
                        </p>
                      </div>
                      <button
                        className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="prospect-routing-batch-start"
                        disabled={batchBusy || Boolean(batchExecution)}
                        onClick={() => void handleStartRoutedBatch()}
                        type="button"
                      >
                        <Play className="size-4" />
                        {batchBusy || batchExecutionActive
                          ? t("bulk.routingBatchStarting")
                          : t("bulk.routingBatchStart")}
                      </button>
                    </div>

                    <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
                      {t("bulk.routingBatchStartWarning")}
                    </p>
                    {!toBatchSender(storedSender) ? (
                      <p className="mt-2 text-xs text-amber-800">
                        {t("batch.senderMissing")}
                      </p>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium">
                      <span className="rounded-full bg-sky-100 px-2.5 py-1 text-sky-800">
                        {batchExecution
                          ? t("bulk.routingBatchStarted")
                          : t("bulk.routingBatchCreatedOnly")}
                      </span>
                      <span className="rounded-full bg-amber-100 px-2.5 py-1 text-amber-900">
                        {t("bulk.routingBatchDraftCount", { count: draftCount })}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">
                        {t("batch.emailNotSent")}
                      </span>
                    </div>

                    <div className="mt-4 space-y-3" data-testid="prospect-routing-batch-companies">
                      {batchCompanies.map((company) => (
                        <article
                          className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                          key={company.company_id}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <p className="font-semibold text-slate-900">
                                {company.company_name}
                              </p>
                              <p className="mt-1 text-xs text-slate-500">
                                {t(`batch.stage.${company.current_stage}`)}
                              </p>
                            </div>
                            <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-700">
                              {t(`batch.companyStatus.${company.status}`)}
                            </span>
                          </div>
                          {company.error_code ? (
                            <p className="mt-2 text-xs text-amber-800">
                              {company.error_code} · {company.error_summary}
                            </p>
                          ) : null}
                          <div className="mt-3 flex flex-wrap gap-3">
                            <a
                              className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700"
                              href={`/?${new URLSearchParams({
                                company_id: company.company_id,
                                batch_id: createdBatchId,
                                ...(session ? { import_session_id: session.session_id } : {}),
                                ...(routingRun ? { routing_run_id: routingRun.routing_run_id } : {}),
                              }).toString()}`}
                            >
                              {t("batch.openWorkspace")} <ExternalLink className="size-3" />
                            </a>
                            {company.current_stage === "awaiting_evidence_review" && company.research_id ? (
                              <>
                                <a
                                  className="inline-flex items-center gap-1 text-xs font-semibold text-amber-800"
                                  data-testid="review-routing-batch-evidence"
                                  href={`/?${new URLSearchParams({
                                    batch_id: createdBatchId,
                                    company_id: company.company_id,
                                    research_id: company.research_id,
                                    ...(session ? { import_session_id: session.session_id } : {}),
                                    ...(routingRun ? { routing_run_id: routingRun.routing_run_id } : {}),
                                  }).toString()}#research-panel`}
                                >
                                  <ShieldCheck className="size-3" /> {t("batch.reviewEvidence")}
                                </a>
                                <button
                                  className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 disabled:opacity-50"
                                  data-testid="resume-routing-batch-company"
                                  disabled={batchBusy || batchExecutionActive}
                                  onClick={() => void handleResumeRoutedCompany(company.company_id)}
                                  type="button"
                                >
                                  <CheckCircle2 className="size-3" /> {t("batch.resume")}
                                </button>
                              </>
                            ) : null}
                            {company.error_code && ROUTING_RETRYABLE_ERRORS.has(company.error_code) ? (
                              <button
                                className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 disabled:opacity-50"
                                disabled={batchBusy || batchExecutionActive}
                                onClick={() => void handleRetryRoutedCompany(company.company_id)}
                                type="button"
                              >
                                <RefreshCw className="size-3" /> {t("batch.retry")}
                              </button>
                            ) : null}
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <label className="text-sm font-medium text-slate-700">
              {t("bulk.rowFilter")}
              <select
                className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                data-testid="bulk-import-status-filter"
                onChange={(event) =>
                  void changeFilter(event.target.value as RawImportRowStatus | "")
                }
                value={rowStatus}
              >
                <option value="">{t("bulk.filterAll")}</option>
                <option value="accepted">{t("bulk.accepted")}</option>
                <option value="invalid">{t("bulk.invalid")}</option>
                <option value="duplicate">{t("bulk.duplicate")}</option>
              </select>
            </label>
            <span className="text-xs text-slate-500">
              {t("bulk.page", { page, pages: pageCount, total: rowTotal })}
            </span>
          </div>

          <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-3 py-2">{t("bulk.rowNumber")}</th>
                  <th className="px-3 py-2">{t("bulk.rowStatus")}</th>
                  <th className="px-3 py-2">{t("bulk.errors")}</th>
                  <th className="px-3 py-2">{t("bulk.payload")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white" data-testid="bulk-import-rows">
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="px-3 py-3 font-mono text-slate-500">{row.row_number}</td>
                    <td className="px-3 py-3 font-semibold text-slate-700">{row.status}</td>
                    <td className="px-3 py-3 text-rose-700">
                      {row.error_codes.join(", ") || "—"}
                    </td>
                    <td className="max-w-2xl px-3 py-3 font-mono text-slate-600">
                      <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-all">
                        {JSON.stringify(row.raw_payload, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              disabled={busy || page <= 1}
              onClick={() => void changePage(page - 1)}
              type="button"
            >
              {t("bulk.previous")}
            </button>
            <button
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40"
              disabled={busy || page >= pageCount}
              onClick={() => void changePage(page + 1)}
              type="button"
            >
              {t("bulk.next")}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function splitList(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[,;|\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

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

function getRoutedBatchStatus(
  batch: ProspectBatchResponse | null,
  execution: ProspectBatchExecutionResponse | null,
  companies: ProspectBatchCompanyResponse[],
):
  | "not_started"
  | "queued"
  | "running"
  | "awaiting_evidence_review"
  | "needs_review"
  | "completed"
  | "partial_failed"
  | "failed" {
  if (!execution) return "not_started";
  if (execution.status === "pending") return "queued";
  if (["leased", "running"].includes(execution.status)) return "running";
  if (
    companies.some(
      (company) => company.current_stage === "awaiting_evidence_review",
    )
  ) {
    return "awaiting_evidence_review";
  }
  if (execution.status === "failed" || batch?.status === "failed") return "failed";
  if (batch?.status === "completed") return "completed";
  if (batch?.status === "partial_failed") return "partial_failed";
  if (companies.some((company) => company.status === "needs_review")) {
    return "needs_review";
  }
  return "queued";
}
