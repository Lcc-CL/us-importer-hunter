import { Gauge, ShieldCheck, Telescope } from "lucide-react";

import type {
  AssessmentDetailResponse,
  OpportunityAnalysisResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface OpportunityCardProps {
  analysis: OpportunityAnalysisResponse | null;
  detail: AssessmentDetailResponse | null;
}

function formatScore(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(1);
}

function formatRatio(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

export function OpportunityCard({ analysis, detail }: OpportunityCardProps) {
  const { t, label } = useI18n();
  const score = detail?.score ?? analysis?.score;
  const confidence = detail?.confidence ?? analysis?.confidence;
  const completeness = detail?.data_completeness ?? analysis?.data_completeness;
  const decision = detail?.qualification_decision ?? analysis?.qualification_decision;
  const recommendedAction = detail?.recommended_action ?? analysis?.recommended_action;
  const reasons = detail?.reasons ?? analysis?.reasons ?? [];
  const action = analysis?.action ?? decision?.toUpperCase() ?? "NOT ASSESSED";
  const needsResearch = action === "RESEARCH_MORE" || decision === "research_more";

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700">
            <Gauge className="size-4" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
              {t("opp.kicker")}
            </p>
            <h3 className="mt-0.5 font-semibold text-slate-950">{t("opp.title")}</h3>
          </div>
        </div>
        <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-800">
          {label("stage", action)}
        </span>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Metric
          label={t("opp.score")}
          value={formatScore(score)}
          hint={t("opp.scoreHint")}
        />
        <Metric
          label={t("opp.confidence")}
          value={formatRatio(confidence)}
          hint={t("opp.confidenceHint")}
        />
        <Metric
          label={t("opp.completeness")}
          value={formatRatio(completeness)}
          hint={t("opp.completenessHint")}
        />
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold text-slate-500">{t("opp.decision")}</p>
          <p className="mt-1 text-sm font-medium text-slate-900">
            {label("decision", decision)}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold text-slate-500">
            {t("opp.recommendedAction")}
          </p>
          <p className="mt-1 text-sm font-medium text-slate-900">
            {label("recommendedAction", recommendedAction)}
          </p>
        </div>
      </div>

      {needsResearch ? (
        <div className="mt-5 flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <Telescope className="mt-0.5 size-4 shrink-0" />
          <p>{t("opp.researchNotice")}</p>
        </div>
      ) : null}

      {reasons.length > 0 ? (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="flex items-center gap-2 text-xs font-semibold text-slate-600">
            <ShieldCheck className="size-4 text-teal-700" /> {t("opp.why")}
          </p>
          <ul className="mt-2 space-y-1.5 text-sm leading-6 text-slate-600">
            {reasons.map((reason, index) => (
              <li className="flex gap-2" key={`reason-${index}`}>
                <span className="text-teal-700">•</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
