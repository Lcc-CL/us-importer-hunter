"use client";

/**
 * Research panel: name + website → reviewable claims → the existing form.
 *
 * The panel proposes; the human decides; the existing prospect form and its
 * Analyze button stay exactly as they were. Nothing here triggers analysis,
 * scoring, draft generation or company creation.
 */

import { useState } from "react";
import {
  AlertCircle,
  Check,
  ExternalLink,
  FileSearch,
  LoaderCircle,
  Pencil,
  ShieldAlert,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { getClientErrorDetails, type ClientErrorDetails } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import {
  confirmResearchRun,
  startResearch,
  type ApplicationPayload,
  type ClaimDecisionInput,
  type ClaimKind,
  type ResearchClaim,
  type ResearchRun,
  type ReviewDecision,
} from "@/lib/research-api";
import { SIGNAL_KINDS } from "@/features/mvp-analysis/signal-kinds";

type PanelState = "idle" | "researching" | "reviewing" | "confirming" | "applied" | "error";

/** A claim plus the reviewer's working state. Never defaults to accepted. */
interface ClaimReview {
  decision: ReviewDecision | "pending";
  editedKind: ClaimKind;
  editedDetail: string;
}

interface ResearchPanelProps {
  /** Fills the existing prospect form. Never submits it. */
  onApply: (payload: ApplicationPayload) => void;
}

const inputClass =
  "h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 " +
  "shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-600 " +
  "focus:ring-3 focus:ring-teal-600/10 disabled:bg-slate-100";
const labelClass = "mb-1.5 block text-xs font-semibold tracking-wide text-slate-700";

function statusTone(status: string): string {
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (status === "partial") return "border-amber-200 bg-amber-50 text-amber-900";
  return "border-rose-200 bg-rose-50 text-rose-800";
}

export function ResearchPanel({ onApply }: ResearchPanelProps) {
  const { t, label } = useI18n();
  const [state, setState] = useState<PanelState>("idle");
  const [companyName, setCompanyName] = useState("");
  const [website, setWebsite] = useState("");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [reviews, setReviews] = useState<Record<number, ClaimReview>>({});
  const [error, setError] = useState<ClientErrorDetails | null>(null);
  const [applied, setApplied] = useState<{ sources: number; signals: number } | null>(null);

  const busy = state === "researching" || state === "confirming";

  async function handleStart() {
    if (busy || !companyName.trim() || !website.trim()) return;
    setState("researching");
    setError(null);
    setRun(null);
    setReviews({});
    setApplied(null);
    try {
      const created = await startResearch({
        company_name: companyName.trim(),
        website: website.trim(),
      });
      setRun(created);
      // Deliberately empty: every claim starts as "pending". Auto-accepting
      // would make the reviewer a rubber stamp.
      setReviews(
        Object.fromEntries(
          created.claims.map((claim) => [
            claim.position,
            { decision: "pending", editedKind: claim.kind, editedDetail: claim.detail },
          ]),
        ),
      );
      setState("reviewing");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught));
      setState("error");
    }
  }

  function setDecision(position: number, decision: ReviewDecision | "pending") {
    setReviews((current) => ({
      ...current,
      [position]: { ...current[position], decision },
    }));
  }

  function updateEdit(position: number, patch: Partial<ClaimReview>) {
    setReviews((current) => ({
      ...current,
      [position]: { ...current[position], ...patch },
    }));
  }

  async function handleConfirm() {
    if (!run || busy) return;
    const decisions: ClaimDecisionInput[] = [];
    for (const claim of run.claims) {
      const review = reviews[claim.position];
      if (!review || review.decision === "pending") continue;
      if (review.decision === "edited") {
        decisions.push({
          claim_position: claim.position,
          decision: "edited",
          edited_detail: review.editedDetail.trim(),
          edited_kind: review.editedKind,
        });
      } else {
        decisions.push({ claim_position: claim.position, decision: review.decision });
      }
    }

    if (decisions.length === 0) {
      setError({
        code: "no_decisions",
        message: t("research.confirm.needsDecision"),
        request_id: null,
      });
      return;
    }

    setState("confirming");
    setError(null);
    try {
      // No target_company_id: this phase never writes into an existing company.
      const response = await confirmResearchRun(run.research_id, {
        reviewer_name: "reviewer",
        decisions,
      });
      const payload = response.application_payload;
      if (payload) {
        onApply(payload);
        setApplied({ sources: payload.sources.length, signals: payload.signals.length });
      }
      setState("applied");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught));
      setState("error");
    }
  }

  return (
    <section
      aria-label="research-panel"
      data-testid="research-panel"
      className="mb-6 overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="border-b border-slate-200 bg-slate-950 px-5 py-4 text-white sm:px-7">
        <div className="flex items-center gap-2">
          <FileSearch className="size-4 text-teal-300" />
          <h2 className="font-semibold tracking-tight">{t("research.title")}</h2>
        </div>
        <p
          data-testid="research-security-notice"
          className="mt-2 flex items-start gap-2 rounded-xl bg-amber-500/15 px-3 py-2 text-xs
                     leading-5 text-amber-200"
        >
          <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
          {t("research.notice")}
        </p>
      </div>

      <div className="px-5 py-5 sm:px-7">
        <div className="grid gap-4 sm:grid-cols-2">
          <label>
            <span className={labelClass}>{t("research.companyName")}</span>
            <input
              aria-label="Research target name"
              className={inputClass}
              disabled={busy}
              onChange={(event) => setCompanyName(event.target.value)}
              placeholder="Acme Hardware"
              value={companyName}
            />
          </label>
          <label>
            <span className={labelClass}>{t("research.website")}</span>
            <input
              aria-label="Research target website"
              className={inputClass}
              disabled={busy}
              onChange={(event) => setWebsite(event.target.value)}
              placeholder="https://acme.example"
              value={website}
            />
          </label>
        </div>

        <Button
          className="mt-4 h-10 bg-teal-700 text-white hover:bg-teal-800"
          disabled={busy || !companyName.trim() || !website.trim()}
          onClick={() => void handleStart()}
          type="button"
        >
          {state === "researching" ? <LoaderCircle className="animate-spin" /> : <FileSearch />}
          {state === "researching" ? t("research.running") : t("research.start")}
        </Button>

        {error ? (
          <div
            data-testid="research-error"
            className="mt-4 flex gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4
                       text-sm text-rose-950"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <div>
              <p className="font-semibold">{t("research.error")}</p>
              <p className="mt-1">{error.message}</p>
            </div>
          </div>
        ) : null}

        {!run && state !== "researching" && !error ? (
          <p className="mt-4 text-sm leading-6 text-slate-500">{t("research.empty")}</p>
        ) : null}

        {run ? (
          <ResearchResult
            applied={applied}
            busy={busy}
            label={label}
            onConfirm={() => void handleConfirm()}
            onDecision={setDecision}
            onEdit={updateEdit}
            reviews={reviews}
            run={run}
            state={state}
            t={t}
          />
        ) : null}
      </div>
    </section>
  );
}

