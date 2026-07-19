import { useState } from "react";
import { Check, Clipboard, FileText, LoaderCircle, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import type {
  DraftApprovalResponse,
  EmailDraftAnalysisResponse,
  EmailDraftDetailResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface EmailDraftCardProps {
  analysis: EmailDraftAnalysisResponse | null;
  detail: EmailDraftDetailResponse | null;
  approval: DraftApprovalResponse | null;
  approverName: string;
  isApproving: boolean;
  onApproverNameChange: (value: string) => void;
  onApprove: (outreachId: string, version: number) => Promise<void>;
}

export function EmailDraftCard({
  analysis,
  detail,
  approval,
  approverName,
  isApproving,
  onApproverNameChange,
  onApprove,
}: EmailDraftCardProps) {
  const { t, label, dateLocale } = useI18n();
  const [copied, setCopied] = useState<"subject" | "body" | null>(null);
  const outreachId = detail?.outreach_id ?? analysis?.outreach_id;
  const version = detail?.version ?? analysis?.version;
  const subject = detail?.subject ?? analysis?.subject;
  const body = detail?.body ?? analysis?.body;
  const status = approval?.approval_status ?? detail?.approval_status ?? analysis?.status;
  const approvedAt = approval?.approved_at ?? detail?.approved_at;
  const approvedBy = approval?.approved_by_name ?? detail?.approved_by_name;
  const action = analysis?.action ?? (detail ? "GENERATED" : "SKIPPED");
  const canApprove =
    status?.toLowerCase() === "generated" && Boolean(outreachId) && version != null;

  function formatDate(value: string) {
    return new Intl.DateTimeFormat(dateLocale, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }

  async function copy(value: string, field: "subject" | "body") {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(field);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopied(null);
    }
  }

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-5 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
            <FileText className="size-4" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              {t("draft.kicker")}
            </p>
            <h3 className="mt-0.5 font-semibold text-slate-950">
              {version ? t("draft.version", { n: version }) : t("draft.notGenerated")}
            </h3>
          </div>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            status === "approved"
              ? "bg-emerald-100 text-emerald-800"
              : status === "generated"
                ? "bg-amber-100 text-amber-900"
                : "bg-slate-100 text-slate-700"
          }`}
        >
          {status ? label("draftStatus", status) : label("stage", action)}
        </span>
      </div>

      <div className="px-5 py-5 sm:px-6">
        <div className="mb-5 flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-950">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          <p>{t("draftMode.notice")}</p>
        </div>

        {subject && body ? (
          <>
            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-xs font-semibold text-slate-500">
                  {t("draft.subject")}
                </p>
                <Button
                  onClick={() => copy(subject, "subject")}
                  size="sm"
                  type="button"
                  variant="ghost"
                >
                  {copied === "subject" ? <Check /> : <Clipboard />}
                  {copied === "subject" ? t("draft.copied") : t("draft.copySubject")}
                </Button>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-900">
                {subject}
              </div>
            </div>
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-xs font-semibold text-slate-500">{t("draft.body")}</p>
                <Button
                  onClick={() => copy(body, "body")}
                  size="sm"
                  type="button"
                  variant="ghost"
                >
                  {copied === "body" ? <Check /> : <Clipboard />}
                  {copied === "body" ? t("draft.copied") : t("draft.copyBody")}
                </Button>
              </div>
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-2xl border border-slate-200 bg-slate-50 p-4 font-sans text-sm leading-6 text-slate-700">
                {body}
              </pre>
            </div>
          </>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm leading-6 text-slate-600">
            {t("draft.empty")}
          </div>
        )}

        {approvedAt && approvedBy ? (
          <div className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
            <p className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
              <Check className="size-4" /> {t("draft.approvedBy", { name: approvedBy })}
            </p>
            <p className="mt-1 text-xs text-emerald-800">{formatDate(approvedAt)}</p>
          </div>
        ) : null}

        {canApprove ? (
          <div className="mt-5 border-t border-slate-200 pt-5">
            <label>
              <span className="mb-1.5 block text-xs font-semibold text-slate-700">
                {t("draft.approverName")}
              </span>
              <input
                aria-label={t("draft.approverName")}
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm shadow-sm outline-none focus:border-teal-600 focus:ring-3 focus:ring-teal-600/10"
                maxLength={200}
                onChange={(event) => onApproverNameChange(event.target.value)}
                value={approverName}
              />
            </label>
            <Button
              className="mt-3 h-10 bg-teal-700 text-white hover:bg-teal-800"
              disabled={isApproving || !approverName.trim()}
              onClick={() => {
                if (outreachId && version != null) void onApprove(outreachId, version);
              }}
              type="button"
            >
              {isApproving ? <LoaderCircle className="animate-spin" /> : <Check />}
              {isApproving ? t("draft.approving") : t("draft.approve")}
            </Button>
          </div>
        ) : null}

        {analysis?.notes.length && status !== "approved" ? (
          <ul className="mt-5 space-y-1 text-xs leading-5 text-slate-500">
            {analysis.notes.map((note, index) => (
              <li key={`note-${index}`}>• {note}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
