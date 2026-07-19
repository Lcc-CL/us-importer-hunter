"use client";

import { Check, CircleDashed, Loader2, TriangleAlert } from "lucide-react";

import { useI18n, type MessageKey } from "@/lib/i18n";

export type FlowStep = "research" | "review" | "analysis" | "draft";
export type StepState = "todo" | "current" | "done" | "blocked";

const STEPS: Array<{ id: FlowStep; key: MessageKey }> = [
  { id: "research", key: "research.step.research" },
  { id: "review", key: "research.step.review" },
  { id: "analysis", key: "research.step.analysis" },
  { id: "draft", key: "research.step.draft" },
];

interface StepNavProps {
  states: Record<FlowStep, StepState>;
  /** What the user should do next, already localized. */
  nextAction?: string | null;
  /** Why the flow cannot continue, already localized. */
  blockedBy?: string | null;
}

function tone(state: StepState): string {
  if (state === "done") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (state === "current") return "border-teal-300 bg-teal-50 text-teal-900";
  if (state === "blocked") return "border-amber-300 bg-amber-50 text-amber-900";
  return "border-slate-200 bg-white text-slate-400";
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") return <Check className="size-3.5" />;
  if (state === "current") return <Loader2 className="size-3.5 animate-spin" />;
  if (state === "blocked") return <TriangleAlert className="size-3.5" />;
  return <CircleDashed className="size-3.5" />;
}

/**
 * Four steps, always visible. The panel used to show only the stage it was in,
 * so a reviewer could not tell how much was left or why nothing was happening.
 */
export function StepNav({ states, nextAction, blockedBy }: StepNavProps) {
  const { t } = useI18n();

  return (
    <div data-testid="research-steps">
      <ol className="flex flex-wrap items-center gap-1.5">
        {STEPS.map((step, index) => {
          const state = states[step.id];
          return (
            <li className="flex items-center gap-1.5" key={step.id}>
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${tone(state)}`}
                data-state={state}
                data-testid={`research-step-${step.id}`}
              >
                <StepIcon state={state} />
                {t(step.key)}
              </span>
              {index < STEPS.length - 1 ? (
                <span aria-hidden className="text-slate-300">
                  ›
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>

      {blockedBy ? (
        <p
          className="mt-2 text-xs leading-5 text-amber-900"
          data-testid="research-step-blocked"
        >
          {t("research.step.blockedBy", { reason: blockedBy })}
        </p>
      ) : nextAction ? (
        <p className="mt-2 text-xs leading-5 text-slate-500" data-testid="research-step-next">
          {t("research.step.next", { action: nextAction })}
        </p>
      ) : null}
    </div>
  );
}
