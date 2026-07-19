"use client";

import { useI18n } from "@/lib/i18n";
import type { ResearchClaim, ResearchProfile } from "@/lib/research-api";

interface ResearchSummaryProps {
  profile: ResearchProfile;
  claims: ResearchClaim[];
  unknownDimensions: string[];
}

/**
 * A readable summary of what the research found, grouped the way a forwarder
 * thinks rather than by claim kind.
 *
 * It is assembled, not generated: every line is either a validated claim's
 * detail or a field of company_profile. Nothing here is written by a model at
 * render time, so the summary cannot introduce a fact the evidence does not
 * support — which is the same rule the claims themselves live under.
 */
export function ResearchSummary({
  profile,
  claims,
  unknownDimensions,
}: ResearchSummaryProps) {
  const { t, label } = useI18n();

  const of = (...kinds: string[]) =>
    claims.filter((claim) => kinds.includes(claim.kind)).map((claim) => claim.detail);

  const businessModel = [profile.summary, profile.industry].filter(
    (value): value is string => Boolean(value && value.trim()),
  );
  const products = profile.products ?? [];
  const scale = of("company_scale");
  const complexity = of("logistics_complexity", "china_dependency");
  const opportunity = of("import_activity", "shipping_fit", "cargo_value_potential", "growth_signal", "pain_point");

  const groups: Array<{ key: string; heading: string; items: string[] }> = [
    { key: "model", heading: t("research.summary.model"), items: businessModel },
    { key: "products", heading: t("research.summary.products"), items: products },
    { key: "scale", heading: t("research.summary.scale"), items: scale },
    { key: "complexity", heading: t("research.summary.complexity"), items: complexity },
    { key: "opportunity", heading: t("research.summary.opportunity"), items: opportunity },
  ];

  const hasAnything =
    groups.some((group) => group.items.length > 0) || unknownDimensions.length > 0;
  if (!hasAnything) return null;

  return (
    <section
      className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
      data-testid="research-summary"
    >
      <p className="text-xs font-semibold text-slate-700">{t("research.summary.title")}</p>
      <p className="mt-1 text-xs leading-5 text-slate-500">{t("research.summary.note")}</p>

      <dl className="mt-3 space-y-2.5">
        {groups.map((group) => (
          <div key={group.key} data-testid={`research-summary-${group.key}`}>
            <dt className="text-xs font-medium text-slate-600">{group.heading}</dt>
            <dd className="mt-0.5 text-sm leading-6 text-slate-800">
              {group.items.length > 0 ? (
                <ul className="space-y-0.5">
                  {group.items.map((item, index) => (
                    <li key={`${group.key}-${index}`}>· {item}</li>
                  ))}
                </ul>
              ) : (
                <span className="text-slate-400">{t("research.summary.none")}</span>
              )}
            </dd>
          </div>
        ))}

        {unknownDimensions.length > 0 ? (
          <div data-testid="research-summary-unknown">
            <dt className="text-xs font-medium text-slate-600">
              {t("research.summary.unknown")}
            </dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {unknownDimensions.map((kind) => (
                <span
                  className="rounded-lg bg-slate-100 px-2 py-1 text-xs text-slate-700"
                  key={`summary-unknown-${kind}`}
                >
                  {label("signalKind", kind)}
                </span>
              ))}
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}
