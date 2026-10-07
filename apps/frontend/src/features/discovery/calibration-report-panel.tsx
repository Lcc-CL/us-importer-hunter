"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, ExternalLink, ShieldCheck } from "lucide-react";

import {
  calibrationExportUrl,
  getCalibrationReport,
  getClientErrorDetails,
  saveCalibrationEvaluation,
  type CalibrationCompanyReport,
  type CalibrationEvaluationRequest,
  type CalibrationReportResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface CalibrationReportPanelProps {
  calibrationId: string;
  refreshToken?: string | null;
}

function percentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function duration(value: number | null): string {
  if (value === null) return "—";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function truthTone(value: number): string {
  return value === 0
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : "border-rose-200 bg-rose-50 text-rose-900";
}

function EvaluationForm({
  calibrationId,
  company,
  onSaved,
}: {
  calibrationId: string;
  company: CalibrationCompanyReport;
  onSaved: () => Promise<void>;
}) {
  const { t } = useI18n();
  const saved = company.evaluation;
  const [values, setValues] = useState<CalibrationEvaluationRequest>({
    research_accuracy: saved?.research_accuracy ?? 3,
    opportunity_reasonableness: saved?.opportunity_reasonableness ?? 3,
    contact_usability: saved?.contact_usability ?? 3,
    draft_personalization: saved?.draft_personalization ?? 3,
    draft_professionalism: saved?.draft_professionalism ?? 3,
    ready_for_real_outreach: saved?.ready_for_real_outreach ?? false,
    reviewer_name: saved?.reviewer_name ?? "",
    notes: saved?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function scoreField(
    key:
      | "research_accuracy"
      | "opportunity_reasonableness"
      | "contact_usability"
      | "draft_personalization"
      | "draft_professionalism",
    label: string,
  ) {
    return (
      <label className="block text-xs text-slate-600">
        <span className="mb-1 block">{label}</span>
        <select
          className="h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-sm"
          onChange={(event) =>
            setValues((current) => ({
              ...current,
              [key]: Number(event.target.value),
            }))
          }
          value={values[key]}
        >
          {[1, 2, 3, 4, 5].map((score) => (
            <option key={score} value={score}>
              {score}
            </option>
          ))}
        </select>
      </label>
    );
  }

  async function save() {
    if (!values.reviewer_name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await saveCalibrationEvaluation(calibrationId, company.company_id, {
        ...values,
        reviewer_name: values.reviewer_name.trim(),
        notes: values.notes?.trim() || null,
      });
      await onSaved();
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-2xl border border-violet-200 bg-violet-50/60 p-4">
      <p className="text-sm font-semibold text-violet-950">
        {t("calibration.evaluation.title")}
      </p>
      <p className="mt-1 text-xs leading-5 text-violet-800">
        {t("calibration.evaluation.internalNotice")}
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {scoreField("research_accuracy", t("calibration.evaluation.research"))}
        {scoreField(
          "opportunity_reasonableness",
          t("calibration.evaluation.opportunity"),
        )}
        {scoreField("contact_usability", t("calibration.evaluation.contact"))}
        {scoreField("draft_personalization", t("calibration.evaluation.personalization"))}
        {scoreField("draft_professionalism", t("calibration.evaluation.professionalism"))}
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
        <label className="block text-xs text-slate-600">
          <span className="mb-1 block">{t("calibration.evaluation.reviewer")}</span>
          <input
            className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
            maxLength={200}
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                reviewer_name: event.target.value,
              }))
            }
            value={values.reviewer_name}
          />
        </label>
        <label className="block text-xs text-slate-600">
          <span className="mb-1 block">{t("calibration.evaluation.notes")}</span>
          <input
            className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
            maxLength={4000}
            onChange={(event) =>
              setValues((current) => ({ ...current, notes: event.target.value }))
            }
            value={values.notes ?? ""}
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-2 text-sm text-slate-700">
          <input
            checked={values.ready_for_real_outreach}
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                ready_for_real_outreach: event.target.checked,
              }))
            }
            type="checkbox"
          />
          {t("calibration.evaluation.ready")}
        </label>
        <button
          className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          data-testid="save-calibration-evaluation"
          disabled={busy || !values.reviewer_name.trim()}
          onClick={save}
          type="button"
        >
          {busy ? t("calibration.evaluation.saving") : t("calibration.evaluation.save")}
        </button>
        {saved ? (
          <span className="text-xs text-violet-800">
            {t("calibration.evaluation.savedAt", {
              time: new Date(saved.reviewed_at).toLocaleString(),
            })}
          </span>
        ) : null}
      </div>
      {error ? <p className="mt-2 text-xs text-rose-700">{error}</p> : null}
    </div>
  );
}

