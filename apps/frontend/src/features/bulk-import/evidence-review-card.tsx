"use client";

/**
 * Single-page Evidence Review for an A-tier batch company.
 *
 * The batch card renders this inline — the reviewer no longer needs to open
 * the company workspace. Decisions use the existing research confirm API
 * (accept/reject). When every claim has a decision and the company is ready,
 * the existing resume API is called automatically (idempotent); the user
 * never clicks a separate "continue processing" step.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  X,
} from "lucide-react";

import {
  getClientErrorDetails,
  resumeProspectBatchCompany,
  type ProspectBatchCompanyResponse,
  type ProspectBatchSender,
} from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import {
  confirmResearchRun,
  getResearchRun,
  type ClaimDecisionInput,
  type ResearchClaim,
  type ResearchRun,
  type ReviewDecision,
} from "@/lib/research-api";

type ReviewChoice = ReviewDecision | "pending";

interface EvidenceReviewCardProps {
  company: ProspectBatchCompanyResponse;
  batchId: string;
  sender: ProspectBatchSender | null | undefined;
  canAct: boolean;
  onCompanyRefreshed: () => void;
  onBusyChange: (busy: boolean) => void;
}

function pendingClaims(run: ResearchRun | null): number {
  if (!run) return 0;
  const promoted = new Set(
    (run.promotions ?? []).map((item) => item.claim_position),
  );
  return run.claims.filter((claim) => !promoted.has(claim.position)).length;
}

function choicesForRun(run: ResearchRun): Record<number, ReviewChoice> {
  const promoted = new Map(
    (run.promotions ?? []).map((item) => [item.claim_position, item.decision]),
  );
  return Object.fromEntries(
    run.claims.map((claim) => [claim.position, promoted.get(claim.position) ?? "pending"]),
  );
}

export function EvidenceReviewCard({
  company,
  batchId,
  sender,
  canAct,
  onCompanyRefreshed,
  onBusyChange,
}: EvidenceReviewCardProps) {
  const { t, label } = useI18n();
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [choices, setChoices] = useState<Record<number, ReviewChoice>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [resumed, setResumed] = useState(false);

  const loadRun = useCallback(async () => {
    if (!company.research_id) return;
    try {
      const saved = await getResearchRun(company.research_id);
      setFetchError(null);
      setRun(saved);
      setChoices(choicesForRun(saved));
    } catch (caught: unknown) {
      setFetchError(t("batch.evidence.loadError"));
      getClientErrorDetails(caught); // keep mapping stable; message is business-fixed
    } finally {
      setLoading(false);
    }
  }, [company.research_id, t]);

  useEffect(() => {
    if (!company.research_id) return;
    let active = true;
    async function load() {
      try {
        const saved = await getResearchRun(company.research_id as string);
        if (!active) return;
        setRun(saved);
        setChoices(choicesForRun(saved));
      } catch (caught: unknown) {
        if (active) setFetchError(t("batch.evidence.loadError"));
        getClientErrorDetails(caught);
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [company.research_id, t]);

  const totalPending = pendingClaims(run);
  const decidedCount =
    run?.claims.filter(
      (claim) =>
        (choices[claim.position] ?? "pending") !== "pending" ||
        (run.promotions ?? []).some(
          (item) => item.claim_position === claim.position,
        ),
    ).length ?? 0;

  const setChoice = (position: number, decision: ReviewDecision) => {
    setChoices((current) => ({ ...current, [position]: decision }));
    setDecisionError(null);
  };

  const resumeCompany = useCallback(async () => {
    if (!company.company_id) return;
    setResuming(true);
    setResumeError(null);
    onBusyChange(true);
    try {
      await resumeProspectBatchCompany(batchId, company.company_id, sender ?? undefined);
      setResumed(true);
      onCompanyRefreshed();
    } catch (caught: unknown) {
      setResumeError(t("batch.evidence.resumeError"));
      getClientErrorDetails(caught);
    } finally {
      setResuming(false);
      onBusyChange(false);
    }
  }, [batchId, company.company_id, onBusyChange, onCompanyRefreshed, sender, t]);

  async function handleSubmit() {
    if (!run || submitting) return;
    const undecided = run.claims.filter(
      (claim) => (choices[claim.position] ?? "pending") === "pending",
    );
    if (undecided.length > 0) return;
    const decisions: ClaimDecisionInput[] = run.claims
      .filter((claim) => (choices[claim.position] ?? "pending") !== "pending")
      .map((claim) => ({
        claim_position: claim.position,
        decision: choices[claim.position] as ReviewDecision,
      }));
    if (decisions.length === 0) return;

    setSubmitting(true);
    setDecisionError(null);
    setResumeError(null);
    onBusyChange(true);
    try {
      await confirmResearchRun(run.research_id, {
        reviewer_name: "reviewer",
        decisions,
      });
      const refreshed = await getResearchRun(run.research_id);
      setRun(refreshed);
      setChoices(choicesForRun(refreshed));
      if (pendingClaims(refreshed) === 0) {
        await resumeCompany();
      }
    } catch (caught: unknown) {
      setDecisionError(t("batch.evidence.decisionError"));
      getClientErrorDetails(caught);
    } finally {
      setSubmitting(false);
      onBusyChange(false);
    }
  }

  if (loading) {
    return (
      <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
        <LoaderCircle className="size-3.5 animate-spin" />
        {t("batch.evidence.loading")}
      </div>
    );
  }

  if (fetchError) {
    return (
      <div
        className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
        data-testid="evidence-fetch-error"
      >
        <span className="flex items-center gap-2">
          <AlertCircle className="size-3.5" />
          {fetchError}
        </span>
        <button
          className="rounded-lg border border-rose-300 bg-white px-2.5 py-1 font-semibold text-rose-700"
          onClick={() => void loadRun()}
          type="button"
        >
          {t("batch.evidence.retry")}
        </button>
      </div>
    );
  }

  if (!run) return null;

  return (
    <div
      className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3"
      data-testid="inline-evidence-review"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-700">
          {t("batch.evidence.progress", {
            done: Math.min(decidedCount, run.claims.length),
            total: run.claims.length,
          })}
        </p>
        <span className="text-[11px] text-slate-500" data-testid="evidence-pending-count">
          {t("batch.evidence.pendingCount", { count: totalPending })}
        </span>
      </div>

      <ul className="mt-3 space-y-2">
        {run.claims.map((claim) => (
          <ClaimRow
            choice={choices[claim.position] ?? "pending"}
            claim={claim}
            disabled={!canAct || submitting || resuming}
            key={claim.position}
            label={label}
            onChoice={setChoice}
            t={t}
          />
        ))}
      </ul>

      {decisionError ? (
        <p
          className="mt-3 flex items-center gap-2 text-xs text-rose-700"
          data-testid="evidence-decision-error"
        >
          <AlertCircle className="size-3.5" />
          {decisionError}
        </p>
      ) : null}
      {resumeError ? (
        <div
          className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"
          data-testid="evidence-resume-error"
        >
          <span className="flex items-center gap-2">
            <AlertCircle className="size-3.5" />
            {resumeError}
          </span>
          <button
            className="rounded-lg border border-amber-300 bg-white px-2.5 py-1 font-semibold text-amber-800"
            disabled={resuming}
            onClick={() => void resumeCompany()}
            type="button"
          >
            <RefreshCw className="mr-1 inline size-3" />
            {t("batch.evidence.resumeRetry")}
          </button>
        </div>
      ) : null}
      {resumed ? (
        <p
          className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-medium text-emerald-900"
          data-testid="evidence-review-resumed"
        >
          {t("batch.evidence.resumed")}
        </p>
      ) : null}

      {totalPending > 0 ? (
        <button
          className="mt-3 inline-flex h-9 items-center gap-2 rounded-xl bg-emerald-800 px-4 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          data-testid="evidence-submit"
          disabled={
            !canAct ||
            submitting ||
            resuming ||
            run.claims.some(
              (claim) => (choices[claim.position] ?? "pending") === "pending",
            )
          }
          onClick={() => void handleSubmit()}
          type="button"
        >
          {submitting ? (
            <LoaderCircle className="size-3.5 animate-spin" />
          ) : (
            <Check className="size-3.5" />
          )}
          {t("batch.evidence.submit")}
        </button>
      ) : null}
    </div>
  );
}

interface ClaimRowProps {
  claim: ResearchClaim;
  choice: ReviewChoice;
  disabled: boolean;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
  label: (group: string, value: string | null | undefined) => string;
  onChoice: (position: number, decision: ReviewDecision) => void;
}

function ClaimRow({ claim, choice, disabled, t, label, onChoice }: ClaimRowProps) {
  const decided = choice !== "pending";
  return (
    <li
      className={`rounded-xl border p-3 ${
        choice === "accepted"
          ? "border-emerald-200 bg-emerald-50/50"
          : choice === "rejected"
            ? "border-rose-200 bg-rose-50/50"
            : "border-slate-200 bg-white"
      }`}
      data-testid={`inline-claim-${claim.position}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-slate-900 px-2.5 py-0.5 text-[11px] font-semibold text-white">
            {label("signalKind", claim.kind)}
          </span>
          <span className="text-[11px] text-slate-500">
            {t("research.claims.confidence")} {Math.round(claim.confidence * 100)}%
          </span>
          {decided ? (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                choice === "accepted"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-rose-100 text-rose-800"
              }`}
              data-testid={`inline-claim-${claim.position}-decided`}
            >
              {choice === "accepted"
                ? t("batch.evidence.accepted")
                : t("batch.evidence.rejected")}
            </span>
          ) : null}
        </div>
        <div className="flex gap-1">
          <button
            className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold disabled:opacity-40 ${
              choice === "accepted"
                ? "bg-emerald-700 text-white"
                : "border border-emerald-300 text-emerald-800"
            }`}
            data-testid={`inline-accept-${claim.position}`}
            disabled={disabled}
            onClick={() => onChoice(claim.position, "accepted")}
            type="button"
          >
            <Check className="mr-1 inline size-3" />
            {t("batch.evidence.accept")}
          </button>
          <button
            className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold disabled:opacity-40 ${
              choice === "rejected"
                ? "bg-rose-700 text-white"
                : "border border-rose-300 text-rose-800"
            }`}
            data-testid={`inline-reject-${claim.position}`}
            disabled={disabled}
            onClick={() => onChoice(claim.position, "rejected")}
            type="button"
          >
            <X className="mr-1 inline size-3" />
            {t("batch.evidence.reject")}
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-800">{claim.detail}</p>
      <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-xs italic text-slate-600">
        {claim.evidence_snippet}
      </blockquote>
      {claim.source_url ? (
        <a
          className="mt-1 inline-flex items-center gap-1 break-all text-[11px] text-teal-800 hover:underline"
          href={claim.source_url}
          rel="noreferrer"
          target="_blank"
        >
          {claim.source_url} <ExternalLink className="size-3" />
        </a>
      ) : (
        <p className="mt-1 text-[11px] text-slate-500">
          {t("batch.evidence.noSource")}
        </p>
      )}
    </li>
  );
}
