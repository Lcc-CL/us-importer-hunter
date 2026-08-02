"use client";

import { useCallback, useEffect, useState } from "react";
import { FileCheck2, Upload } from "lucide-react";

import {
  createBulkImportSession,
  getBulkImportRows,
  getBulkImportSession,
  getClientErrorDetails,
  type ImportSessionResponse,
  type RawImportRowResponse,
  type RawImportRowStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const DEFAULT_SOURCE = "netease_foreign_trade";
const PAGE_SIZE = 20;

interface BulkImportPanelProps {
  initialSessionId?: string;
}

export function BulkImportPanel({ initialSessionId }: BulkImportPanelProps) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [mappingText, setMappingText] = useState("");
  const [session, setSession] = useState<ImportSessionResponse | null>(null);
  const [rows, setRows] = useState<RawImportRowResponse[]>([]);
  const [rowTotal, setRowTotal] = useState(0);
  const [rowStatus, setRowStatus] = useState<RawImportRowStatus | "">("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(Boolean(initialSessionId));
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!initialSessionId) return;
    let active = true;
    async function load() {
      try {
        await restore(initialSessionId as string);
      } catch (caught: unknown) {
        if (active) setError(getClientErrorDetails(caught).message);
      } finally {
        if (active) setBusy(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [initialSessionId, restore]);

  useEffect(() => {
    if (!session || !["receiving", "processing"].includes(session.status)) return;
    const timer = window.setInterval(() => {
      void restore(session.session_id, page, rowStatus).catch((caught: unknown) => {
        setError(getClientErrorDetails(caught).message);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [page, restore, rowStatus, session]);

  function persistSessionId(sessionId: string) {
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set("import_session_id", sessionId);
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
      persistSessionId(created.session_id);
      await loadRows(created.session_id, 1, "");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
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