interface ResearchResultProps {
  run: ResearchRun;
  reviews: Record<number, ClaimReview>;
  state: PanelState;
  busy: boolean;
  applied: { sources: number; signals: number } | null;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
  label: (group: string, value: string | null | undefined) => string;
  onDecision: (position: number, decision: ReviewDecision | "pending") => void;
  onEdit: (position: number, patch: Partial<ClaimReview>) => void;
  onConfirm: () => void;
}

function ResearchResult({
  run,
  reviews,
  state,
  busy,
  applied,
  t,
  label,
  onDecision,
  onEdit,
  onConfirm,
}: ResearchResultProps) {
  const failureKey = run.failure_code
    ? (`research.failure.${run.failure_code}` as MessageKey)
    : null;

  return (
    <div className="mt-5 space-y-5" data-testid="research-result">
      {/* --- status --- */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-slate-500">{t("research.status")}</span>
        <span
          data-testid="research-status"
          className={`rounded-full border px-3 py-1 text-xs font-bold ${statusTone(run.status)}`}
        >
          {t(`research.status.${run.status}` as MessageKey)}
        </span>
        {failureKey ? (
          <span
            data-testid="research-failure-code"
            className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs
                       font-medium text-amber-900"
          >
            {t(failureKey)}
          </span>
        ) : null}
        {run.extractor ? (
          <span className="font-mono text-[11px] text-slate-500">
            {t("research.extractor")}: {run.extractor.provider} · {run.extractor.model}
          </span>
        ) : null}
      </div>

      {/* --- pages --- */}
      <div>
        <p className="text-xs font-semibold text-slate-600">
          {t("research.pages", { count: run.pages.length })}
        </p>
        {run.pages.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">{t("research.pages.empty")}</p>
        ) : (
          <ul className="mt-2 space-y-1.5" data-testid="research-pages">
            {run.pages.map((page) => (
              <li
                className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200
                           bg-slate-50/70 px-3 py-2 text-xs"
                key={page.position}
              >
                <span className="rounded bg-slate-200 px-1.5 py-0.5 font-mono text-[10px]">
                  {page.http_status}
                </span>
                <a
                  className="inline-flex items-center gap-1 break-all text-teal-800 hover:underline"
                  href={page.url}
                  rel="noreferrer"
                  target="_blank"
                >
                  {page.url} <ExternalLink className="size-3" />
                </a>
                <span className="text-slate-500">{page.discovery_reason}</span>
                {page.truncated ? (
                  <span className="text-amber-800">{t("research.pages.truncated")}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* --- claims --- */}
      <div>
        <p className="text-xs font-semibold text-slate-600">
          {t("research.claims", { count: run.claims.length })}
        </p>
        {run.claims.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">{t("research.claims.empty")}</p>
        ) : (
          <ul className="mt-2 space-y-3" data-testid="research-claims">
            {run.claims.map((claim) => (
              <ClaimRow
                claim={claim}
                key={claim.position}
                label={label}
                onDecision={onDecision}
                onEdit={onEdit}
                review={reviews[claim.position]}
                t={t}
              />
            ))}
          </ul>
        )}
      </div>

      {run.rejected_claims.length > 0 ? (
        <details className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-600">
            {t("research.claims.rejected", { count: run.rejected_claims.length })}
          </summary>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
            {run.rejected_claims.map((rejection, index) => (
              <li key={`rejected-${index}`}>• {rejection.warning}</li>
            ))}
          </ul>
        </details>
      ) : null}

      {run.warnings.length > 0 ? (
        <details className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold text-amber-900">
            {t("research.warnings")}
          </summary>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-950">
            {run.warnings.map((warning, index) => (
              <li key={`warning-${index}`}>• {warning}</li>
            ))}
          </ul>
        </details>
      ) : null}

      {/* --- confirm --- */}
      {run.claims.length > 0 ? (
        <div className="border-t border-slate-200 pt-4">
          <Button
            className="h-10 bg-teal-700 text-white hover:bg-teal-800"
            data-testid="research-confirm"
            disabled={busy}
            onClick={onConfirm}
            type="button"
          >
            {state === "confirming" ? <LoaderCircle className="animate-spin" /> : <Check />}
            {state === "confirming" ? t("research.confirming") : t("research.confirm")}
          </Button>
        </div>
      ) : null}

      {applied ? (
        <div
          data-testid="research-applied"
          className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm
                     text-emerald-900"
        >
          <p className="font-semibold">
            {t("research.applied", { sources: applied.sources, signals: applied.signals })}
          </p>
          <p className="mt-1 text-xs text-emerald-800">{t("research.applied.note")}</p>
        </div>
      ) : null}
    </div>
  );
}

interface ClaimRowProps {
  claim: ResearchClaim;
  review: ClaimReview | undefined;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
  label: (group: string, value: string | null | undefined) => string;
  onDecision: (position: number, decision: ReviewDecision | "pending") => void;
  onEdit: (position: number, patch: Partial<ClaimReview>) => void;
}

function ClaimRow({ claim, review, t, label, onDecision, onEdit }: ClaimRowProps) {
  const decision = review?.decision ?? "pending";
  const tone =
    decision === "accepted"
      ? "border-emerald-300 bg-emerald-50/60"
      : decision === "rejected"
        ? "border-rose-200 bg-rose-50/50"
        : decision === "edited"
          ? "border-sky-300 bg-sky-50/50"
          : "border-slate-200 bg-white";

  return (
    <li
      className={`rounded-2xl border p-3 ${tone}`}
      data-testid={`research-claim-${claim.position}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-slate-900 px-2.5 py-0.5 text-xs font-semibold text-white">
            {label("signalKind", claim.kind)}
          </span>
          <span className="text-xs text-slate-500">
            {t("research.claims.confidence")} {Math.round(claim.confidence * 100)}%
          </span>
        </div>
        <div className="flex gap-1">
          <DecisionButton
            active={decision === "accepted"}
            icon={<Check className="size-3.5" />}
            label={t("research.decision.accepted")}
            onClick={() => onDecision(claim.position, "accepted")}
            testId={`accept-${claim.position}`}
            tone="emerald"
          />
          <DecisionButton
            active={decision === "edited"}
            icon={<Pencil className="size-3.5" />}
            label={t("research.decision.edited")}
            onClick={() => onDecision(claim.position, "edited")}
            testId={`edit-${claim.position}`}
            tone="sky"
          />
          <DecisionButton
            active={decision === "rejected"}
            icon={<X className="size-3.5" />}
            label={t("research.decision.rejected")}
            onClick={() => onDecision(claim.position, "rejected")}
            testId={`reject-${claim.position}`}
            tone="rose"
          />
        </div>
      </div>

      {decision === "edited" ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,0.4fr)_minmax(0,1fr)]">
          <label>
            <span className={labelClass}>{t("research.edit.kind")}</span>
            <select
              aria-label={`Claim ${claim.position} kind`}
              className={inputClass}
              onChange={(event) =>
                onEdit(claim.position, { editedKind: event.target.value as ClaimKind })
              }
              value={review?.editedKind ?? claim.kind}
            >
              {SIGNAL_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {label("signalKind", kind)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={labelClass}>{t("research.edit.detail")}</span>
            <input
              aria-label={`Claim ${claim.position} detail`}
              className={inputClass}
              onChange={(event) =>
                onEdit(claim.position, { editedDetail: event.target.value })
              }
              value={review?.editedDetail ?? claim.detail}
            />
          </label>
        </div>
      ) : (
        <p className="mt-2 text-sm leading-6 text-slate-800">{claim.detail}</p>
      )}

      {/* Evidence and source stay read-only in every state — they are what the
          page actually said, not something a reviewer may rewrite. */}
      <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-xs italic text-slate-600">
        {claim.evidence_snippet}
      </blockquote>
      <a
        className="mt-1 inline-flex items-center gap-1 break-all text-[11px] text-teal-800
                   hover:underline"
        href={claim.source_url}
        rel="noreferrer"
        target="_blank"
      >
        {claim.source_url} <ExternalLink className="size-3" />
      </a>
      {decision === "edited" ? (
        <p className="mt-1 text-[11px] text-slate-500">{t("research.edit.readonly")}</p>
      ) : null}
    </li>
  );
}

function DecisionButton({
  active,
  icon,
  label,
  onClick,
  testId,
  tone,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  testId: string;
  tone: "emerald" | "sky" | "rose";
}) {
  const tones: Record<string, string> = {
    emerald: active
      ? "bg-emerald-700 text-white"
      : "bg-white text-emerald-800 hover:bg-emerald-50",
    sky: active ? "bg-sky-700 text-white" : "bg-white text-sky-800 hover:bg-sky-50",
    rose: active ? "bg-rose-700 text-white" : "bg-white text-rose-800 hover:bg-rose-50",
  };
  return (
    <button
      className={`inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1
                  text-xs font-medium transition ${tones[tone]}`}
      data-testid={testId}
      onClick={onClick}
      type="button"
    >
      {icon}
      {label}
    </button>
  );
}
