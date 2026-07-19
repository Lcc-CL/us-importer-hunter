"use client";

import { useI18n, type MessageKey } from "@/lib/i18n";
import type { QualificationExplanation } from "@/lib/api";

interface QualificationExplanationProps {
  explanation: QualificationExplanation;
  decision: string | null;
}

/**
 * Why the verdict is what it is.
 *
 * The internal trial stopped all three companies at REVIEW and the screen said
 * only "REVIEW" — so a salesperson read it as "weak prospect" when the real
 * cause was that a company website cannot prove customs activity. Naming the
 * gap as a limit of the *source* is the whole point of this panel.
 */
export function QualificationExplanationCard({
  explanation,
  decision,
}: QualificationExplanationProps) {
  const { t, label } = useI18n();
  const needsImport = explanation.import_evidence_missing.length > 0;

  return (
    <section
      className="rounded-2xl border border-slate-200 bg-white px-4 py-4"
      data-testid="qualification-explanation"
    >
      <div data-testid="qual-obtained">
        <p className="text-xs font-semibold text-slate-700">
          {t("qual.evidence.obtained")}
        </p>
        <ul className="mt-2 space-y-1">
          {explanation.dimensions
            .filter((item) => item.evidence_status === "present")
            .map((item) => (
              <li
                className="flex flex-wrap items-baseline gap-2 text-sm text-slate-800"
                key={`ok-${item.dimension}`}
              >
                <span className="font-medium">{label("signalKind", item.dimension)}</span>
                <span className="text-xs text-slate-500">
                  {t("qual.contribution", {
                    points: item.earned_score,
                    weight: item.weight,
                  })}
                </span>
              </li>
            ))}
        </ul>
      </div>

      {explanation.missing_key_evidence.length > 0 ? (
        <div className="mt-4" data-testid="qual-missing">
          <p className="text-xs font-semibold text-slate-700">
            {t("qual.evidence.missing")}
          </p>
          <ul className="mt-2 space-y-1">
            {explanation.dimensions
              .filter((item) => item.evidence_status === "absent")
              .map((item) => (
                <li
                  className="flex flex-wrap items-baseline gap-2 text-sm text-slate-700"
                  key={`gap-${item.dimension}`}
                >
                  <span className="font-medium">
                    {label("signalKind", item.dimension)}
                  </span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                    {t(`qual.status.${item.status}` as MessageKey)}
                  </span>
                  <span className="text-xs text-slate-500">
                    {t("qual.contribution", { points: 0, weight: item.weight })}
                  </span>
                </li>
              ))}
          </ul>
        </div>
      ) : null}

      {needsImport ? (
        <div
          className="mt-4 rounded-xl border border-sky-200 bg-sky-50 px-3 py-3"
          data-testid="qual-import-notice"
        >
          <p className="text-sm leading-6 text-sky-900">{t("qual.importNotice")}</p>
          <p className="mt-1 text-xs text-sky-800">
            {t("qual.unreachableWeight", { weight: explanation.unreachable_weight })}
          </p>
          {explanation.next_action ? (
            <p
              className="mt-2 text-xs font-semibold text-sky-900"
              data-testid="qual-next-action"
            >
              {t(`qual.nextAction.${explanation.next_action}` as MessageKey)}
            </p>
          ) : null}
        </div>
      ) : null}

      {decision && decision !== "qualified" ? (
        <div className="mt-4" data-testid="qual-why-review">
          <p className="text-xs font-semibold text-slate-700">{t("qual.whyReview")}</p>
          <p className="mt-1 text-sm leading-6 text-slate-700">
            {needsImport ? t("qual.importNotice") : t("qual.evidence.missing")}
          </p>
        </div>
      ) : null}
    </section>
  );
}
