"use client";

import { Download, Plus, ShieldX } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createSuppression,
  createUmailExportBatch,
  deactivateSuppression,
  downloadUmailExportCsv,
  getClientErrorDetails,
  getSuppressions,
  getUmailExportBatch,
  type ProspectRouteResponse,
  type SuppressionEntryResponse,
  type UmailExportBatchResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AcceptanceHealthState } from "@/features/mvp-analysis/components/provider-badge";

interface UmailExportPanelProps {
  routingRunId: string;
  routes: ProspectRouteResponse[];
  campaign: string;
  initialBatchId?: string;
  onBatchChange?: (batch: UmailExportBatchResponse) => void;
  health: AcceptanceHealthState;
}

type SuppressionTarget = "email" | "domain" | "company";

export function UmailExportPanel({
  routingRunId,
  routes,
  campaign,
  initialBatchId,
  onBatchChange,
  health,
}: UmailExportPanelProps) {
  const { t } = useI18n();
  const eligibleRoutes = useMemo(
    () =>
      routes.filter(
        (route) =>
          route.effective_tier === "B" &&
          ["confirmed", "overridden"].includes(route.review_status),
      ),
    [routes],
  );
  const eligibleIds = useMemo(
    () => new Set(eligibleRoutes.map((route) => route.company_id)),
    [eligibleRoutes],
  );
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>([]);
  const [batch, setBatch] = useState<UmailExportBatchResponse | null>(null);
  const [suppressions, setSuppressions] = useState<SuppressionEntryResponse[]>([]);
  const [targetType, setTargetType] = useState<SuppressionTarget>("email");
  const [targetValue, setTargetValue] = useState("");
  const [suppressionReason, setSuppressionReason] = useState("");
  const [busy, setBusy] = useState(Boolean(initialBatchId));
  const [error, setError] = useState<string | null>(null);

  const loadSuppressions = useCallback(async () => {
    const result = await getSuppressions();
    setSuppressions(result.entries);
  }, []);

  const loadBatch = useCallback(async (batchId: string) => {
    const saved = await getUmailExportBatch(batchId);
    setBatch(saved);
    return saved;
  }, []);

  const effectiveSelectedCompanies = selectedCompanies.filter((companyId) =>
    eligibleIds.has(companyId),
  );

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        await loadSuppressions();
        if (initialBatchId) {
          const restored = await loadBatch(initialBatchId);
          onBatchChange?.(restored);
        }
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
  }, [initialBatchId, loadBatch, loadSuppressions, onBatchChange]);

  function toggleCompany(companyId: string) {
    setSelectedCompanies((current) =>
      current.includes(companyId)
        ? current.filter((value) => value !== companyId)
        : [...current, companyId],
    );
  }

  function persistBatchId(batchId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("umail_export_batch_id", batchId);
    window.history.replaceState(null, "", currentUrl);
  }

  async function handlePrepare() {
    if (busy || !health.backend || !health.postgres || !effectiveSelectedCompanies.length) return;
    if (!campaign.trim()) {
      setError(t("bulk.umailCampaignRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createUmailExportBatch(
        routingRunId,
        effectiveSelectedCompanies,
        campaign,
      );
      setBatch(created);
      onBatchChange?.(created);
      persistBatchId(created.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload() {
    if (!batch || busy || !health.backend) return;
    setBusy(true);
    setError(null);
    try {
      const download = await downloadUmailExportCsv(batch.batch_id);
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = download.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      await loadBatch(batch.batch_id);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateSuppression() {
    if (busy || !health.backend || !health.postgres || !targetValue.trim() || !suppressionReason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createSuppression({
        [targetType]: targetValue,
        reason: suppressionReason,
      });
      setTargetValue("");
      setSuppressionReason("");
      await loadSuppressions();
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeactivate(suppressionId: string) {
    if (busy || !health.backend || !health.postgres) return;
    setBusy(true);
    setError(null);
    try {
      await deactivateSuppression(suppressionId);
      await loadSuppressions();
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="mt-5 rounded-2xl border border-indigo-200 bg-indigo-50/60 p-4"
      data-testid="umail-export-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-700">
            {t("bulk.umailKicker")}
          </p>
          <h4 className="mt-1 text-lg font-semibold text-slate-950">
            {t("bulk.umailTitle")}
          </h4>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
            {t("bulk.umailIntro")}
          </p>
        </div>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
          {t("bulk.umailNotSent")}
        </span>
      </div>

      {error ? (
        <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="rounded-xl border border-indigo-100 bg-white p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-slate-900">
              {t("bulk.umailSelectB")}
            </p>
            <button
              className="text-xs font-semibold text-indigo-700 disabled:opacity-40"
              disabled={!eligibleRoutes.length}
              onClick={() =>
                setSelectedCompanies(
                  effectiveSelectedCompanies.length === eligibleRoutes.length
                    ? []
                    : eligibleRoutes.map((route) => route.company_id),
                )
              }
              type="button"
            >
              {t("bulk.umailSelectAll")}
            </button>
          </div>
          <div className="mt-2 max-h-56 space-y-2 overflow-y-auto">
            {eligibleRoutes.length ? (
              eligibleRoutes.map((route) => (
                <label
                  className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 px-3 py-2 text-sm"
                  key={route.route_id}
                >
                  <span className="flex items-center gap-2">
                    <input
                      aria-label={`${t("bulk.umailSelectB")} ${route.company_name}`}
                      checked={effectiveSelectedCompanies.includes(route.company_id)}
                      onChange={() => toggleCompany(route.company_id)}
                      type="checkbox"
                    />
                    <span className="font-medium text-slate-800">{route.company_name}</span>
                  </span>
                  <span className="text-xs text-slate-500">{route.pre_score.toFixed(1)}</span>
                </label>
              ))
            ) : (
              <p className="py-4 text-sm text-slate-500">{t("bulk.umailNoEligibleB")}</p>
            )}
          </div>
          <button
            className="mt-3 w-full rounded-xl bg-indigo-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
            data-testid="umail-export-prepare"
            disabled={!health.backend || !health.postgres || busy || !effectiveSelectedCompanies.length}
            onClick={() => void handlePrepare()}
            type="button"
          >
            {t("bulk.umailPrepare", { count: effectiveSelectedCompanies.length })}
          </button>
        </div>

        <div className="rounded-xl border border-indigo-100 bg-white p-3">
          <p className="text-sm font-semibold text-slate-900">
            {t("bulk.umailSuppression")}
          </p>
          <div className="mt-2 grid grid-cols-[110px_1fr] gap-2">
            <select
              className="rounded-lg border border-slate-200 px-2 py-2 text-sm"
              onChange={(event) => setTargetType(event.target.value as SuppressionTarget)}
              value={targetType}
            >
              <option value="email">Email</option>
              <option value="domain">Domain</option>
              <option value="company">Company</option>
            </select>
            <input
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              data-testid="suppression-target"
              onChange={(event) => setTargetValue(event.target.value)}
              placeholder={t("bulk.umailSuppressionTarget")}
              value={targetValue}
            />
          </div>
          <input
            className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            data-testid="suppression-reason"
            onChange={(event) => setSuppressionReason(event.target.value)}
            placeholder={t("bulk.umailSuppressionReason")}
            value={suppressionReason}
          />
          <button
            className="mt-2 inline-flex items-center gap-1 rounded-lg border border-indigo-200 px-3 py-2 text-xs font-semibold text-indigo-800 disabled:opacity-40"
            data-testid="suppression-create"
            disabled={!health.backend || !health.postgres || busy || !targetValue.trim() || !suppressionReason.trim()}
            onClick={() => void handleCreateSuppression()}
            type="button"
          >
            <Plus className="size-3" /> {t("bulk.umailSuppressionCreate")}
          </button>
          <div className="mt-3 max-h-40 space-y-2 overflow-y-auto text-xs">
            {suppressions.map((entry) => {
              const target = entry.email ?? entry.domain ?? entry.company ?? "—";
              return (
                <div
                  className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-2 py-2"
                  key={entry.suppression_id}
                >
                  <span className={entry.active ? "text-slate-700" : "text-slate-400 line-through"}>
                    {target} · {entry.reason}
                  </span>
                  {entry.active ? (
                    <button
                      aria-label={`${t("bulk.umailSuppressionDeactivate")} ${target}`}
                      className="text-rose-700 disabled:opacity-40"
                      disabled={!health.backend || !health.postgres || busy}
                      onClick={() => void handleDeactivate(entry.suppression_id)}
                      type="button"
                    >
                      <ShieldX className="size-3.5" />
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {batch ? (
        <div
          className="mt-4 rounded-xl border border-indigo-100 bg-white p-3"
          data-testid="umail-export-preview"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-semibold text-slate-900">{batch.campaign}</p>
              <p className="mt-1 font-mono text-[10px] text-slate-400">
                {batch.batch_id} · {batch.mapping_version}
              </p>
            </div>
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              data-testid="umail-export-download"
              disabled={!health.backend || busy}
              onClick={() => void handleDownload()}
              type="button"
            >
              <Download className="size-4" /> {t("bulk.umailDownload")}
            </button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(["ready", "suppressed", "invalid", "duplicate"] as const).map((status) => (
              <div className="rounded-lg bg-slate-50 p-2" key={status}>
                <p className="text-[11px] text-slate-500">{t(`bulk.umailStatus.${status}`)}</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">
                  {batch[`${status}_count`]}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 rounded-lg bg-amber-50 p-2 text-xs font-medium text-amber-900">
            {t("bulk.umailNotSent")}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-[900px] divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-2 py-2">#</th>
                  <th className="px-2 py-2">{t("bulk.routingCompany")}</th>
                  <th className="px-2 py-2">{t("bulk.umailContact")}</th>
                  <th className="px-2 py-2">Email</th>
                  <th className="px-2 py-2">{t("bulk.umailRowStatus")}</th>
                  <th className="px-2 py-2">{t("bulk.umailExclusionReason")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {batch.rows.map((row) => (
                  <tr key={row.row_id}>
                    <td className="px-2 py-2">{row.position}</td>
                    <td className="px-2 py-2 font-medium text-slate-800">{row.company_name}</td>
                    <td className="px-2 py-2 text-slate-600">
                      {row.contact_name ?? "—"}
                      {row.is_department_contact ? ` · ${t("bulk.umailDepartmentFallback")}` : ""}
                    </td>
                    <td className="px-2 py-2 text-slate-600">{row.email ?? "—"}</td>
                    <td className="px-2 py-2 font-semibold">
                      {t(`bulk.umailStatus.${row.status}`)}
                    </td>
                    <td className="px-2 py-2 text-slate-500">
                      {row.exclusion_reason ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
