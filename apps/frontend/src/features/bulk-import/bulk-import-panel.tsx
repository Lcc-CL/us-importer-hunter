"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  Ban,
  CheckCircle2,
  ExternalLink,
  FileCheck2,
  FileSearch,
  GitMerge,
  Play,
  RefreshCw,
  Route,
  ShieldCheck,
  Upload,
} from "lucide-react";

import {
  senderProfileServerSnapshot,
  senderProfileSnapshot,
  subscribeSenderProfile,
} from "@/features/mvp-analysis/sender-profile";
import type { ProspectSender } from "@/features/mvp-analysis/prospect-state";
import type { AcceptanceHealthState } from "@/features/mvp-analysis/components/provider-badge";

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
  getRoutingPreview,
  preflightNetEaseImport,
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
  type NetEasePreflightResponse,
  type ProspectRouteResponse,
  type ProspectBatchCompanyResponse,
  type ProspectBatchExecutionResponse,
  type ProspectBatchResponse,
  type ProspectBatchSender,
  type ProspectRoutingRunResponse,
  type RoutingPreviewResponse,
  type ProspectTier,
  type RawImportRowResponse,
  type RawImportRowStatus,
  type UmailExportBatchResponse,
  type UmailResultImportResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { UmailExportPanel } from "./umail-export-panel";
import { UmailFeedbackPanel } from "./umail-feedback-panel";
import {
  StructuredMappingEditor,
  type MappingGroupDefinition,
} from "./structured-mapping-editor";

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

function formatBatchTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface BulkImportPanelProps {
  initialSessionId?: string;
  initialRoutingRunId?: string;
  initialBatchId?: string;
  initialUmailExportBatchId?: string;
  initialUmailResultImportId?: string;
  initialRealDataMode?: boolean;
  initialStep?: number;
  health: AcceptanceHealthState;
  onModeChange?: (enabled: boolean) => void;
}

const NETEASE_MAPPING_GROUPS: MappingGroupDefinition[] = [
  {
    labelZh: "公司身份",
    labelEn: "Company identity",
    fields: [
      { key: "company_name", labelZh: "公司名称", labelEn: "Company name", required: true },
      { key: "external_company_id", labelZh: "外部公司 ID", labelEn: "External company ID" },
      { key: "website", labelZh: "官网 / 域名", labelEn: "Website / domain" },
      { key: "company_type", labelZh: "公司类型", labelEn: "Company type" },
    ],
  },
  {
    labelZh: "联系人",
    labelEn: "Contacts",
    fields: [
      { key: "contact_name", labelZh: "联系人姓名", labelEn: "Contact name" },
      { key: "contact_title", labelZh: "职位", labelEn: "Job title" },
      { key: "contact_email", labelZh: "联系人邮箱", labelEn: "Contact email" },
      { key: "contact_phone", labelZh: "联系人电话", labelEn: "Contact phone" },
      { key: "contact_linkedin", labelZh: "LinkedIn", labelEn: "LinkedIn" },
    ],
  },
  {
    labelZh: "贸易记录",
    labelEn: "Trade records",
    fields: [
      { key: "shipment_date", labelZh: "进口 / 到港日期", labelEn: "Shipment date" },
      { key: "last_import_at", labelZh: "最后进口时间", labelEn: "Last import time" },
      { key: "quantity", labelZh: "数量", labelEn: "Quantity" },
      { key: "weight", labelZh: "重量", labelEn: "Weight" },
      { key: "amount", labelZh: "金额", labelEn: "Amount" },
      {
        key: "origin_country",
        labelZh: "产品/供应商来源国",
        labelEn: "Shipment/Supplier origin country",
      },
    ],
  },
  {
    labelZh: "地址和地区",
    labelEn: "Address and region",
    fields: [
      { key: "address", labelZh: "公司地址", labelEn: "Company address" },
      {
        key: "country",
        labelZh: "进口商所在国家/地区",
        labelEn: "Importer company country",
      },
      { key: "phone", labelZh: "公司电话", labelEn: "Company phone" },
      { key: "pol", labelZh: "起运港", labelEn: "Port of loading" },
      { key: "pod", labelZh: "目的港", labelEn: "Port of discharge" },
    ],
  },
  {
    labelZh: "产品和 HS Code",
    labelEn: "Products and HS code",
    fields: [
      { key: "product_description", labelZh: "产品描述", labelEn: "Product description" },
      { key: "hs_code", labelZh: "HS Code", labelEn: "HS code" },
    ],
  },
  {
    labelZh: "其他字段",
    labelEn: "Other fields",
    fields: [],
  },
];

/**
 * Minimal Campaign preset (D5e2h0). JSON config object, no Campaign CRUD:
 * a single real business scenario today. Values auto-derive the Routing
 * Preview parameters; the operator only reviews the summary and clicks
 * "生成客户优先级".
 */
const FITNESS_EQUIPMENT_US_PRESET = {
  id: "fitness-equipment-us-v1",
  market: "美国",
  industry: "健身器材",
  taxonomy: "fitness_equipment_v1",
  originPreference: "China",
  routingPolicy: "real-routing-v1.1",
  targetProductKeywords: "fitness, gym equipment",
  targetHsCodes: "",
  preferredOrigins: "China",
  preferredPol: "",
  preferredPod: "",
  campaignName: "fitness-equipment-us-v1",
} as const;

