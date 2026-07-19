/**
 * Canonical signal kinds submitted to the analysis API. The UI shows a
 * localized label (see i18n `signalKind` group); the value on the wire is
 * always one of these fixed English enums, matching the backend scorer's
 * dimension mapping. Database/API enums stay English — only display is
 * translated.
 */

export const SIGNAL_KINDS = [
  "import_activity",
  "china_dependency",
  "shipping_fit",
  "cargo_value_potential",
  "company_scale",
  "growth_signal",
  "logistics_complexity",
  "pain_point",
] as const;

export type SignalKind = (typeof SIGNAL_KINDS)[number];

/**
 * Legacy kinds that historical data may still carry. Kept only so an old
 * value renders with its canonical meaning when editing; new submissions use
 * the canonical enums above. The backend accepts these aliases too.
 */
export const LEGACY_SIGNAL_KINDS: Record<string, SignalKind> = {
  cargo_value: "cargo_value_potential",
  growth: "growth_signal",
  complexity: "logistics_complexity",
};

export function isCanonicalSignalKind(value: string): value is SignalKind {
  return (SIGNAL_KINDS as readonly string[]).includes(value);
}
