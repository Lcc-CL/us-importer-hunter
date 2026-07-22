"use client";

import { useRef, useState } from "react";
import { FileUp, LoaderCircle } from "lucide-react";

import type { EvidenceUploadResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface ImportEvidencePanelProps {
  companyId: string | null;
  disabled: boolean;
  result: EvidenceUploadResponse | null;
  error: string | null;
  onUpload: (file: File) => Promise<void>;
}

const signalLabels: Record<string, string> = {
  import_activity: "持续进口活动",
  china_dependency: "中国来源依赖",
  logistics_complexity: "物流复杂度",
};

const statusLabels: Record<string, string> = {
  VERIFIED: "已验证",
  USABLE: "可使用",
  REVIEW: "需要复核",
  REJECTED: "已拒绝",
  qualified: "已达标",
  review: "需要复核",
  research_more: "需要补充证据",
  disqualified: "不适合开发",
};

function reasonLabel(reason: string): string {
  const dimension = Object.entries({
    import_activity: "进口活动",
    china_dependency: "中国来源依赖",
    shipping_fit: "运输匹配度",
    cargo_value_potential: "货值潜力",
    company_scale: "公司规模",
    growth_signal: "增长信号",
    logistics_complexity: "物流复杂度",
  }).find(([key]) => reason.includes(key));
  if (reason.startsWith("no ") && dimension) return `尚缺少${dimension[1]}证据。`;
  if (reason.includes("data completeness")) return "当前证据完整度仍不足。";
  return "当前资格条件尚未全部满足，需要人工复核或补充证据。";
}

export function ImportEvidencePanel({
  companyId,
  disabled,
  result,
  error,
  onUpload,
}: ImportEvidencePanelProps) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  async function submit() {
    if (!file || !companyId || uploading || disabled) return;
    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
    }
  }

  const scoreChanged =
    result?.previous_qualification_score !== null &&
    result?.qualification_score !== null;

  return (
    <section
      className="mt-6 rounded-3xl border border-teal-200 bg-white p-5 shadow-sm sm:p-7"
      data-testid="import-evidence-panel"
    >
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-teal-50 p-2 text-teal-700">
          <FileUp className="size-5" />
        </div>
        <div>
          <h2 className="font-semibold text-slate-950">{t("evidence.title")}</h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">{t("evidence.hint")}</p>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        <input
          accept=".csv,text/csv"
          className="block min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white"
          data-testid="evidence-file"
          disabled={disabled || uploading || !companyId}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          ref={inputRef}
          type="file"
        />
        <button
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="evidence-upload"
          disabled={!file || !companyId || disabled || uploading}
          onClick={() => void submit()}
          type="button"
        >
          {uploading ? <LoaderCircle className="size-4 animate-spin" /> : null}
          {uploading ? t("evidence.uploading") : t("evidence.upload")}
        </button>
      </div>
      {!companyId ? (
        <p className="mt-3 text-xs text-amber-700">{t("evidence.saveFirst")}</p>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-5 space-y-4" data-testid="evidence-result">
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label={t("evidence.records")} value={result.records_received} />
            <Metric label={t("evidence.shipments")} value={result.shipments_matched} />
            <Metric
              label={t("evidence.quality")}
              value={
                result.quality_status
                  ? (statusLabels[result.quality_status] ?? result.quality_status)
                  : t("evidence.unknown")
              }
            />
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t("evidence.signals")}
            </p>
            <div className="mt-2 flex flex-wrap gap-2" data-testid="evidence-signals">
              {result.promoted_signals.length ? result.promoted_signals.map((signal) => (
                <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800" key={signal}>
                  {signalLabels[signal] ?? signal}
                </span>
              )) : <span className="text-sm text-slate-500">{t("evidence.noSignals")}</span>}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-950 p-4 text-white" data-testid="evidence-score">
            <p className="text-xs text-slate-300">{t("evidence.qualification")}</p>
            <p className="mt-1 text-lg font-semibold">
              {scoreChanged
                ? `${result.previous_qualification_score?.toFixed(1)} → ${result.qualification_score?.toFixed(1)}`
                : (result.qualification_score?.toFixed(1) ?? "—")}
              <span className="ml-2 text-sm font-medium text-teal-300">
                {result.qualification_status
                  ? (statusLabels[result.qualification_status] ?? result.qualification_status)
                  : t("evidence.unknown")}
              </span>
            </p>
          </div>

          {result.qualification_status !== "qualified" && result.qualification_reasons.length ? (
            <div className="text-sm text-slate-600">
              <p className="font-semibold text-slate-800">{t("evidence.missing")}</p>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {[...new Set(result.qualification_reasons.map(reasonLabel))]
                  .slice(0, 4)
                  .map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            </div>
          ) : null}
          {result.draft_status !== "skipped" ? (
            <p className="text-sm font-semibold text-teal-800" data-testid="evidence-draft-status">
              {t("evidence.draftReady")}
            </p>
          ) : null}
          {result.warnings.length ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-amber-700">
              {result.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 font-semibold text-slate-900">{value}</p>
    </div>
  );
}
