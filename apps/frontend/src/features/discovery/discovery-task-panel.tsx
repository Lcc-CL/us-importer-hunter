"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Search, Upload } from "lucide-react";

import {
  createDiscoveryTask,
  createManualCsvDiscoveryTask,
  getClientErrorDetails,
  getDiscoveryTask,
  getDiscoveryTaskCompanies,
  type DiscoveryCompanyResponse,
  type DiscoveryTaskResponse,
  type DiscoveryTaskStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const EXAMPLE_PROMPT = "帮我找 20 家北美五金进口商";

interface DiscoveryTaskPanelProps {
  initialTaskId?: string;
}

function safeEvidenceUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

function statusTone(status: DiscoveryTaskStatus): string {
  if (status === "completed") return "bg-emerald-100 text-emerald-800";
  if (status === "partial_failed") return "bg-amber-100 text-amber-800";
  if (status === "failed") return "bg-rose-100 text-rose-800";
  return "bg-sky-100 text-sky-800";
}

const CSV_ERROR_KEYS = {
  discovery_csv_empty: "error.discovery_csv_empty",
  discovery_csv_invalid_encoding: "error.discovery_csv_invalid_encoding",
  discovery_csv_invalid_header: "error.discovery_csv_invalid_header",
  discovery_csv_too_large: "error.discovery_csv_too_large",
  discovery_csv_too_many_rows: "error.discovery_csv_too_many_rows",
  discovery_csv_malformed: "error.discovery_csv_malformed",
} as const;

export function DiscoveryTaskPanel({ initialTaskId }: DiscoveryTaskPanelProps) {
  const { t } = useI18n();
  const [prompt, setPrompt] = useState(EXAMPLE_PROMPT);
  const [task, setTask] = useState<DiscoveryTaskResponse | null>(null);
  const [companies, setCompanies] = useState<DiscoveryCompanyResponse[]>([]);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(Boolean(initialTaskId));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!initialTaskId) return;
    let active = true;

    async function restore() {
      try {
        const [savedTask, savedCompanies] = await Promise.all([
          getDiscoveryTask(initialTaskId as string),
          getDiscoveryTaskCompanies(initialTaskId as string),
        ]);
        if (!active) return;
        setTask(savedTask);
        setCompanies(savedCompanies.companies);
        setPrompt(savedTask.original_prompt);
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
  }, [initialTaskId]);

  function persistTaskId(taskId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("task_id", taskId);
    window.history.replaceState(null, "", currentUrl);
  }

  async function finishCreation(created: DiscoveryTaskResponse) {
    const savedCompanies = await getDiscoveryTaskCompanies(created.task_id);
    setTask(created);
    setCompanies(savedCompanies.companies);
    persistTaskId(created.task_id);
  }

  async function handleCreate() {
    if (busy || !prompt.trim()) return;
    setBusy(true);
    setError(null);
    setTask(null);
    setCompanies([]);
    try {
      await finishCreation(await createDiscoveryTask(prompt.trim()));
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleManualCsv() {
    if (busy || !prompt.trim() || !csvFile) return;
    setBusy(true);
    setError(null);
    setTask(null);
    setCompanies([]);
    try {
      await finishCreation(
        await createManualCsvDiscoveryTask(prompt.trim(), csvFile),
      );
    } catch (caught: unknown) {
      const details = getClientErrorDetails(caught);
      const key = CSV_ERROR_KEYS[details.code as keyof typeof CSV_ERROR_KEYS];
      setError(key ? t(key) : details.message);
    } finally {
      setBusy(false);
    }
  }

  const statusLabel = task ? t(`discovery.status.${task.status}`) : null;

  return (
    <section
      className="mb-8 overflow-hidden rounded-3xl border border-teal-200 bg-white shadow-sm"
      data-testid="discovery-task-panel"
    >
      <div className="border-b border-teal-100 bg-teal-50/70 px-5 py-5 sm:px-7">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-700">
          {t("discovery.kicker")}
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
          {t("discovery.title")}
        </h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          {t("discovery.intro")}
        </p>
      </div>

      <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-800">
            {t("discovery.prompt")}
          </span>
          <textarea
            className="min-h-24 w-full resize-y rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm leading-6 outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-4 focus:ring-teal-100"
            data-testid="discovery-prompt"
            disabled={busy}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={EXAMPLE_PROMPT}
            value={prompt}
          />
          <span className="mt-2 block text-xs text-slate-500">
            {t("discovery.limit")}
          </span>
        </label>
        <button
          className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="create-discovery-task"
          disabled={busy || !prompt.trim()}
          onClick={handleCreate}
          type="button"
        >
          <Search className="size-4" />
          {busy ? t("discovery.creating") : t("discovery.create")}
        </button>
      </div>

      <div className="mx-5 mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 sm:mx-7">
        <p className="text-sm font-medium text-amber-950">
          {t("discovery.providerNotice")}
        </p>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            accept=".csv,text/csv"
            className="min-w-0 flex-1 rounded-xl border border-amber-300 bg-white px-3 py-2 text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-amber-100 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-amber-900"
            data-testid="discovery-csv-file"
            disabled={busy}
            onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)}
            type="file"
          />
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-amber-300 bg-white px-4 text-sm font-semibold text-amber-950 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="create-manual-csv-discovery-task"
            disabled={busy || !csvFile || !prompt.trim()}
            onClick={handleManualCsv}
            type="button"
          >
            <Upload className="size-4" /> {t("discovery.csvCreate")}
          </button>
        </div>
        <p className="mt-2 text-xs leading-5 text-amber-800">
          {t("discovery.csvHelp")}
        </p>
      </div>

      {error ? (
        <div className="mx-5 mb-6 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 sm:mx-7">
          {error}
        </div>
      ) : null}

      {task ? (
        <div className="border-t border-slate-200 px-5 py-6 sm:px-7" data-testid="discovery-task-result">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${statusTone(task.status)}`}
            >
              {statusLabel}
            </span>
            <span className="font-mono text-xs text-slate-500">{task.task_id}</span>
            <span className="text-xs text-slate-500">
              {task.provider} · {task.parsed_region} · {task.parsed_category}
            </span>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {[
              [t("discovery.count.requested"), task.requested_count],
              [t("discovery.count.discovered"), task.discovered_count],
              [t("discovery.count.ingested"), task.ingested_count],
              [t("discovery.count.duplicate"), task.duplicate_count],
              [t("discovery.count.failed"), task.failed_count],
            ].map(([label, value]) => (
              <div className="rounded-2xl bg-slate-50 p-3" key={String(label)}>
                <p className="text-xs text-slate-500">{label}</p>
                <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
              </div>
            ))}
          </div>

          {task.requested_count > task.effective_count ? (
            <p className="mt-4 text-sm text-amber-700">
              {t("discovery.capped", {
                requested: task.requested_count,
                effective: task.effective_count,
              })}
            </p>
          ) : null}

          {task.error_summary ? (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
              {task.error_code === "REAL_PROVIDER_BLOCKED_BY_API_CAPABILITY" ? (
                <p className="font-medium" data-testid="provider-unavailable-message">
                  {t("discovery.providerUnavailable")}
                </p>
              ) : null}
              {task.error_code ? (
                <p className="mt-1 font-mono text-xs">{task.error_code}</p>
              ) : null}
              <p className="mt-1">{task.error_summary}</p>
            </div>
          ) : null}

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            {companies.map((company) => {
              const evidenceUrl = safeEvidenceUrl(company.source_url);
              return (
                <article
                  className="rounded-2xl border border-slate-200 bg-white p-4"
                  data-testid="discovery-company-card"
                  key={company.candidate_id}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-slate-950">
                        {company.company_name}
                      </h3>
                      <p className="mt-1 text-xs text-slate-500">
                        {company.website ?? company.domain ?? t("common.notAvailable")}
                      </p>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                      {t(`discovery.candidate.${company.status}`)}
                    </span>
                  </div>
                  <dl className="mt-4 space-y-2 text-sm text-slate-600">
                    <div>
                      <dt className="inline font-medium text-slate-800">
                        {t("discovery.company.region")}：
                      </dt>
                      <dd className="inline">
                        {company.region ?? company.address ?? t("common.notAvailable")}
                      </dd>
                    </div>
                    <div>
                      <dt className="inline font-medium text-slate-800">
                        {t("discovery.company.description")}：
                      </dt>
                      <dd className="inline">
                        {company.product_description ??
                          company.import_evidence ??
                          t("common.notAvailable")}
                      </dd>
                    </div>
                    <div>
                      <dt className="inline font-medium text-slate-800">
                        {t("discovery.company.source")}：
                      </dt>
                      <dd className="inline">{company.source}</dd>
                    </div>
                  </dl>
                  {evidenceUrl ? (
                    <a
                      className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-teal-700 hover:text-teal-900"
                      href={evidenceUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {t("discovery.company.evidence")} <ExternalLink className="size-3.5" />
                    </a>
                  ) : company.external_id ? (
                    <p className="mt-4 break-all font-mono text-xs text-slate-500">
                      {company.external_id}
                    </p>
                  ) : null}
                  {company.failure_reason ? (
                    <p className="mt-3 text-sm text-rose-700">{company.failure_reason}</p>
                  ) : null}
                </article>
              );
            })}
          </div>

          {companies.length === 0 ? (
            <p className="mt-6 rounded-2xl bg-slate-50 p-5 text-sm text-slate-600">
              {t("discovery.empty")}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
