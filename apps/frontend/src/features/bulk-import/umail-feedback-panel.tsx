"use client";

import { CheckCircle2, FileSearch, FileUp, RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  applyUmailResultImport,
  getClientErrorDetails,
  getUmailFeedbackStatistics,
  getUmailResultImport,
  getUmailResultRows,
  preflightUmailResult,
  uploadUmailResultImport,
  type ContactEngagementEventType,
  type UmailFeedbackStatisticsResponse,
  type UmailResultImportResponse,
  type UmailResultMatchStatus,
  type UmailPreflightResponse,
  type UmailResultRowResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const PAGE_SIZE = 50;
const EVENT_TYPES: ContactEngagementEventType[] = [
  "sent",
  "delivered",
  "hard_bounced",
  "soft_bounced",
  "bounce_unknown",
  "unsubscribed",
  "complained",
  "replied",
  "opened",
  "clicked",
];
const MATCH_STATUSES: UmailResultMatchStatus[] = [
  "matched",
  "unmatched",
  "ambiguous",
  "invalid",
  "duplicate",
];

interface UmailFeedbackPanelProps {
  initialImportId?: string;
  realDataMode?: boolean;
  onImportChange?: (result: UmailResultImportResponse) => void;
}

export function UmailFeedbackPanel({
  initialImportId,
  realDataMode = false,
  onImportChange,
}: UmailFeedbackPanelProps) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [mappingText, setMappingText] = useState("");
  const [preflight, setPreflight] = useState<UmailPreflightResponse | null>(null);
  const [mappingConfirmed, setMappingConfirmed] = useState(false);
  const [resultImport, setResultImport] =
    useState<UmailResultImportResponse | null>(null);
  const [rows, setRows] = useState<UmailResultRowResponse[]>([]);
  const [rowTotal, setRowTotal] = useState(0);
  const [statistics, setStatistics] =
    useState<UmailFeedbackStatisticsResponse | null>(null);
  const [matchStatus, setMatchStatus] = useState<UmailResultMatchStatus | "">("");
  const [eventType, setEventType] = useState<ContactEngagementEventType | "">("");
  const [suppressionFilter, setSuppressionFilter] = useState<"" | "yes" | "no">("");
  const [campaignDraft, setCampaignDraft] = useState("");
  const [campaignFilter, setCampaignFilter] = useState("");
  const [page, setPage] = useState(1);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(Boolean(initialImportId));
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(async (resultImportId: string) => {
    const [saved, savedStatistics] = await Promise.all([
      getUmailResultImport(resultImportId),
      getUmailFeedbackStatistics(resultImportId),
    ]);
    setResultImport(saved);
    setStatistics(savedStatistics);
    return saved;
  }, []);

  const fetchRows = useCallback(
    async (resultImportId: string, nextPage: number) => {
      return getUmailResultRows(resultImportId, {
        page: nextPage,
        limit: PAGE_SIZE,
        matchStatus: matchStatus || undefined,
        eventType: eventType || undefined,
        campaign: campaignFilter || undefined,
        suppressionImpact:
          suppressionFilter === "" ? undefined : suppressionFilter === "yes",
      });
    },
    [campaignFilter, eventType, matchStatus, suppressionFilter],
  );

  useEffect(() => {
    if (!initialImportId) return;
    let active = true;
    async function restore() {
      try {
        const restored = await loadSummary(initialImportId as string);
        onImportChange?.(restored);
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
  }, [initialImportId, loadSummary, onImportChange]);

  useEffect(() => {
    if (!resultImport) return;
    let active = true;
    async function restoreRows() {
      try {
        const result = await fetchRows(resultImport?.result_import_id ?? "", page);
        if (active) {
          setRows(result.rows);
          setRowTotal(result.total);
        }
      } catch (caught: unknown) {
        if (active) setError(getClientErrorDetails(caught).message);
      }
    }
    void restoreRows();
    return () => {
      active = false;
    };
  }, [fetchRows, page, resultImport]);

  function persistImportId(resultImportId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("umail_result_import_id", resultImportId);
    window.history.replaceState(null, "", currentUrl);
  }

  function parseMapping(): Record<string, string> | undefined {
    if (!mappingText.trim()) return undefined;
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
    return decoded as Record<string, string>;
  }

  async function handleUpload() {
    if (!file || busy) return;
    let mapping: Record<string, string> | undefined;
    try {
      mapping = parseMapping();
    } catch {
      setError(t("feedback.mappingInvalid"));
      return;
    }
    if (realDataMode && (!preflight || !mappingConfirmed)) {
      setError(t("acceptance.confirmMappingRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    setConfirmed(false);
    try {
      const created = await uploadUmailResultImport(file, mapping, {
        realData: realDataMode,
        mappingConfirmed,
      });
      setResultImport(created);
      onImportChange?.(created);
      setPage(1);
      setMatchStatus("");
      setEventType("");
      setSuppressionFilter("");
      setCampaignDraft("");
      setCampaignFilter("");
      persistImportId(created.result_import_id);
      setStatistics(await getUmailFeedbackStatistics(created.result_import_id));
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePreflight() {
    if (!file || busy) return;
    let mapping: Record<string, string> | undefined;
    try {
      mapping = parseMapping();
    } catch {
      setError(t("feedback.mappingInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    setMappingConfirmed(false);
    try {
      const inspected = await preflightUmailResult(file, mapping);
      setPreflight(inspected);
      setMappingText(JSON.stringify(inspected.suggested_mapping, null, 2));
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleApply() {
    if (!resultImport || !confirmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      const applied = await applyUmailResultImport(
        resultImport.result_import_id,
        realDataMode,
      );
      setResultImport(applied);
      onImportChange?.(applied);
      setStatistics(await getUmailFeedbackStatistics(applied.result_import_id));
      const result = await fetchRows(applied.result_import_id, page);
      setRows(result.rows);
      setRowTotal(result.total);
      setConfirmed(false);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRefresh() {
    if (!resultImport || busy) return;
    setBusy(true);
    setError(null);
    try {
      await loadSummary(resultImport.result_import_id);
      const result = await fetchRows(resultImport.result_import_id, page);
      setRows(result.rows);
      setRowTotal(result.total);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  const pageCount = Math.max(1, Math.ceil(rowTotal / PAGE_SIZE));
  const canApply = resultImport?.status === "ready_for_review";

  return (
    <section
      className="border-t border-violet-200 bg-violet-50/40 px-5 py-6 sm:px-7"
      data-testid="umail-feedback-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-800">
            {t("feedback.kicker")}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">
            {t("feedback.title")}
          </h3>
          <p className="mt-1 max-w-4xl text-sm leading-6 text-slate-600">
            {t("feedback.intro")}
          </p>
        </div>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
          {t("feedback.noSend")}
        </span>
      </div>

      <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-950">
        {t("feedback.exactWarning")}
      </p>

      {error ? (
        <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <label className="text-sm font-medium text-slate-800">
          {t("feedback.file")}
          <input
            accept=".csv,text/csv"
            className="mt-2 block w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-violet-100 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-violet-900"
            data-testid="umail-feedback-file"
            disabled={busy}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreflight(null);
              setMappingConfirmed(false);
            }}
            type="file"
          />
        </label>
        <label className="text-sm font-medium text-slate-800">
          {t("feedback.mapping")}
          <textarea
            className="mt-2 min-h-24 w-full rounded-xl border border-violet-200 bg-white px-3 py-2 font-mono text-xs leading-5"
            data-testid="umail-feedback-mapping"
            disabled={busy}
            onChange={(event) => {
              setMappingText(event.target.value);
              setPreflight(null);
              setMappingConfirmed(false);
            }}
            placeholder={'{"event_type":"状态","occurred_at":"发生时间"}'}
            value={mappingText}
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          className="inline-flex items-center gap-2 rounded-xl border border-violet-300 bg-white px-4 py-2 text-sm font-semibold text-violet-800 disabled:opacity-40"
          data-testid="umail-feedback-preflight"
          disabled={busy || !file}
          onClick={() => void handlePreflight()}
          type="button"
        >
          <FileSearch className="size-4" /> {t("acceptance.preflight")}
        </button>
        <button
          className="inline-flex items-center gap-2 rounded-xl bg-violet-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          data-testid="umail-feedback-upload"
          disabled={busy || !file || (realDataMode && (!preflight || !mappingConfirmed))}
          onClick={() => void handleUpload()}
          type="button"
        >
          <FileUp className="size-4" />
          {busy ? t("feedback.processing") : t("feedback.upload")}
        </button>
        <span className="text-xs text-slate-500">{t("feedback.limits")}</span>
      </div>

      {preflight ? (
        <div className="mt-4 rounded-xl border border-violet-200 bg-white p-3" data-testid="umail-feedback-preflight-result">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-slate-900">
              {preflight.mapping_profile} · {preflight.total_rows} {t("acceptance.rows")}
            </p>
            <span className={preflight.real_data_gate === "enabled" ? "rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-900" : "rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-900"}>
              {preflight.real_data_gate === "enabled"
                ? t("acceptance.gateEnabled")
                : t("acceptance.gateBlocked")}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {[
              [t("acceptance.strongId"), preflight.estimated_strong_id_matches],
              [t("acceptance.emailFallback"), preflight.estimated_email_fallback_matches],
              [t("feedback.match.ambiguous"), preflight.estimated_ambiguous_rows],
              [t("acceptance.unsupportedEvents"), preflight.unsupported_event_count],
              [t("acceptance.missingTime"), preflight.missing_occurred_at_count],
            ].map(([label, value]) => (
              <div className="rounded-lg bg-violet-50 p-2" key={String(label)}>
                <p className="text-[11px] text-slate-500">{label}</p>
                <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
              </div>
            ))}
          </div>
          <label className="mt-3 flex items-start gap-2 text-sm text-slate-700">
            <input
              checked={mappingConfirmed}
              className="mt-1"
              data-testid="umail-preflight-mapping-confirmed"
              disabled={preflight.missing_required_fields.length > 0 || preflight.duplicate_columns.length > 0}
              onChange={(event) => setMappingConfirmed(event.target.checked)}
              type="checkbox"
            />
            <span>{t("acceptance.confirmMapping")}</span>
          </label>
        </div>
      ) : null}

      {resultImport ? (
        <div className="mt-5" data-testid="umail-feedback-preview">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3">
            <div>
              <p className="font-semibold text-slate-900">
                {resultImport.source_filename} · {t(`feedback.status.${resultImport.status}`)}
              </p>
              <p className="mt-1 break-all font-mono text-[10px] text-slate-500">
                SHA-256 {resultImport.file_sha256}
              </p>
              <p className="mt-1 font-mono text-[10px] text-slate-400">
                {resultImport.result_import_id} · {resultImport.mapping_version}
              </p>
            </div>
            <button
              aria-label={t("feedback.refresh")}
              className="rounded-lg border border-violet-200 p-2 text-violet-800 disabled:opacity-40"
              disabled={busy}
              onClick={() => void handleRefresh()}
              type="button"
            >
              <RefreshCw className="size-4" />
            </button>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {MATCH_STATUSES.map((status) => (
              <div className="rounded-xl bg-white p-3" key={status}>
                <p className="text-[11px] text-slate-500">
                  {t(`feedback.match.${status}`)}
                </p>
                <p className="mt-1 text-xl font-semibold text-slate-950">
                  {resultImport[`${status}_count`]}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label={t("feedback.totalRows")} value={resultImport.input_row_count} />
            <Metric
              label={t("feedback.projectedEvents")}
              value={resultImport.projected_event_count}
            />
            <Metric
              label={t("feedback.projectedSuppressions")}
              value={resultImport.projected_suppression_count}
            />
            <Metric
              label={t("feedback.appliedEvents")}
              value={resultImport.applied_event_count}
            />
          </div>

          <details className="mt-3 rounded-xl bg-white p-3 text-xs text-slate-600">
            <summary className="cursor-pointer font-semibold text-slate-800">
              {t("feedback.mappingSnapshot")}
            </summary>
            <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all font-mono">
              {JSON.stringify(resultImport.mapping_snapshot, null, 2)}
            </pre>
          </details>

          {canApply ? (
            <div className="mt-3 rounded-xl border border-violet-200 bg-white p-3">
              <label className="flex items-start gap-2 text-sm text-slate-700">
                <input
                  checked={confirmed}
                  className="mt-1"
                  data-testid="umail-feedback-confirm"
                  onChange={(event) => setConfirmed(event.target.checked)}
                  type="checkbox"
                />
                <span>{t("feedback.confirmApply")}</span>
              </label>
              <button
                className="mt-3 inline-flex items-center gap-2 rounded-xl bg-violet-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
                data-testid="umail-feedback-apply"
                disabled={busy || !confirmed}
                onClick={() => void handleApply()}
                type="button"
              >
                <CheckCircle2 className="size-4" /> {t("feedback.apply")}
              </button>
            </div>
          ) : (
            <p className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-900">
              {t("feedback.appliedSummary", {
                events: resultImport.applied_event_count,
                suppressions: resultImport.suppression_created_count,
              })}
            </p>
          )}

          <div className="mt-5 rounded-xl bg-white p-3">
            <div className="grid gap-2 md:grid-cols-4">
              <select
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                data-testid="umail-feedback-match-filter"
                onChange={(event) => {
                  setMatchStatus(event.target.value as UmailResultMatchStatus | "");
                  setPage(1);
                }}
                value={matchStatus}
              >
                <option value="">{t("feedback.filterAllMatches")}</option>
                {MATCH_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {t(`feedback.match.${status}`)}
                  </option>
                ))}
              </select>
              <select
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                data-testid="umail-feedback-event-filter"
                onChange={(event) => {
                  setEventType(event.target.value as ContactEngagementEventType | "");
                  setPage(1);
                }}
                value={eventType}
              >
                <option value="">{t("feedback.filterAllEvents")}</option>
                {EVENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`feedback.event.${type}`)}
                  </option>
                ))}
              </select>
              <select
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                data-testid="umail-feedback-suppression-filter"
                onChange={(event) => {
                  setSuppressionFilter(event.target.value as "" | "yes" | "no");
                  setPage(1);
                }}
                value={suppressionFilter}
              >
                <option value="">{t("feedback.filterAllSuppression")}</option>
                <option value="yes">{t("feedback.filterSuppressionYes")}</option>
                <option value="no">{t("feedback.filterSuppressionNo")}</option>
              </select>
              <div className="flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  data-testid="umail-feedback-campaign-filter"
                  onChange={(event) => setCampaignDraft(event.target.value)}
                  placeholder={t("feedback.campaignFilter")}
                  value={campaignDraft}
                />
                <button
                  className="rounded-lg border border-violet-200 px-3 py-2 text-xs font-semibold text-violet-800"
                  onClick={() => {
                    setCampaignFilter(campaignDraft.trim());
                    setPage(1);
                  }}
                  type="button"
                >
                  {t("feedback.filter")}
                </button>
              </div>
            </div>

            <div className="mt-3 overflow-x-auto">
              <table className="min-w-[1120px] divide-y divide-slate-200 text-left text-xs">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-2 py-2">#</th>
                    <th className="px-2 py-2">Email</th>
                    <th className="px-2 py-2">Campaign</th>
                    <th className="px-2 py-2">{t("feedback.eventType")}</th>
                    <th className="px-2 py-2">{t("feedback.matchStatus")}</th>
                    <th className="px-2 py-2">{t("feedback.matchSource")}</th>
                    <th className="px-2 py-2">Suppression</th>
                    <th className="px-2 py-2">{t("feedback.errors")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100" data-testid="umail-feedback-rows">
                  {rows.map((row) => (
                    <tr key={row.result_row_id}>
                      <td className="px-2 py-2">{row.row_number}</td>
                      <td className="px-2 py-2">{row.normalized_email ?? "—"}</td>
                      <td className="px-2 py-2">{row.campaign ?? "—"}</td>
                      <td className="px-2 py-2">
                        {row.canonical_event_type
                          ? t(`feedback.event.${row.canonical_event_type}`)
                          : "—"}
                      </td>
                      <td className="px-2 py-2 font-semibold">
                        {t(`feedback.match.${row.match_status}`)}
                      </td>
                      <td className="px-2 py-2 font-mono text-[10px]">
                        {row.match_method ?? "—"}
                      </td>
                      <td className="px-2 py-2">
                        {row.suppression_impact ? (
                          <span className="inline-flex items-center gap-1 text-rose-700">
                            <ShieldAlert className="size-3" /> {t("feedback.yes")}
                          </span>
                        ) : (
                          t("feedback.no")
                        )}
                      </td>
                      <td className="px-2 py-2 text-rose-700">
                        {row.error_codes.join(" · ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-500">
              <span>
                {t("feedback.page", { page, pages: pageCount, total: rowTotal })}
              </span>
              <div className="flex gap-2">
                <button
                  className="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
                  disabled={busy || page <= 1}
                  onClick={() => setPage((current) => current - 1)}
                  type="button"
                >
                  {t("bulk.previous")}
                </button>
                <button
                  className="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
                  disabled={busy || page >= pageCount}
                  onClick={() => setPage((current) => current + 1)}
                  type="button"
                >
                  {t("bulk.next")}
                </button>
              </div>
            </div>
          </div>

          {statistics ? <StatisticsPanel statistics={statistics} /> : null}
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-white p-3">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function StatisticsPanel({
  statistics,
}: {
  statistics: UmailFeedbackStatisticsResponse;
}) {
  const { t } = useI18n();
  const rateMetrics = [
    [t("feedback.matchedRate"), statistics.matched_rate],
    [t("feedback.deliveredRate"), statistics.rates.delivered_rate],
    [t("feedback.replyRate"), statistics.rates.reply_rate],
    [t("feedback.hardBounceRate"), statistics.rates.hard_bounce_rate],
    [t("feedback.unsubscribeRate"), statistics.rates.unsubscribe_rate],
    [t("feedback.complaintRate"), statistics.rates.complaint_rate],
  ] as const;
  return (
    <div className="mt-5 rounded-xl border border-violet-200 bg-white p-3" data-testid="umail-feedback-statistics">
      <h4 className="font-semibold text-slate-900">{t("feedback.statistics")}</h4>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {rateMetrics.map(([label, value]) => (
          <Metric key={label} label={label} value={`${(value * 100).toFixed(1)}%`} />
        ))}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <StatisticsGroup
          entries={Object.entries(statistics.campaign_statistics)}
          title={t("feedback.byCampaign")}
        />
        <StatisticsGroup
          entries={Object.entries(statistics.route_statistics)}
          title={t("feedback.byRoute")}
        />
        <StatisticsGroup
          entries={statistics.company_statistics.map((company) => [
            company.company_name,
            company.event_counts,
          ])}
          title={t("feedback.byCompany")}
        />
      </div>
    </div>
  );
}

function StatisticsGroup({
  title,
  entries,
}: {
  title: string;
  entries: Array<[string, Record<ContactEngagementEventType, number>]>;
}) {
  const { t } = useI18n();
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      <div className="mt-2 max-h-52 space-y-2 overflow-y-auto text-xs">
        {entries.length ? (
          entries.map(([label, counts]) => (
            <div className="rounded-lg bg-white p-2" key={label}>
              <p className="font-semibold text-slate-800">{label}</p>
              <p className="mt-1 text-slate-500">
                {EVENT_TYPES.filter((type) => counts[type] > 0)
                  .map((type) => `${t(`feedback.event.${type}`)} ${counts[type]}`)
                  .join(" · ") || "—"}
              </p>
            </div>
          ))
        ) : (
          <p className="text-slate-500">{t("feedback.noStatistics")}</p>
        )}
      </div>
    </div>
  );
}