export function BulkImportPanel({
  initialSessionId,
  initialRoutingRunId,
  initialBatchId,
  initialUmailExportBatchId,
  initialUmailResultImportId,
  initialRealDataMode = false,
  initialStep = 1,
  health,
  onModeChange,
}: BulkImportPanelProps) {
  const { t } = useI18n();
  const backendOk = health.components.backend === "ok";
  const postgresOk = health.components.postgres === "ok";
  const workerOk = health.components.worker === "ok";
  const writesConfirmed = !health.stale;
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [mappingValidated, setMappingValidated] = useState(false);
  const [preflightFileSignature, setPreflightFileSignature] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<NetEasePreflightResponse | null>(null);
  const [preflightBusy, setPreflightBusy] = useState(false);
  const [mappingConfirmed, setMappingConfirmed] = useState(false);
  const [realDataMode, setRealDataMode] = useState(initialRealDataMode);
  const [session, setSession] = useState<ImportSessionResponse | null>(null);
  const [rows, setRows] = useState<RawImportRowResponse[]>([]);
  const [rowTotal, setRowTotal] = useState(0);
  const [rowStatus, setRowStatus] = useState<RawImportRowStatus | "">("");
  const [page, setPage] = useState(1);
  const [resolution, setResolution] = useState<ImportResolutionResponse | null>(null);
  const [decisions, setDecisions] = useState<ImportEntityDecisionResponse[]>([]);
  const [resolving, setResolving] = useState(false);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [routingRun, setRoutingRun] = useState<ProspectRoutingRunResponse | null>(null);
  const [routes, setRoutes] = useState<ProspectRouteResponse[]>([]);
  const [routingPreview, setRoutingPreview] = useState<RoutingPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewTierFilter, setPreviewTierFilter] = useState("All");
  const [confirmMergeDecision, setConfirmMergeDecision] =
    useState<ImportEntityDecisionResponse | null>(null);
  const [confirmRoutingApply, setConfirmRoutingApply] = useState(false);
  const [productKeywords, setProductKeywords] = useState<string>(
    FITNESS_EQUIPMENT_US_PRESET.targetProductKeywords,
  );
  const [hsCodes, setHsCodes] = useState<string>(
    FITNESS_EQUIPMENT_US_PRESET.targetHsCodes,
  );
  const [originCountries, setOriginCountries] = useState<string>(
    FITNESS_EQUIPMENT_US_PRESET.preferredOrigins,
  );
  const [preferredPol, setPreferredPol] = useState<string>(
    FITNESS_EQUIPMENT_US_PRESET.preferredPol,
  );
  const [preferredPod, setPreferredPod] = useState<string>(
    FITNESS_EQUIPMENT_US_PRESET.preferredPod,
  );
  const [campaignName, setCampaignName] = useState<string>(
    FITNESS_EQUIPMENT_US_PRESET.campaignName,
  );
  const [routingBusy, setRoutingBusy] = useState(false);
  const [reviewingRouteId, setReviewingRouteId] = useState<string | null>(null);
  const [routeTiers, setRouteTiers] = useState<Record<string, ProspectTier>>({});
  const [routeReasons, setRouteReasons] = useState<Record<string, string>>({});
  const [selectedACompanies, setSelectedACompanies] = useState<string[]>([]);
  const defaultASelectionAppliedRef = useRef(false);
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
  const [umailExportBatch, setUmailExportBatch] =
    useState<UmailExportBatchResponse | null>(null);
  const [umailResult, setUmailResult] = useState<UmailResultImportResponse | null>(null);
  const [activeStep, setActiveStep] = useState(Math.min(10, Math.max(1, initialStep)));
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
      const eligibleRoutes = page.routes.filter(
        (route) =>
          route.effective_tier === "A" &&
          ["confirmed", "overridden"].includes(route.review_status),
      );
      const eligible = new Set(eligibleRoutes.map((route) => route.company_id));
      if (!defaultASelectionAppliedRef.current && eligibleRoutes.length > 0) {
        // Default selection: A <= 5 selects all A companies; A > 5 selects the
        // top-5 by pre_score. Applied once per session; users may deselect.
        defaultASelectionAppliedRef.current = true;
        setSelectedACompanies(
          [...eligibleRoutes]
            .sort((a, b) => b.pre_score - a.pre_score)
            .slice(0, 5)
            .map((route) => route.company_id),
        );
      } else {
        setSelectedACompanies((current) =>
          current.filter((value) => eligible.has(value)),
        );
      }
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
      void restore(session.session_id, page, rowStatus)
        .then(() => setPollError(null))
        .catch((caught: unknown) => {
          setPollError(getClientErrorDetails(caught).message);
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
      void loadResolutionState(session.session_id)
        .then(() => setPollError(null))
        .catch((caught: unknown) => {
          setPollError(getClientErrorDetails(caught).message);
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
      void loadRoutingState(routingRun.routing_run_id)
        .then(() => setPollError(null))
        .catch((caught: unknown) => {
          setPollError(getClientErrorDetails(caught).message);
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
      void loadRoutedBatchState(createdBatchId)
        .then(() => setPollError(null))
        .catch((caught: unknown) => {
          setPollError(getClientErrorDetails(caught).message);
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

  function updateRealDataMode(enabled: boolean) {
    setRealDataMode(enabled);
    onModeChange?.(enabled);
    setMappingConfirmed(false);
    const currentUrl = new URL(window.location.href);
    if (enabled) currentUrl.searchParams.set("real_data", "1");
    else currentUrl.searchParams.delete("real_data");
    window.history.replaceState(null, "", currentUrl);
  }

  function persistActiveStep(step: number) {
    setActiveStep(step);
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("step", String(step));
    window.history.replaceState(null, "", currentUrl);
  }

  function updateMapping(next: Record<string, string>) {
    setMapping(next);
    setMappingValidated(false);
    setMappingConfirmed(false);
  }

  async function handlePreflight() {
    if (!file || preflightBusy || busy || !backendOk) return;
    setPreflightBusy(true);
    setError(null);
    setMappingConfirmed(false);
    try {
      const inspected = await preflightNetEaseImport(
        file,
        Object.keys(mapping).length ? mapping : undefined,
      );
      setPreflight(inspected);
      setMapping(inspected.suggested_mapping);
      setMappingValidated(true);
      setPreflightFileSignature(fileSignature(file));
      persistActiveStep(2);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setPreflightBusy(false);
    }
  }

  async function handleUpload() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    if (!workerOk) {
      setError(t("runtime.workerRequired"));
      setBusy(false);
      return;
    }
    if (
      !backendOk ||
      !postgresOk ||
      !workerOk ||
      !writesConfirmed ||
      (realDataMode && health.realDataGate !== "enabled") ||
      (realDataMode && (!preflight || !mappingConfirmed || !mappingValidated)) ||
      (preflight && preflightFileSignature !== fileSignature(file))
    ) {
      setError(t("acceptance.confirmMappingRequired"));
      setBusy(false);
      return;
    }
    try {
      const created = await createBulkImportSession(file, DEFAULT_SOURCE, mapping, {
        realData: realDataMode,
        mappingConfirmed,
        expectedFileSha256: preflight?.file_sha256,
      });
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
      persistActiveStep(3);
      await loadRows(created.session_id, 1, "");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStartResolution() {
    if (!session || resolving || !backendOk || !postgresOk || !workerOk || !writesConfirmed) return;
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
    if (!session || reviewingId || !backendOk || !postgresOk || !writesConfirmed) return;
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
    if (!session || routingBusy || !backendOk || !postgresOk || !workerOk || !writesConfirmed) return;
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

  const loadRoutingPreview = useCallback(async () => {
    if (!session || !backendOk) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const preview = await getRoutingPreview(session.session_id, {
        target_product_keywords: splitList(productKeywords),
        target_hs_codes: splitList(hsCodes),
        preferred_origin_countries: splitList(originCountries),
        preferred_pol: splitList(preferredPol),
        preferred_pod: splitList(preferredPod),
      });
      setRoutingPreview(preview);
      setError(null);
    } catch (caught: unknown) {
      setPreviewError(getClientErrorDetails(caught).message);
    } finally {
      setPreviewLoading(false);
    }
  }, [
    session,
    backendOk,
    productKeywords,
    hsCodes,
    originCountries,
    preferredPol,
    preferredPod,
  ]);

  async function handleRouteReview(
    route: ProspectRouteResponse,
    action: "confirm" | "override" | "exclude",
  ) {
    if (reviewingRouteId || !backendOk || !postgresOk || !writesConfirmed) return;
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

  /**
   * One-click deep analysis: creates the prospect batch (if needed) and
   * enqueues the worker job in a single action. The worker then advances
   * research → scoring → contact → decision maker → draft automatically;
   * the only pauses are evidence review, entity/DM ambiguity, provider
   * failure, and final draft approval.
   */
  async function handleStartDeepAnalysis() {
    if (
      !routingRun ||
      batchBusy ||
      !backendOk ||
      !postgresOk ||
      !workerOk ||
      !writesConfirmed ||
      batchExecutionActive ||
      (!createdBatchId &&
        (selectedACompanies.length === 0 || selectedACompanies.length > 5))
    ) return;
    if (!window.confirm(t("bulk.routingBatchStartConfirmation"))) return;
    setBatchBusy(true);
    setError(null);
    try {
      let batchId = createdBatchId;
      if (!batchId) {
        const created = await createRoutedProspectBatch(
          routingRun.routing_run_id,
          selectedACompanies,
        );
        batchId = created.batch_id;
        setCreatedBatchId(batchId);
        persistBatchExecution(batchId);
      }
      const started = await startRoutedProspectBatch(batchId, {
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
    if (
      !createdBatchId ||
      batchBusy ||
      !backendOk ||
      !postgresOk ||
      !workerOk ||
      !writesConfirmed
    ) return;
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
    if (
      !createdBatchId ||
      batchBusy ||
      !backendOk ||
      !postgresOk ||
      !workerOk ||
      !writesConfirmed
    ) return;
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
  const deepAnalysisProviderUnavailable =
    realDataMode &&
    Boolean(
      health.runtime && !health.runtime.draft_available,
    );
  const batchExecutionActive = Boolean(
    batchExecution && ["pending", "leased", "running"].includes(batchExecution.status),
  );
  const draftCount = batchCompanies.filter((company) => company.draft_id !== null).length;
  const resolutionComplete = Boolean(
    resolution && ["completed", "partial_failed"].includes(resolution.resolution_status),
  );
  const routingComplete = Boolean(
    routingRun && ["completed", "partial_completed"].includes(routingRun.status),
  );
  const hasBRoute = routes.some(
    (route) =>
      route.effective_tier === "B" &&
      ["confirmed", "overridden"].includes(route.review_status),
  );
  const acceptanceSteps = [
    { label: t("acceptance.step1"), complete: Boolean(session) || Boolean(preflight), unlocked: true, reason: "" },
    { label: t("acceptance.step2"), complete: Boolean(session) || mappingConfirmed, unlocked: Boolean(preflight) || Boolean(session), reason: t("acceptance.unlockPreflight") },
    { label: t("acceptance.step3"), complete: Boolean(session), unlocked: mappingConfirmed || Boolean(session), reason: t("acceptance.unlockMapping") },
    { label: t("acceptance.step4"), complete: resolutionComplete, unlocked: Boolean(session), reason: t("acceptance.unlockSession") },
    { label: t("acceptance.step5"), complete: routingComplete, unlocked: resolutionComplete, reason: t("acceptance.unlockResolution") },
    { label: t("acceptance.step6"), complete: Boolean(routedBatch || hasBRoute), unlocked: routingComplete, reason: t("acceptance.unlockRouting") },
    { label: t("acceptance.step7"), complete: Boolean(umailExportBatch || initialUmailExportBatchId), unlocked: routingComplete && hasBRoute, reason: t("acceptance.unlockBRoute") },
    { label: t("acceptance.step8"), complete: Boolean(umailResult), unlocked: Boolean(umailExportBatch || initialUmailExportBatchId), reason: t("acceptance.unlockExport") },
    { label: t("acceptance.step9"), complete: Boolean(umailResult?.status.includes("applied")), unlocked: Boolean(umailResult), reason: t("acceptance.unlockPreview") },
    { label: t("acceptance.step10"), complete: false, unlocked: Boolean(umailResult?.status.includes("applied")), reason: t("acceptance.unlockApply") },
  ];
  const selectedColumns = Object.values(mapping);
  const mappingHasConflict = new Set(selectedColumns).size !== selectedColumns.length;
  const mappingComplete = Boolean(mapping.company_name) && !mappingHasConflict;
  const supportedFile = Boolean(file && /\.(csv|xlsx)$/i.test(file.name));
  const currentFileMatchesPreflight = Boolean(
    file && preflight && preflightFileSignature === fileSignature(file),
  );
  const preflightDisabledReasons = [
    !backendOk ? t("runtime.backendRequired") : null,
    !file ? t("acceptance.selectFileReason") : null,
    file && !supportedFile ? t("acceptance.unsupportedFileReason") : null,
  ].filter((value): value is string => Boolean(value));
  const importDisabledReasons = [
    !backendOk ? t("runtime.backendRequired") : null,
    !postgresOk ? t("acceptance.databaseRequired") : null,
    !workerOk ? t("runtime.workerRequired") : null,
    !writesConfirmed ? t("runtime.staleWriteBlocked") : null,
    !preflight ? t("acceptance.unlockPreflight") : null,
    !mappingComplete ? t("acceptance.mappingIncomplete") : null,
    !mappingValidated ? t("acceptance.mappingNeedsValidation") : null,
    !mappingConfirmed ? t("acceptance.unlockMapping") : null,
    !currentFileMatchesPreflight ? t("acceptance.fileHashChanged") : null,
    realDataMode && health.realDataGate !== "enabled"
      ? t("acceptance.systemGateBlockedReason")
      : null,
  ].filter((value): value is string => Boolean(value));
  const acceptanceModeLabel = realDataMode && mappingConfirmed
    ? t("acceptance.controlledMode")
    : preflight
      ? t("acceptance.waitingMapping")
      : t("acceptance.preparationMode");
  const hasCompanySummaryFields = [
    "hs_code",
    "product_description",
    "supplier",
    "amount",
  ].some((field) => Boolean(mapping[field]));
  const isCompanyImportSummary = Boolean(
    preflight &&
      (preflight.company_import_summary_rows ?? 0) > 0 &&
      (preflight.true_shipment_rows ?? 0) === 0,
  );
  const mappingGroups = isCompanyImportSummary
    ? NETEASE_MAPPING_GROUPS.map((group) =>
        group.labelEn === "Trade records"
          ? {
              ...group,
              labelZh: t("acceptance.importSummaryGroup"),
              labelEn: "Company import summary",
            }
          : group,
      )
    : NETEASE_MAPPING_GROUPS;
  const firstIncompleteIndex = acceptanceSteps.findIndex(
    (step) => !step.complete && step.unlocked,
  );
  const firstExecutableIndex = firstIncompleteIndex + 1;
  const firstExecutableStep =
    firstIncompleteIndex >= 0 ? acceptanceSteps[firstIncompleteIndex] : null;
  const nextStep =
    firstIncompleteIndex >= 0 && firstIncompleteIndex + 1 < acceptanceSteps.length
      ? acceptanceSteps[firstIncompleteIndex + 1]
      : null;

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
        <div className="mt-4 rounded-2xl border border-indigo-200 bg-white/90 p-4" data-testid="acceptance-step-nav">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-700">
                {t("acceptance.kicker")}
              </p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {t("acceptance.currentStep", { step: activeStep })}
              </p>
              {firstExecutableStep ? (
                <p
                  className="mt-1 text-xs text-slate-600"
                  data-testid="acceptance-current-executable"
                >
                  {t("acceptance.currentExecutable", {
                    step: firstExecutableIndex,
                    label: firstExecutableStep.label,
                  })}
                </p>
              ) : null}
              {nextStep ? (
                <p
                  className="mt-1 text-xs text-slate-600"
                  data-testid="acceptance-next-step"
                >
                  {t("acceptance.nextStep", { label: nextStep.label })}
                </p>
              ) : null}
              <p className="mt-1 text-xs text-slate-600" data-testid="acceptance-mode-label">
                {acceptanceModeLabel}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs font-semibold">
              <span className={realDataMode ? "rounded-full bg-emerald-100 px-3 py-1 text-emerald-900" : "rounded-full bg-slate-100 px-3 py-1 text-slate-700"}>
                {realDataMode ? t("acceptance.realData") : t("acceptance.syntheticData")}
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
                {t("acceptance.providerNotCalled")}
              </span>
              <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-900">
                {t("acceptance.noSend")}
              </span>
            </div>
          </div>
          <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {acceptanceSteps.map((step, index) => (
              <li
                className={step.complete ? "rounded-xl border border-emerald-200 bg-emerald-50 text-xs text-emerald-900" : index + 1 === activeStep ? "rounded-xl border border-indigo-300 bg-indigo-50 text-xs font-semibold text-indigo-900" : "rounded-xl border border-slate-200 bg-slate-50 text-xs text-slate-500"}
                key={step.label}
              >
                <button
                  className="w-full p-2 text-left disabled:cursor-not-allowed"
                  data-testid={`acceptance-step-${index + 1}`}
                  disabled={!step.unlocked}
                  onClick={() => persistActiveStep(index + 1)}
                  title={step.unlocked ? step.label : step.reason}
                  type="button"
                >
                  {index + 1}. {step.label}
                  {!step.unlocked ? (
                    <span className="mt-1 block truncate text-[10px] font-normal text-slate-400">
                      {step.reason}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-slate-600">
            {t("acceptance.entitySummary", {
              rows: session?.total_rows ?? 0,
              accepted: session?.accepted_rows ?? 0,
              companies: resolution?.canonical_company_count ?? 0,
              contacts: resolution?.canonical_contact_count ?? 0,
              routes:
                routingPreview?.companies.length ??
                routingRun?.total_companies ??
                0,
            })}
          </p>
          {preflight ? (
            <p className="mt-1 text-xs text-slate-500" data-testid="preflight-estimate">
              {t("acceptance.preflightEstimate", {
                companies: preflight.estimated_company_count,
                contacts: preflight.estimated_contact_count,
              })}
            </p>
          ) : null}
        </div>
      </div>

      {activeStep === 1 ? (
        <div className="grid gap-4 p-5 sm:p-7 lg:grid-cols-2" data-testid="acceptance-workspace-step-1">
          <label className="block text-sm font-medium text-slate-800">
            {t("bulk.file")}
            <input
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-100 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-indigo-900"
              data-testid="bulk-import-file"
              disabled={busy}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setPreflight(null);
                setMapping({});
                setMappingValidated(false);
                setPreflightFileSignature(null);
                setMappingConfirmed(false);
              }}
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
          <label className="flex items-start gap-2 rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-sm text-slate-700 lg:col-span-2">
            <input
              checked={realDataMode}
              className="mt-1"
              data-testid="acceptance-real-data-mode"
              onChange={(event) => updateRealDataMode(event.target.checked)}
              type="checkbox"
            />
            <span>{t("acceptance.realDataToggle")}</span>
          </label>
          <p
            className="text-xs font-medium text-slate-600 lg:col-span-2"
            data-testid="system-gate"
          >
            {t("acceptance.systemGate")}:{" "}
            {health.realDataGate === "enabled"
              ? t("acceptance.systemGateEnabled")
              : t("acceptance.systemGateDisabled")}
          </p>
          <div className="lg:col-span-2">
            <button
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-indigo-300 bg-white px-5 text-sm font-semibold text-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="netease-preflight"
              disabled={busy || preflightBusy || preflightDisabledReasons.length > 0}
              onClick={() => void handlePreflight()}
              type="button"
            >
              <FileSearch className="size-4" />
              {preflightBusy ? t("acceptance.preflighting") : t("acceptance.preflight")}
            </button>
            <p className="mt-2 text-xs text-slate-500">{t("bulk.limits")}</p>
            {preflightDisabledReasons.length ? (
              <p className="mt-2 text-xs text-amber-800" data-testid="netease-preflight-disabled-reason">
                {preflightDisabledReasons.join(" · ")}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {activeStep === 2 && preflight ? (
        <div className="space-y-4 p-5 sm:p-7" data-testid="acceptance-workspace-step-2">
          {hasCompanySummaryFields ? (
            <p
              className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"
              data-testid="company-import-summary-note"
            >
              {t("acceptance.companyImportSummary")}
            </p>
          ) : null}
          <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            {t("acceptance.noEmailInMappingStep")}
          </p>
          <div className="rounded-2xl border border-indigo-200 bg-slate-50 p-4" data-testid="netease-preflight-result">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-900">
                {preflight.mapping_profile} · {preflight.file_type.toUpperCase()} · {preflight.inferred_data_type}
              </p>
              <span className={preflight.real_data_gate === "enabled" ? "rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-900" : "rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-900"}>
                {preflight.real_data_gate === "enabled" ? t("acceptance.gateEnabled") : t("acceptance.gateBlocked")}
              </span>
            </div>
            <p className="mt-2 font-mono text-[10px] text-slate-500">
              SHA-256 {preflight.file_sha256.slice(0, 12)}…{preflight.file_sha256.slice(-8)}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {[
                [t("acceptance.rawRows"), preflight.total_rows],
                [t("acceptance.companyAnchors"), preflight.company_anchor_rows ?? 0],
                [t("acceptance.contactContinuation"), preflight.contact_continuation_rows ?? 0],
                [t("acceptance.companies"), preflight.estimated_company_count],
                [t("acceptance.contacts"), preflight.estimated_contact_count],
                [
                  t("acceptance.reviewRequired"),
                  (preflight.orphan_contact_rows ?? 0) +
                    preflight.estimated_medium_confidence_reviews,
                ],
                [t("acceptance.invalidRows"), preflight.invalid_rows],
              ].map(([label, value]) => (
                <div className="rounded-xl bg-white p-2" key={String(label)}>
                  <p className="text-[11px] text-slate-500">{label}</p>
                  <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-slate-500">
              {t("acceptance.highConfidenceMerge", {
                count: preflight.estimated_high_confidence_reviews,
              })}
              {" · "}
              {t("acceptance.mediumConfidenceMerge", {
                count: preflight.estimated_medium_confidence_reviews,
              })}
            </p>
          </div>

          {preflight.true_shipment_rows !== undefined ? (
            <p
              className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"
              data-testid="true-shipment-count"
            >
              {t("acceptance.trueShipmentRows", {
                count: preflight.true_shipment_rows ?? 0,
              })}
            </p>
          ) : null}

          <StructuredMappingEditor
            confidence={preflight.mapping_confidence}
            source={preflight.mapping_source}
            confirmed={mappingConfirmed}
            disabled={busy || preflightBusy}
            duplicateColumns={preflight.duplicate_columns}
            groups={mappingGroups}
            mapping={mapping}
            onChange={updateMapping}
            samples={preflight.sample_values}
            sourceColumns={preflight.source_columns}
            validated={mappingValidated}
          />

          <div
            className="rounded-xl border border-indigo-200 bg-indigo-50/70 p-3"
            data-testid="prewrite-preview"
          >
            <p className="text-xs font-semibold text-indigo-900">
              {t("acceptance.prewritePreview")}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-700 sm:grid-cols-3">
              <span>
                {t("acceptance.rawRows")}: {preflight.total_rows}
              </span>
              <span>
                {t("acceptance.companies")}:{" "}
                {preflight.expected_company_count ?? preflight.estimated_company_count}
              </span>
              <span>
                {t("acceptance.contacts")}:{" "}
                {preflight.expected_contact_count ?? preflight.estimated_contact_count}
              </span>
              <span>
                CompanyContact: {preflight.companycontact_relation_count ?? 0}
              </span>
              <span>
                {t("acceptance.importSummaryGroup")}:{" "}
                {preflight.company_import_summary_rows ?? 0}
              </span>
              <span>
                {t("acceptance.shipments")}: {preflight.true_shipment_rows ?? 0}
              </span>
              <span>
                {t("acceptance.companyMerges")}: {preflight.company_merge_count ?? 0}
              </span>
              <span>
                {t("acceptance.contactDedup")}: {preflight.contact_merge_count ?? 0}
              </span>
              <span>
                {t("acceptance.reviewRequired")}:{" "}
                {(preflight.contact_review_count ?? 0) +
                  (preflight.company_review_count ?? 0)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-start gap-4">
            <button
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-indigo-300 bg-white px-4 text-sm font-semibold text-indigo-800 disabled:opacity-50"
              data-testid="netease-preflight-again"
              disabled={busy || preflightBusy || !file || !backendOk}
              onClick={() => void handlePreflight()}
              type="button"
            >
              <RefreshCw className="size-4" /> {t("acceptance.revalidateMapping")}
            </button>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                checked={mappingConfirmed}
                className="mt-1"
                data-testid="netease-mapping-confirmed"
                disabled={!mappingComplete || !mappingValidated}
                onChange={(event) => setMappingConfirmed(event.target.checked)}
                type="checkbox"
              />
              <span>{t("acceptance.confirmMapping")}</span>
            </label>
            <button
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-indigo-700 px-5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="bulk-import-upload"
              disabled={busy || preflightBusy || !file || importDisabledReasons.length > 0}
              onClick={handleUpload}
              type="button"
            >
              <Upload className="size-4" />
              {busy ? t("bulk.processing") : t("bulk.upload")}
            </button>
          </div>
          {importDisabledReasons.length ? (
            <p className="text-xs text-amber-800" data-testid="bulk-import-disabled-reason">
              {importDisabledReasons.join(" · ")}
            </p>
          ) : null}
        </div>
      ) : null}

      <p
        className="mx-5 mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900 sm:mx-7"
        data-testid="stage-boundary"
      >
        {resolutionComplete ? t("bulk.boundaryResolved") : t("bulk.boundary")}
      </p>

      {error ? (
        <p
          className="mx-5 mb-6 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 sm:mx-7"
          data-testid="global-error"
        >
          {error}
        </p>
      ) : null}
      {pollError ? (
        <p
          className="mx-5 mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 sm:mx-7"
          data-testid="poll-error"
        >
          {pollError}
        </p>
      ) : null}

      {activeStep === 8 || activeStep === 9 ? (
        <UmailFeedbackPanel
          exportBatchId={umailExportBatch?.batch_id ?? initialUmailExportBatchId}
          health={health}
          initialImportId={initialUmailResultImportId}
          mode={activeStep === 8 ? "preview" : "apply"}
          onImportChange={setUmailResult}
          realDataMode={realDataMode}
        />
      ) : null}

      {activeStep === 10 ? (
        <div className="border-t border-slate-200 p-5 sm:p-7" data-testid="acceptance-workspace-step-10">
          <h3 className="text-lg font-semibold text-slate-950">{t("acceptance.step10")}</h3>
          <p className="mt-2 text-sm text-slate-600">{t("acceptance.closureSummary")}</p>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MetricCard label={t("acceptance.rows")} value={session?.total_rows ?? 0} />
            <MetricCard
              label={t("acceptance.companies")}
              value={resolution?.canonical_company_count ?? 0}
            />
            <MetricCard label={t("bulk.routingTotal")} value={routingRun?.total_companies ?? 0} />
            <MetricCard label={t("feedback.appliedEvents")} value={umailResult?.applied_event_count ?? 0} />
          </div>
          <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            {t("acceptance.noSend")}
          </p>
        </div>
      ) : null}

      {session && activeStep >= 3 && activeStep <= 7 ? (
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

          {activeStep === 4 ? (
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
                  !backendOk ||
                  !postgresOk ||
                  !workerOk ||
                  !writesConfirmed ||
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
            {!workerOk ? (
              <p
                className="mt-2 text-xs font-medium text-amber-800"
                data-testid="worker-disabled-reason"
              >
                {t("runtime.workerRequired")}
              </p>
            ) : null}

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
                    <span className="text-xs text-slate-500" data-testid="review-progress">
                      {t("bulk.reviewProgress", {
                        done: 0,
                        pending: decisions.length,
                      })}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
                    <span>
                      {t("bulk.reviewPendingCount", { count: decisions.length })}
                    </span>
                    <span>
                      {t("bulk.reviewCompanyConflicts", {
                        count: decisions.filter((d) => d.entity_type === "company").length,
                      })}
                    </span>
                    <span>
                      {t("bulk.reviewContactConflicts", {
                        count: decisions.filter((d) => d.entity_type === "contact").length,
                      })}
                    </span>
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
                            <div className="flex items-center gap-2">
                              {decision.is_department_contact ? (
                                <span
                                  className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900"
                                  data-testid="department-contact-badge"
                                >
                                  {t("bulk.departmentContact")}
                                </span>
                              ) : null}
                              <span className="text-xs text-slate-500">
                                {(decision.confidence * 100).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-slate-600">
                            {decision.reason_codes.join(" · ")}
                          </p>
                          {decision.source_facts ? (
                            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-600 sm:grid-cols-3">
                              {Object.entries(decision.source_facts).map(([key, value]) => (
                                <div key={key}>
                                  <dt className="text-slate-400">{key}</dt>
                                  <dd className="truncate font-medium text-slate-700">
                                    {value}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          ) : null}
                          {decision.is_department_contact ? (
                            <p className="mt-2 text-[11px] text-amber-800">
                              {t("bulk.departmentContactNote")}
                            </p>
                          ) : null}
                          <div className="mt-3 flex flex-wrap gap-2">
                            <span className="mr-1 self-center text-[11px] text-slate-500">
                              {t("bulk.reviewDefaultDefer")}
                            </span>
                            {(
                              [
                                [
                                  "defer",
                                  t("bulk.reviewDefer"),
                                  t("bulk.reviewDeferHint"),
                                ],
                                [
                                  "merge",
                                  t("bulk.reviewMerge"),
                                  t("bulk.reviewMergeHint"),
                                ],
                                [
                                  "keep_separate",
                                  t("bulk.reviewSeparate"),
                                  t("bulk.reviewSeparateHint"),
                                ],
                                [
                                  "reject",
                                  t("bulk.reviewReject"),
                                  t("bulk.reviewRejectHint"),
                                ],
                              ] as const
                            ).map(([action, label, hint]) => (
                              <button
                                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-40"
                                disabled={
                                  !backendOk ||
                                  !postgresOk ||
                                  !writesConfirmed ||
                                  Boolean(reviewingId)
                                }
                                key={action}
                                title={hint}
                                onClick={
                                  action === "defer"
                                    ? () => undefined
                                    : action === "merge" &&
                                        (decision.confidence < 0.8 ||
                                          decision.reason_codes.includes("company_name_similar") ||
                                          decision.reason_codes.includes("same_company_name_only"))
                                      ? () => setConfirmMergeDecision(decision)
                                      : () => void handleReview(decision.decision_id, action)
                                }
                                type="button"
                                data-testid={`review-action-${action}`}
                              >
                                {action !== "defer" && reviewingId === decision.decision_id
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
          ) : null}

          {activeStep >= 5 && activeStep <= 7 ? (
            <div
              className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4"
              data-testid="prospect-routing-panel"
            >
            {activeStep === 5 ? (
              <>
            <div className="mb-4 rounded-xl border border-emerald-200 bg-white p-3" data-testid="routing-preview-panel">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold text-emerald-900">
                  {t("routing.previewTitle")}
                </p>
                <button
                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-semibold text-emerald-800 disabled:opacity-50"
                  data-testid="routing-preview-generate"
                  disabled={previewLoading || !backendOk}
                  onClick={() => void loadRoutingPreview()}
                  type="button"
                >
                  <RefreshCw className={`size-3.5 ${previewLoading ? "animate-spin" : ""}`} />
                  {t("routing.previewGenerate")}
                </button>
              </div>
              {previewError ? (
                <p className="mt-2 text-xs text-rose-700">{previewError}</p>
              ) : null}
              {routingPreview ? (
                <div className="mt-3">
                  <div className="flex flex-wrap gap-2 text-xs">
                    {(["A", "B", "C", "D", "blocked"] as const).map((tier) => (
                      <button
                        className={
                          previewTierFilter === tier
                            ? "rounded-full bg-emerald-800 px-3 py-1 font-semibold text-white"
                            : "rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-700"
                        }
                        data-testid={`routing-filter-${tier}`}
                        key={tier}
                        onClick={() => setPreviewTierFilter(tier)}
                        type="button"
                      >
                        {tier === "A"
                          ? t("routing.tierA")
                          : tier === "B"
                            ? t("routing.tierB")
                            : tier === "C"
                              ? t("routing.tierC")
                              : tier === "D"
                                ? t("routing.tierD")
                                : t("routing.tierBlocked")}
                        : {routingPreview.totals[tier] ?? 0}
                      </button>
                    ))}
                    <button
                      className={
                        previewTierFilter === "All"
                          ? "rounded-full bg-emerald-800 px-3 py-1 font-semibold text-white"
                          : "rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-700"
                      }
                      onClick={() => setPreviewTierFilter("All")}
                      type="button"
                    >
                      {t("routing.filterAll")}
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] text-slate-500">
                    {t("routing.tierLegend")}
                  </p>
                  <p className="mt-1 text-[11px] font-semibold text-amber-700">
                    {t("routing.notWinProbability")}
                  </p>
                  <div className="mt-3 space-y-2">
                    {routingPreview.companies
                      .filter((company) =>
                        previewTierFilter === "All" || company.tier === previewTierFilter,
                      )
                      .sort((a, b) => b.pre_score - a.pre_score)
                      .map((company) => (
                        <div
                          className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs"
                          data-testid={`routing-preview-company-${company.tier}`}
                          key={company.company_id}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-slate-800">
                              {company.company_name}
                            </span>
                            <span className="text-slate-500">
                              {company.tier} · {company.pre_score.toFixed(1)}
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-600">
                            {company.reason_codes.slice(0, 4).join(" · ")}
                          </p>
                          {company.explicit_negative.length ? (
                            <p className="mt-1 text-[11px] font-semibold text-rose-700">
                              {company.explicit_negative.join(" · ")}
                            </p>
                          ) : null}
                          {company.unknown_evidence.length ? (
                            <p className="mt-1 text-[11px] text-slate-500">
                              {company.unknown_evidence.slice(0, 3).join(" · ")}
                            </p>
                          ) : null}
                          <p className="mt-1 font-mono text-[10px] text-slate-400">
                            rules: {company.rules_version} · contacts {company.person_contact_count}p/
                            {company.department_contact_count}d · import{" "}
                            {company.import_signal ? "Y" : "N"}
                          </p>
                        </div>
                      ))}
                  </div>
                  {!routingPreview.preview_valid ? (
                    <p className="mt-2 text-xs font-semibold text-rose-700" data-testid="preview-invalid">
                      {t("routing.previewInvalid")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div
              className="mb-4 rounded-xl border border-emerald-200 bg-white p-4"
              data-testid="routing-campaign-summary"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
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
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-semibold text-emerald-900">
                  {t("bulk.routingPreset")}: {FITNESS_EQUIPMENT_US_PRESET.id}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                {[
                  [t("bulk.routingMarket"), FITNESS_EQUIPMENT_US_PRESET.market],
                  [t("bulk.routingIndustry"), FITNESS_EQUIPMENT_US_PRESET.industry],
                  [
                    t("bulk.routingSupplyPreference"),
                    originCountries || t("bulk.routingNoValue"),
                  ],
                  [
                    t("bulk.routingRulesVersion"),
                    routingPreview?.rules_version ??
                      FITNESS_EQUIPMENT_US_PRESET.routingPolicy,
                  ],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <dt className="text-[11px] text-slate-400">{String(label)}</dt>
                    <dd className="mt-0.5 truncate text-xs font-semibold text-slate-800">
                      {String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            <details
              className="mb-4 rounded-xl border border-emerald-200 bg-white p-3"
              data-testid="routing-advanced-rules"
            >
              <summary className="cursor-pointer text-xs font-semibold text-slate-700">
                {t("bulk.routingAdvancedTitle")}
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  [
                    t("bulk.routingProducts"),
                    productKeywords,
                    setProductKeywords,
                    "prospect-routing-products",
                  ],
                  [
                    t("bulk.routingHsCodes"),
                    hsCodes,
                    setHsCodes,
                    "prospect-routing-hs",
                  ],
                  [
                    t("bulk.routingOrigins"),
                    originCountries,
                    setOriginCountries,
                    "prospect-routing-origins",
                  ],
                  [
                    t("bulk.routingPol"),
                    preferredPol,
                    setPreferredPol,
                    "prospect-routing-pol",
                  ],
                  [
                    t("bulk.routingPod"),
                    preferredPod,
                    setPreferredPod,
                    "prospect-routing-pod",
                  ],
                ].map(([label, value, setter, testId]) => (
                  <label className="text-xs font-medium text-slate-700" key={String(testId)}>
                    {String(label)}
                    <input
                      className="mt-1 block w-full rounded-xl border border-emerald-200 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-500"
                      data-testid={String(testId)}
                      onChange={(event) =>
                        (setter as (next: string) => void)(event.target.value)
                      }
                      placeholder={t("bulk.routingNoValue")}
                      value={String(value)}
                    />
                  </label>
                ))}
                <div>
                  <p className="text-xs font-medium text-slate-700">
                    {t("bulk.routingRulesVersion")}
                  </p>
                  <p className="mt-1 rounded-xl border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700">
                    {routingPreview?.rules_version ??
                      FITNESS_EQUIPMENT_US_PRESET.routingPolicy}
                  </p>
                </div>
              </div>
            </details>

            <div className="flex flex-wrap items-start justify-between gap-3">
              <p className="max-w-md text-xs leading-5 text-slate-600">
                {t("bulk.routingBoundary")}
              </p>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="prospect-routing-start"
                disabled={
                  !backendOk ||
                  !postgresOk ||
                  !workerOk ||
                  !writesConfirmed ||
                  routingBusy ||
                  !routingPreview ||
                  routingPreview.entity_pending_count > 0 ||
                  !routingPreview.preview_valid ||
                  !routingPreview.rules_version ||
                  health.realDataGate !== "enabled" ||
                  !resolution ||
                  !["completed", "partial_failed"].includes(resolution.resolution_status) ||
                  Boolean(
                    routingRun?.processing_status &&
                      ["pending", "leased", "running"].includes(
                        routingRun.processing_status,
                      ),
                  )
                }
                onClick={() => setConfirmRoutingApply(true)}
                type="button"
              >
                <Route className="size-4" />
                {routingBusy ? t("bulk.routingStarting") : t("bulk.routingStart")}
              </button>
              {routingPreview && routingPreview.entity_pending_count > 0 ? (
                <p
                  className="mt-2 text-xs font-medium text-amber-800"
                  data-testid="routing-apply-blocker"
                >
                  {t("routing.applyBlockerPending", {
                    count: routingPreview.entity_pending_count,
                  })}
                </p>
              ) : routingPreview && !routingPreview.preview_valid ? (
                <p
                  className="mt-2 text-xs font-medium text-rose-700"
                  data-testid="routing-apply-blocker"
                >
                  {t("routing.applyBlockerInvalid")}
                </p>
              ) : health.realDataGate !== "enabled" ? (
                <p
                  className="mt-2 text-xs font-medium text-amber-800"
                  data-testid="routing-apply-blocker"
                >
                  {t("routing.applyBlockerGate")}
                </p>
              ) : null}
            </div>

            <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              {t("bulk.routingBoundary")}
            </p>
            {!workerOk ? (
              <p
                className="mt-2 text-xs font-medium text-amber-800"
                data-testid="worker-disabled-reason"
              >
                {t("runtime.workerRequired")}
              </p>
            ) : null}
              </>
            ) : (
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-800">
                  {activeStep === 6 ? t("acceptance.step6") : t("acceptance.step7")}
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  {activeStep === 6 ? t("acceptance.step6Hint") : t("acceptance.step7Hint")}
                </p>
              </div>
            )}

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

                {activeStep === 6 && routes.length ? (
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
                                        disabled={
                                          !backendOk ||
                                          !postgresOk ||
                                          !writesConfirmed ||
                                          Boolean(reviewingRouteId)
                                        }
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
                                        disabled={
                                          !backendOk ||
                                          !postgresOk ||
                                          !writesConfirmed ||
                                          Boolean(reviewingRouteId)
                                        }
                                        onClick={() => void handleRouteReview(route, "override")}
                                        type="button"
                                      >
                                        {t("bulk.routingOverride")}
                                      </button>
                                      <button
                                        className="inline-flex items-center gap-1 rounded-lg border border-rose-300 px-2 py-1 font-semibold text-rose-700 disabled:opacity-40"
                                        disabled={
                                          !backendOk ||
                                          !postgresOk ||
                                          !writesConfirmed ||
                                          Boolean(reviewingRouteId)
                                        }
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

                {activeStep === 7 ? (
                  <UmailExportPanel
                    campaign={campaignName}
                    health={health}
                    initialBatchId={initialUmailExportBatchId}
                    key={routingRun.routing_run_id}
                    routes={routes}
                    routingRunId={routingRun.routing_run_id}
                    onBatchChange={setUmailExportBatch}
                  />
                ) : null}

                {activeStep === 6 ? (
                  <>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button
                    className="rounded-xl bg-emerald-800 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="deep-analysis-start"
                    disabled={
                      !backendOk ||
                      !postgresOk ||
                      !workerOk ||
                      !writesConfirmed ||
                      batchBusy ||
                      selectedACompanies.length === 0 ||
                      selectedACompanies.length > 5 ||
                      deepAnalysisProviderUnavailable
                    }
                    onClick={() => void handleStartDeepAnalysis()}
                    type="button"
                  >
                    {t("bulk.routingDeepAnalysis", {
                      count: selectedACompanies.length,
                    })}
                  </button>
                  <span className="text-xs text-slate-500">
                    {t("bulk.routingBatchLimit")}
                  </span>
                  {deepAnalysisProviderUnavailable ? (
                    <p
                      className="text-xs font-medium text-amber-800"
                      data-testid="deep-analysis-provider-blocker"
                    >
                      {t("batch.providerNotConfigured")}
                    </p>
                  ) : null}
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
                          {t("bulk.routingBatchSource")}
                        </p>
                        <p className="mt-1 text-sm font-semibold text-slate-900" data-testid="prospect-routing-batch-status">
                          {t(`bulk.routingBatchStatus.${routedBatchStatus}`)}
                        </p>
                        <p className="mt-1 text-xs text-slate-500" data-testid="prospect-routing-batch-progress">
                          {t("batch.progress", {
                            completed: routedBatch.completed_count,
                            needsReview: routedBatch.needs_review_count,
                            failed: routedBatch.failed_count,
                          })}
                        </p>
                      </div>
                      <button
                        className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="prospect-routing-batch-start"
                        disabled={
                          !backendOk ||
                          !postgresOk ||
                          !workerOk ||
                          !writesConfirmed ||
                          batchBusy ||
                          batchExecutionActive ||
                          deepAnalysisProviderUnavailable
                        }
                        onClick={() => void handleStartDeepAnalysis()}
                        type="button"
                      >
                        <Play className="size-4" />
                        {batchBusy || batchExecutionActive
                          ? t("bulk.routingBatchStarting")
                          : t("bulk.routingDeepAnalysisSimple")}
                      </button>
                    </div>

                    <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-2">
                      <summary className="cursor-pointer text-[11px] font-semibold text-slate-500">
                        {t("batch.technicalDetails")}
                      </summary>
                      <div className="mt-2 space-y-1 font-mono text-[10px] text-slate-500">
                        <p>
                          generation {routedBatch.routing_execution_generation}
                        </p>
                        <p>{createdBatchId}</p>
                      </div>
                    </details>

                    <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
                      {t("bulk.routingBatchStartWarning")}
                    </p>
                    {!workerOk ? (
                      <p
                        className="mt-2 text-xs font-medium text-amber-800"
                        data-testid="worker-disabled-reason"
                      >
                        {t("runtime.workerRequired")}
                      </p>
                    ) : null}
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
                          {company.started_at || company.completed_at ? (
                            <p className="mt-1 text-[10px] text-slate-400">
                              {t("batch.lastUpdated", {
                                time: formatBatchTime(
                                  company.completed_at ?? company.started_at ?? "",
                                ),
                              })}
                            </p>
                          ) : null}
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
                                  disabled={
                                    !backendOk ||
                                    !postgresOk ||
                                    !workerOk ||
                                    !writesConfirmed ||
                                    batchBusy ||
                                    batchExecutionActive
                                  }
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
                                disabled={
                                  !backendOk ||
                                  !postgresOk ||
                                  !workerOk ||
                                  !writesConfirmed ||
                                  batchBusy ||
                                  batchExecutionActive
                                }
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
                  </>
                ) : null}
              </div>
            ) : null}
            </div>
          ) : null}

          {activeStep === 3 ? (
            <>
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
            </>
          ) : null}
        </div>
      ) : null}
      {confirmMergeDecision ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-900">
              {t("bulk.mergeConfirmTitle")}
            </h3>
            <p className="mt-2 text-xs leading-5 text-slate-600">
              {t("bulk.mergeConfirmBody")}
            </p>
            <div className="mt-4 space-y-3" data-testid="merge-confirm-candidates">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] font-semibold text-slate-500">
                  {t("bulk.mergeCandidateIncoming")}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-700">
                  <div className="col-span-2">
                    <dt className="inline text-slate-400">
                      {t("bulk.mergeRowNumber")}:{" "}
                    </dt>
                    <dd className="inline font-medium">
                      #{confirmMergeDecision.row_number ?? "—"}
                    </dd>
                  </div>
                  {Object.entries(confirmMergeDecision.source_facts ?? {}).map(
                    ([key, value]) => (
                      <div key={key} className="col-span-2">
                        <dt className="inline text-slate-400">{key}: </dt>
                        <dd className="inline font-medium">{value}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] font-semibold text-slate-500">
                  {t("bulk.mergeCandidateExisting")}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-700">
                  <div className="col-span-2">
                    <dt className="inline text-slate-400">
                      {t("bulk.entityCompany")}/{t("bulk.entityContact")}:{" "}
                    </dt>
                    <dd className="inline font-medium">
                      {confirmMergeDecision.candidate_label ?? "—"}
                    </dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="inline text-slate-400">
                      {t("bulk.mergeConfidence")}:{" "}
                    </dt>
                    <dd className="inline font-medium">
                      {(confirmMergeDecision.confidence * 100).toFixed(0)}%
                    </dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="inline text-slate-400">
                      {t("bulk.mergeReason")}:{" "}
                    </dt>
                    <dd className="inline font-medium">
                      {confirmMergeDecision.reason_codes.join(" · ")}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700"
                onClick={() => setConfirmMergeDecision(null)}
                type="button"
              >
                {t("routing.cancel")}
              </button>
              <button
                className="rounded-lg bg-emerald-800 px-3 py-1.5 text-xs font-semibold text-white"
                data-testid="merge-confirm-submit"
                onClick={() => {
                  void handleReview(confirmMergeDecision.decision_id, "merge");
                  setConfirmMergeDecision(null);
                }}
                type="button"
              >
                {t("bulk.reviewMerge")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {confirmRoutingApply ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-900">
              {t("routing.applyConfirmTitle")}
            </h3>
            <p className="mt-2 text-xs leading-5 text-slate-600">
              {routingPreview
                ? t("routing.applyConfirmSummary", {
                    a: routingPreview.totals.A ?? 0,
                    b: routingPreview.totals.B ?? 0,
                    c: routingPreview.totals.C ?? 0,
                    d: routingPreview.totals.D ?? 0,
                  })
                : ""}
            </p>
            <p className="mt-2 text-xs leading-5 text-slate-600">
              {t("routing.applyConfirmBody")}
            </p>
            <p className="mt-2 text-xs font-semibold text-emerald-800">
              {t("routing.noEmailGuarantee")}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700"
                onClick={() => setConfirmRoutingApply(false)}
                type="button"
              >
                {t("routing.cancel")}
              </button>
              <button
                className="rounded-lg bg-emerald-800 px-3 py-1.5 text-xs font-semibold text-white"
                data-testid="routing-apply-confirm-submit"
                onClick={() => {
                  setConfirmRoutingApply(false);
                  void handleStartRouting();
                }}
                type="button"
              >
                {t("routing.applyConfirmButton")}
              </button>
            </div>
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

function fileSignature(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
    </div>
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
