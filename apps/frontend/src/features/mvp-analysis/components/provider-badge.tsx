"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  LoaderCircle,
  RefreshCw,
  Server,
  Sparkles,
  Workflow,
} from "lucide-react";

import {
  getHealthStatus,
  getReadinessStatus,
  getRuntimeStatus,
  getSafeApiRequestTarget,
  type RuntimeStatusResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export interface AcceptanceHealthState {
  phase: "checking" | "healthy" | "degraded" | "unavailable";
  backend: boolean;
  postgres: boolean;
  redis: boolean;
  worker: boolean;
  realDataGate: "enabled" | "blocked";
  runtime: RuntimeStatusResponse | null;
}

const INITIAL_STATE: AcceptanceHealthState = {
  phase: "checking",
  backend: false,
  postgres: false,
  redis: false,
  worker: false,
  realDataGate: "blocked",
  runtime: null,
};

interface ProviderBadgeProps {
  onStatusChange?: (state: AcceptanceHealthState) => void;
}

export function ProviderBadge({ onStatusChange }: ProviderBadgeProps) {
  const { t } = useI18n();
  const [state, setState] = useState<AcceptanceHealthState>(INITIAL_STATE);
  const [retrying, setRetrying] = useState(false);

  const check = useCallback(async () => {
    setRetrying(true);
    try {
      await getHealthStatus();
    } catch {
      const unavailable: AcceptanceHealthState = {
        ...INITIAL_STATE,
        phase: "unavailable",
      };
      setState(unavailable);
      onStatusChange?.(unavailable);
      setRetrying(false);
      return;
    }

    const [readinessResult, runtimeResult] = await Promise.allSettled([
      getReadinessStatus(),
      getRuntimeStatus(),
    ]);
    const readiness = readinessResult.status === "fulfilled"
      ? readinessResult.value
      : null;
    const runtime = runtimeResult.status === "fulfilled" ? runtimeResult.value : null;
    const dependency = (name: string) =>
      readiness?.dependencies.find((item) => item.name === name)?.healthy ?? false;
    const next: AcceptanceHealthState = {
      phase:
        readiness?.status === "ready" && runtime
          ? "healthy"
          : "degraded",
      backend: true,
      postgres: dependency("postgres"),
      redis: dependency("redis"),
      worker: dependency("worker"),
      realDataGate: runtime?.real_data_gate ?? "blocked",
      runtime,
    };
    setState(next);
    onStatusChange?.(next);
    setRetrying(false);
  }, [onStatusChange]);

  useEffect(() => {
    const initial = window.setTimeout(() => void check(), 0);
    const timer = window.setInterval(() => void check(), 5_000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [check]);

  const runtime = state.runtime;
  const isLive = runtime?.provider === "openai";
  const statusStyle =
    state.phase === "healthy"
      ? "border-emerald-200 bg-emerald-50"
      : state.phase === "unavailable"
        ? "border-rose-200 bg-rose-50"
        : "border-amber-200 bg-amber-50";

  return (
    <section
      className={`min-w-0 rounded-2xl border p-4 ${statusStyle}`}
      data-health-phase={state.phase}
      data-testid="runtime-status-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            {state.phase === "checking" || retrying ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : state.phase === "healthy" ? (
              <CheckCircle2 className="size-4 text-emerald-700" />
            ) : (
              <AlertTriangle className="size-4 text-amber-700" />
            )}
            {state.phase === "healthy"
              ? t("runtime.connected")
              : state.phase === "unavailable"
                ? t("runtime.unavailable")
                : state.phase === "checking"
                  ? t("runtime.checking")
                  : t("runtime.degraded")}
          </div>
          {state.phase === "unavailable" ? (
            <div className="mt-2 text-xs leading-5 text-rose-800">
              <p>{t("runtime.target")}: {getSafeApiRequestTarget()}</p>
              <p>{t("runtime.unavailableReason")}</p>
            </div>
          ) : null}
        </div>
        <button
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-50"
          data-testid="runtime-retry"
          disabled={retrying}
          onClick={() => void check()}
          type="button"
        >
          <RefreshCw className={`size-3.5 ${retrying ? "animate-spin" : ""}`} />
          {t("runtime.retry")}
        </button>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <ComponentStatus healthy={state.backend} icon={Server} label="Backend" />
        <ComponentStatus healthy={state.postgres} icon={Database} label="PostgreSQL" />
        <ComponentStatus healthy={state.redis} icon={Database} label="Redis" />
        <ComponentStatus healthy={state.worker} icon={Workflow} label="Worker" />
      </div>

      {runtime ? (
        <div
          className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600"
          data-testid="provider-badge"
        >
          <Sparkles className={`size-3.5 ${isLive ? "text-teal-700" : "text-slate-500"}`} />
          <span>{isLive ? t("provider.live") : t("provider.demo")}</span>
          <span className="font-mono text-[11px]">
            {runtime.provider} · {runtime.model}
          </span>
        </div>
      ) : null}
    </section>
  );
}

function ComponentStatus({
  healthy,
  icon: Icon,
  label,
}: {
  healthy: boolean;
  icon: typeof Server;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-white/80 px-2.5 py-2">
      <Icon className={`size-3.5 ${healthy ? "text-emerald-700" : "text-rose-700"}`} />
      <span className="font-medium text-slate-700">{label}</span>
      <span className={healthy ? "text-emerald-700" : "text-rose-700"}>
        {healthy ? "OK" : "—"}
      </span>
    </div>
  );
}