export function CalibrationReportPanel({
  calibrationId,
  refreshToken,
}: CalibrationReportPanelProps) {
  const { t } = useI18n();
  const [report, setReport] = useState<CalibrationReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setReport(await getCalibrationReport(calibrationId));
      setError(null);
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught).message);
    }
  }, [calibrationId]);

  useEffect(() => {
    let active = true;
    void getCalibrationReport(calibrationId)
      .then((nextReport) => {
        if (!active) return;
        setReport(nextReport);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setError(getClientErrorDetails(caught).message);
      });
    return () => {
      active = false;
    };
  }, [calibrationId, refreshToken]);

  if (error) {
    return (
      <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        {error}
      </div>
    );
  }
  if (!report) {
    return <p className="mt-6 text-sm text-slate-500">{t("calibration.loading")}</p>;
  }

  const summary = report.summary;
  const truth = report.truth_checks;
  const deterministic =
    report.providers.research_provider_mode === "deterministic_fake" ||
    report.providers.draft_provider_mode === "deterministic_fake";

  return (
    <section
      className="mt-6 rounded-3xl border border-violet-200 bg-white p-4 shadow-sm sm:p-6"
      data-testid="calibration-report"
      id="calibration-report"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-700">
            {t("calibration.kicker")}
          </p>
          <h3 className="mt-1 text-xl font-semibold text-slate-950">
            {t("calibration.title")}
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {t("calibration.sample", { count: summary.sample_count })} · {report.status}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            className="inline-flex items-center gap-2 rounded-lg border border-violet-200 px-3 py-2 text-sm font-semibold text-violet-800"
            href={calibrationExportUrl(calibrationId, "csv")}
          >
            <Download className="size-4" /> CSV
          </a>
          <a
            className="inline-flex items-center gap-2 rounded-lg border border-violet-200 px-3 py-2 text-sm font-semibold text-violet-800"
            href={calibrationExportUrl(calibrationId, "json")}
          >
            <Download className="size-4" /> JSON
          </a>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium">
        <span className="rounded-full bg-sky-100 px-3 py-1 text-sky-900">
          HTTP: {report.providers.website_fetch_mode}
        </span>
        <span className="rounded-full bg-violet-100 px-3 py-1 text-violet-900">
          Research: {report.providers.research_provider_mode}
        </span>
        <span className="rounded-full bg-violet-100 px-3 py-1 text-violet-900">
          Draft: {report.providers.draft_provider_mode}
        </span>
        <span className="rounded-full bg-teal-100 px-3 py-1 text-teal-900">
          Contact: {report.providers.contact_source_mode}
        </span>
      </div>
      {deterministic ? (
        <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {t("calibration.deterministicNotice")}
        </p>
      ) : null}

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        {[
          [t("calibration.metric.research"), percentage(summary.website_research_success_rate)],
          [t("calibration.metric.accepted"), summary.evidence_accepted_count],
          [t("calibration.metric.qualified"), summary.qualified_count],
          [t("calibration.metric.personal"), percentage(summary.personal_contact_coverage_rate)],
          [t("calibration.metric.department"), percentage(summary.department_contact_coverage_rate)],
          [t("calibration.metric.draft"), percentage(summary.draft_generation_rate)],
          [t("calibration.metric.ready"), summary.ready_for_real_outreach_count],
          [t("calibration.metric.recovery"), summary.worker_recovery_count],
          [t("calibration.metric.duration"), duration(summary.average_processing_duration_ms)],
        ].map(([label, value]) => (
          <div className="rounded-2xl bg-slate-50 p-3" key={String(label)}>
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-5">
        <h4 className="text-sm font-semibold text-slate-950">
          {t("calibration.truth.title")}
        </h4>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {[
            [t("calibration.truth.fabricated"), truth.fabricated_contact_count],
            [t("calibration.truth.unreviewed"), truth.unreviewed_fact_in_draft_count],
            [t("calibration.truth.rejected"), truth.rejected_claim_in_score_or_draft_count],
            [t("calibration.truth.pending"), truth.pending_claim_bypassed_count],
            [t("calibration.truth.sent"), truth.draft_marked_sent_count],
            [t("calibration.truth.duplicate"), truth.duplicate_entity_count],
            [t("calibration.truth.invalidEmail"), truth.invalid_email_contact_count],
            [
              t("calibration.truth.websiteFailure"),
              truth.website_failure_mislabeled_company_missing_count,
            ],
          ].map(([label, value]) => (
            <div
              className={`rounded-xl border p-3 text-sm ${truthTone(Number(value))}`}
              key={String(label)}
            >
              <ShieldCheck className="mr-1 inline size-4" /> {label}: {value}
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {t("calibration.scoreDisclaimer")}
        </p>
      </div>

      <div className="mt-6 space-y-4">
        {report.companies.map((company) => (
          <article
            className="rounded-2xl border border-slate-200 p-4"
            data-testid="calibration-company"
            key={company.company_id}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h4 className="font-semibold text-slate-950">{company.company_name}</h4>
                <p className="mt-1 text-xs text-slate-500">
                  {company.final_status}
                  {company.error_code ? ` · ${company.error_code}` : ""}
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                {duration(company.worker.total_duration_ms)}
              </span>
            </div>

            <div className="mt-4 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl bg-sky-50 p-3 text-sky-950">
                <p className="font-semibold">{t("calibration.section.research")}</p>
                <p className="mt-1 text-xs leading-5">
                  {company.research.pages_fetched} pages · {company.research.new_claim_count} claims ·
                  {" "}{duration(company.research.duration_ms)}
                </p>
                <p className="text-xs leading-5">
                  A {company.research.accepted_count} / E {company.research.edited_count} / R {company.research.rejected_count} / P {company.research.pending_count}
                </p>
                <p className="text-xs leading-5">
                  {t("calibration.noSourceClaims")}: {company.research.claims_without_source_count}
                </p>
                {company.research.failure_reason ? (
                  <p className="mt-1 text-xs leading-5 text-rose-800">
                    {company.research.failure_reason}
                  </p>
                ) : null}
              </div>
              <div className="rounded-xl bg-indigo-50 p-3 text-indigo-950">
                <p className="font-semibold">{t("calibration.section.opportunity")}</p>
                <p className="mt-1 text-xs leading-5">
                  Score {company.opportunity.score ?? "—"} · {company.opportunity.qualification_decision ?? "—"}
                </p>
                <p className="text-xs leading-5">
                  {company.opportunity.trusted_evidence_count} trusted evidence
                </p>
                {company.opportunity.stopped_for_insufficient_evidence ? (
                  <p className="mt-1 text-xs leading-5 text-amber-800">
                    {t("calibration.insufficientEvidence")}
                  </p>
                ) : null}
              </div>
              <div className="rounded-xl bg-teal-50 p-3 text-teal-950">
                <p className="font-semibold">
                  {t("calibration.section.contact")} · {company.contact.contact_type ?? "none"}
                </p>
                <p className="mt-1 text-xs leading-5">
                  {company.contact.name ?? company.contact.contact_not_found_reason ?? "—"}
                </p>
                <p className="text-xs leading-5">
                  {company.contact.title_or_department ?? "—"}
                </p>
                <p className="break-all text-xs leading-5">{company.contact.email ?? "—"}</p>
                <p className="break-all text-xs leading-5">{company.contact.phone ?? "—"}</p>
                <p className="text-xs leading-5">
                  {company.contact.manually_confirmed
                    ? t("calibration.manuallyConfirmed")
                    : t("calibration.notManuallyConfirmed")}
                </p>
                {company.contact.source_url ? (
                  <a
                    className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-teal-800"
                    href={company.contact.source_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {t("calibration.source")} <ExternalLink className="size-3" />
                  </a>
                ) : null}
              </div>
              <div className="rounded-xl bg-amber-50 p-3 text-amber-950">
                <p className="font-semibold">{t("calibration.section.draft")}</p>
                <p className="mt-1 text-xs leading-5">
                  {company.draft.generated ? t("calibration.generated") : t("calibration.notGenerated")}
                </p>
                <p className="text-xs leading-5">
                  {company.draft.fact_count} facts · {company.draft.awaiting_human_review ? t("calibration.awaitingReview") : "—"}
                </p>
                <p className="text-xs leading-5">
                  {company.draft.all_facts_traceable
                    ? t("calibration.factsTraceable")
                    : t("calibration.factsNotTraceable")}
                </p>
                <p className="text-xs leading-5">
                  {company.draft.explicitly_not_sent ? t("batch.emailNotSent") : "⚠"}
                </p>
                {company.draft.not_generated_reason ? (
                  <p className="mt-1 text-xs leading-5 text-rose-800">
                    {company.draft.not_generated_reason}
                  </p>
                ) : null}
              </div>
            </div>

            <details className="mt-3 rounded-xl bg-indigo-50/70 p-3 text-xs text-slate-700">
              <summary className="cursor-pointer font-semibold">
                {t("calibration.auditDetails")}
              </summary>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <div>
                  <p className="font-semibold text-emerald-800">
                    {t("calibration.positiveReasons")}
                  </p>
                  <p className="mt-1 leading-5">
                    {company.opportunity.major_positive_reasons.join(" · ") || "—"}
                  </p>
                  <p className="mt-2 font-semibold text-rose-800">
                    {t("calibration.deductionReasons")}
                  </p>
                  <p className="mt-1 leading-5">
                    {company.opportunity.major_deduction_reasons.join(" · ") || "—"}
                  </p>
                  <p className="mt-2 font-semibold text-amber-800">
                    {t("calibration.limitingReasons")}
                  </p>
                  <p className="mt-1 leading-5">
                    {company.opportunity.limiting_reasons.join(" · ") || "—"}
                  </p>
                </div>
                <div>
                  <p className="font-semibold text-slate-900">
                    {t("calibration.draftFacts")}
                  </p>
                  {company.draft.facts.length ? (
                    <ul className="mt-1 space-y-2">
                      {company.draft.facts.map((fact, factIndex) => (
                        <li className="rounded-lg bg-white p-2" key={`${fact.claim}-${factIndex}`}>
                          <p>{fact.claim}</p>
                          <p className="mt-1 font-medium">
                            {fact.traceable_to_company_evidence
                              ? t("calibration.traceable")
                              : t("calibration.notTraceable")}
                          </p>
                          <div className="mt-1 flex flex-wrap gap-2">
                            {fact.source_urls.map((sourceUrl) => (
                              <a
                                className="break-all font-semibold text-indigo-700"
                                href={sourceUrl}
                                key={sourceUrl}
                                rel="noreferrer"
                                target="_blank"
                              >
                                {sourceUrl}
                              </a>
                            ))}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1">—</p>
                  )}
                </div>
              </div>
            </details>

            <details className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-700">
              <summary className="cursor-pointer font-semibold">
                {t("calibration.stageTimings")}
              </summary>
              <div className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
                <p>{t("calibration.queueWait")}: {duration(company.worker.queue_wait_ms)}</p>
                <p>{t("calibration.attempts")}: {company.worker.attempt_count}</p>
                <p>{t("calibration.recoveries")}: {company.worker.recovery_count}</p>
                <p>
                  {t("calibration.leaseExpired")}: {company.worker.lease_expired ? t("calibration.yes") : t("calibration.no")}
                </p>
                {Object.entries(company.worker.stage_durations_ms).map(([stage, value]) => (
                  <p key={stage}>{stage}: {duration(value)}</p>
                ))}
              </div>
            </details>

            <EvaluationForm
              calibrationId={calibrationId}
              company={company}
              onSaved={load}
            />
          </article>
        ))}
      </div>
    </section>
  );
}
