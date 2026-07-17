import {
  AlertCircle,
  Building2,
  CheckCircle2,
  LoaderCircle,
  RefreshCw,
  Route,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type {
  ClientErrorDetails,
  DraftApprovalResponse,
  ProspectAnalysisResponse,
  ProspectDetailResponse,
} from "@/lib/api";
import type { MvpPageState, SubmittedProspectContext } from "../types";
import { EmailDraftCard } from "./email-draft-card";
import { OpportunityCard } from "./opportunity-card";

interface AnalysisResultProps {
  analysis: ProspectAnalysisResponse | null;
  detail: ProspectDetailResponse | null;
  approval: DraftApprovalResponse | null;
  error: ClientErrorDetails | null;
  pageState: MvpPageState;
  companyId: string | null;
  context: SubmittedProspectContext | null;
  approverName: string;
  onApproverNameChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  onApprove: (outreachId: string, version: number) => Promise<void>;
}

function statusClass(status: string) {
  if (status === "COMPLETED" || status === "SAVED RESULT") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (status === "PARTIAL") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  if (status === "REJECTED" || status === "FAILED") {
    return "border-rose-200 bg-rose-50 text-rose-800";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function formatRatio(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function AnalysisResult({
  analysis,
  detail,
  approval,
  error,
  pageState,
  companyId,
  context,
  approverName,
  onApproverNameChange,
  onRefresh,
  onApprove,
}: AnalysisResultProps) {
  const hasResult = analysis !== null || detail !== null;
  const overallStatus = analysis?.overall_status ?? (detail ? "SAVED RESULT" : null);
  const selectedContactId =
    detail?.decision_maker.selected_contact_id ??
    analysis?.decision_maker.selected_contact_id ??
    null;
  const selectedContact =
    detail?.contacts.find((contact) => contact.contact_id === selectedContactId) ??
    detail?.contacts[0] ??
    null;
  const selectedRanking =
    detail?.decision_maker.rankings.find(
      (ranking) => ranking.contact_id === selectedContactId,
    ) ??
    detail?.decision_maker.rankings[0] ??
    null;
  const decisionReasons =
    analysis?.decision_maker.reasons.length
      ? analysis.decision_maker.reasons
      : (selectedRanking?.reasons ?? []);
  const isRefreshing = pageState === "refreshing";
  const isApproving = pageState === "approving";

  return (
    <div className="space-y-5" aria-live="polite">
      <div className="flex min-h-11 flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">
            Analysis result
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Persisted workflow outcomes, not a live email delivery status.
          </p>
        </div>
        {companyId ? (
          <Button
            disabled={isRefreshing || isApproving}
            onClick={() => void onRefresh()}
            type="button"
            variant="outline"
          >
            {isRefreshing ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <RefreshCw />
            )}
            {isRefreshing ? "Refreshing…" : "Refresh result"}
          </Button>
        ) : null}
      </div>

      {error ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-950">
          <div className="flex gap-3">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <div>
              <p className="text-sm font-semibold">{error.message}</p>
              <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
                <div>
                  <dt className="inline font-semibold">Code: </dt>
                  <dd className="inline">{error.code}</dd>
                </div>
                <div>
                  <dt className="inline font-semibold">Request ID: </dt>
                  <dd className="inline break-all">{error.request_id ?? "not available"}</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      ) : null}

      {!hasResult ? (
        <div className="flex min-h-[420px] flex-col items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 px-8 text-center">
          <div className="flex size-14 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
            <Route className="size-6" />
          </div>
          <h2 className="mt-5 text-lg font-semibold text-slate-950">
            Your analysis will appear here
          </h2>
          <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">
            Submit a prospect to see company facts, opportunity qualification,
            decision-maker selection, and a reviewable email draft.
          </p>
        </div>
      ) : (
        <>
          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                  Overall status
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <CheckCircle2 className="size-5 text-teal-700" />
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-bold tracking-wide ${statusClass(
                      overallStatus ?? "",
                    )}`}
                  >
                    {overallStatus}
                  </span>
                </div>
              </div>
              {analysis ? (
                <div className="text-right text-xs text-slate-500">
                  <p>Request ID</p>
                  <p className="mt-1 max-w-56 break-all font-mono text-[11px] text-slate-700">
                    {analysis.request_id}
                  </p>
                </div>
              ) : null}
            </div>

            {analysis?.warnings.length ? (
              <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">
                  Workflow notes
                </p>
                <ul className="mt-2 space-y-1 text-sm leading-6 text-amber-950">
                  {analysis.warnings.map((warning) => (
                    <li key={warning}>• {warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex items-start gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-700">
                <Building2 className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      Company
                    </p>
                    <h3 className="mt-1 text-lg font-semibold text-slate-950">
                      {detail?.company.name ?? analysis?.company.name}
                    </h3>
                  </div>
                  {analysis ? (
                    <span className="rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">
                      {analysis.company.action}
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 break-all font-mono text-[11px] text-slate-500">
                  {detail?.company.company_id ?? analysis?.company.company_id}
                </p>
                {detail?.company.sources.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {detail.company.sources.map((source) => (
                      <span
                        className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600"
                        key={source}
                      >
                        {source}
                      </span>
                    ))}
                  </div>
                ) : null}
                {analysis?.company.notes.length ? (
                  <ul className="mt-4 space-y-1 text-sm text-slate-600">
                    {analysis.company.notes.map((note) => (
                      <li key={note}>• {note}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
          </section>

          <OpportunityCard
            analysis={analysis?.opportunity ?? null}
            detail={detail?.latest_assessment ?? null}
          />

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex items-start gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-violet-50 text-violet-700">
                <UserRound className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      Contact · Decision maker
                    </p>
                    <h3 className="mt-1 font-semibold text-slate-950">
                      {selectedContact?.name ?? context?.contact?.name ?? "No contact selected"}
                    </h3>
                    <p className="mt-0.5 text-sm text-slate-500">
                      {selectedContact?.title ?? context?.contact?.title ?? "Title unavailable"}
                    </p>
                  </div>
                  <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-800">
                    {analysis?.decision_maker.action ??
                      (selectedContactId ? "SELECTED" : "RESEARCH MORE")}
                  </span>
                </div>

                <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-xs font-semibold text-slate-500">Contact status</dt>
                    <dd className="mt-1 font-medium capitalize text-slate-900">
                      {selectedContact?.status ?? analysis?.contact.action ?? "Not available"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-semibold text-slate-500">
                      Recommended channel
                    </dt>
                    <dd className="mt-1 font-medium capitalize text-slate-900">
                      {analysis?.decision_maker.recommended_channel ??
                        selectedRanking?.recommended_channel ??
                        "Not available"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-semibold text-slate-500">
                      Selection confidence
                    </dt>
                    <dd className="mt-1 font-medium text-slate-900">
                      {formatRatio(
                        analysis?.decision_maker.confidence ?? selectedRanking?.confidence,
                      )}
                    </dd>
                  </div>
                </dl>

                {selectedContactId ? (
                  <p className="mt-4 break-all font-mono text-[11px] text-slate-500">
                    Selected contact: {selectedContactId}
                  </p>
                ) : null}
                {decisionReasons.length ? (
                  <ul className="mt-4 space-y-1 text-sm leading-6 text-slate-600">
                    {decisionReasons.map((reason) => (
                      <li key={reason}>• {reason}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
          </section>

          <EmailDraftCard
            analysis={analysis?.email_draft ?? null}
            detail={detail?.latest_email_draft ?? null}
            approval={approval}
            approverName={approverName}
            isApproving={isApproving}
            onApprove={onApprove}
            onApproverNameChange={onApproverNameChange}
          />
        </>
      )}
    </div>
  );
}
