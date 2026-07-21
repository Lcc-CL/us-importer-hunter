"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Mail,
  Phone,
  LinkIcon,
  ShieldBan,
  UserRound,
} from "lucide-react";
import { useState } from "react";

import type {
  CandidateScoreResponse,
  DecisionMakerSelectionResponse,
} from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";

function roleLabel(role: string, t: (key: MessageKey, params?: Record<string, string | number>) => string): string {
  const key = `role.${role}` as MessageKey;
  const translated = t(key);
  return translated === key ? role.replace(/_/g, " ") : translated;
}

function CandidateCard({
  candidate,
  status,
  isPrimary,
  onConfirm,
}: {
  candidate: CandidateScoreResponse;
  status: string;
  isPrimary?: boolean;
  onConfirm?: (id: string) => void;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);

  const statusBadge = isPrimary
    ? "bg-green-50 text-green-700 border-green-200"
    : status === "rejected" || status === "no_relevant_contact"
      ? "bg-red-50 text-red-700 border-red-200"
      : "bg-slate-50 text-slate-600 border-slate-200";

  const statusText = isPrimary
    ? t("result.recommended")
    : status === "alternatives_available"
      ? t("result.alternatives")
      : status === "rejected" || status === "no_relevant_contact"
        ? t("result.rejected")
        : t("result.supporting");

  const { score_breakdown: b = {} } = candidate;
  const dims = [
    { key: "role_relevance", label: t("result.roleRelevance"), score: b.role_relevance ?? 0 },
    { key: "seniority", label: t("result.seniority"), score: b.seniority ?? 0 },
    { key: "company_size_fit", label: t("result.companySizeFit"), score: b.company_size_fit ?? 0 },
    { key: "import_logistics_fit", label: t("result.importLogisticsFit"), score: b.import_logistics_fit ?? 0 },
    { key: "reachability", label: t("result.reachability"), score: b.reachability ?? 0 },
    { key: "source_confidence", label: t("result.sourceConfidence"), score: b.source_confidence ?? 0 },
  ];

  return (
    <div className={`rounded-xl border p-4 ${statusBadge}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <UserRound className="size-4 shrink-0 text-slate-400" />
            <span className="text-sm font-semibold text-slate-900">
              {candidate.original_title || candidate.normalized_title || t("result.noTitle")}
            </span>
            {isPrimary && (
              <CheckCircle2 className="size-4 shrink-0 text-green-600" />
            )}
          </div>
          {candidate.roles?.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {candidate.roles.map((role) => (
                <span
                  key={role}
                  className="rounded-full bg-white/60 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
                >
                  {roleLabel(role, t)}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="text-right">
          <span className="text-lg font-bold text-slate-900">
            {candidate.overall_score.toFixed(0)}
          </span>
          <span className="text-[11px] text-slate-500">/100</span>
        </div>
      </div>

      {candidate.rejection_reasons?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {candidate.rejection_reasons.map((r) => (
            <span
              key={r}
              className="inline-flex items-center gap-1 rounded-full bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-700"
            >
              <ShieldBan className="size-3" />
              {r.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="mt-2 flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-slate-700"
      >
        {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
        {expanded ? t("result.collapseScore") : t("result.expandScore")}
      </button>

      {expanded && (
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {dims.map((d) => (
            <div key={d.key} className="rounded bg-white/50 px-2 py-1">
              <div className="text-[10px] text-slate-500">{d.label}</div>
              <div className="text-xs font-semibold text-slate-800">{d.score.toFixed(0)}</div>
            </div>
          ))}
          <div className="rounded bg-white/50 px-2 py-1">
            <div className="text-[10px] text-slate-500">{t("result.classConfidence")}</div>
            <div className="text-xs font-semibold text-slate-800">
              {(candidate.classification_confidence * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      )}

      {onConfirm && !isPrimary && status !== "rejected" && status !== "no_relevant_contact" && (
        <button
          type="button"
          onClick={() => onConfirm(candidate.contact_id)}
          className="mt-2 w-full rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-700"
        >
          {t("result.confirmContact")}
        </button>
      )}
    </div>
  );
}

export function CandidateCards({
  selection,
  selectedContactId,
  onConfirm,
}: {
  selection: DecisionMakerSelectionResponse | null;
  selectedContactId: string | null;
  onConfirm?: (contactId: string) => void;
}) {
  const { t } = useI18n();

  if (!selection) return null;

  const { primary_contact, alternative_contacts, supporting_contacts, rejected_contacts, review_required } =
    selection;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <UserRound className="size-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-800">{t("result.dmSelection")}</h3>
      </div>

      {review_required && (
        <div className="mb-4 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          <AlertTriangle className="size-4 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">{t("result.reviewRequired")}</p>
            {selection.review_reasons?.length > 0 && (
              <ul className="mt-1 list-inside list-disc text-xs text-amber-700">
                {selection.review_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {primary_contact && (
        <div className="mb-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            {t("result.primary")}
          </p>
          <CandidateCard
            candidate={primary_contact}
            status="selected"
            isPrimary
          />
        </div>
      )}

      {alternative_contacts.length > 0 && (
        <div className="mb-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            {t("result.alternatives")} ({alternative_contacts.length})
          </p>
          <div className="space-y-2">
            {alternative_contacts.map((c) => (
              <CandidateCard
                key={c.contact_id}
                candidate={c}
                status="alternatives_available"
                onConfirm={onConfirm}
              />
            ))}
          </div>
        </div>
      )}

      {supporting_contacts.length > 0 && (
        <div className="mb-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            {t("result.supporting")} ({supporting_contacts.length})
          </p>
          <div className="space-y-2">
            {supporting_contacts.map((c) => (
              <CandidateCard
                key={c.contact_id}
                candidate={c}
                status="supporting"
              />
            ))}
          </div>
        </div>
      )}

      {rejected_contacts.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-600">
            {t("result.rejected")} ({rejected_contacts.length})
          </summary>
          <div className="mt-2 space-y-2">
            {rejected_contacts.map((c) => (
              <CandidateCard
                key={c.contact_id}
                candidate={c}
                status="no_relevant_contact"
              />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
