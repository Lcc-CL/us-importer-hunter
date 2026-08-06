"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  type ReadinessResponse,
  type RuntimeStatusResponse,
} from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";

export type DependencyName = "backend" | "postgres" | "redis" | "worker";
export type ComponentStatusKind = "ok" | "error" | "unknown" | "checking";
export type WorkerReasonCode =
  | "WORKER_HEARTBEAT_OK"
  | "WORKER_HEARTBEAT_MISSING"
  | "WORKER_HEARTBEAT_EXPIRED"
  | "WORKER_HEARTBEAT_INVALID"
  | "REDIS_UNAVAILABLE";

export interface WorkerHealthDetail {
  status: "healthy" | "unavailable" | "unknown";
  reasonCode: WorkerReasonCode | null;
  lastSeenAt: string | null;
  ageSeconds: number | null;
}

export interface AcceptanceHealthState {
  phase: "checking" | "healthy" | "degraded" | "unavailable";
  /** Convenience booleans: true only when the component is confirmed "ok". */
  backend: boolean;
  postgres: boolean;
  redis: boolean;
  worker: boolean;
  /** Precise per-component status for display (ok/error/unknown/checking). */
  components: Record<DependencyName, ComponentStatusKind>;
  workerDetail: WorkerHealthDetail | null;
  realDataGate: "enabled" | "blocked";
  runtime: RuntimeStatusResponse | null;
  /** True when the last fully-successful check is older than the staleness window. */
  stale: boolean;
  lastSuccessAt: number | null;
  checkedAt: number;
}

export const INITIAL_STATE: AcceptanceHealthState = {
  phase: "checking",
  backend: false,
  postgres: false,
  redis: false,
  worker: false,
  components: {
    backend: "checking",
    postgres: "checking",
    redis: "checking",
    worker: "checking",
  },
  workerDetail: null,
  realDataGate: "blocked",
  runtime: null,
  stale: false,
  lastSuccessAt: null,
  checkedAt: 0,
};

/** A fully successful check older than this is treated as possibly stale. */
const STALE_AFTER_MS = 30_000;

interface ProviderBadgeProps {
  onStatusChange?: (state: AcceptanceHealthState) => void;
  realDataMode?: boolean;
}

function isStale(lastSuccessAt: number | null, checkedAt: number): boolean {
  return lastSuccessAt !== null && checkedAt - lastSuccessAt > STALE_AFTER_MS;
}

function componentFromHealthy(healthy: boolean | null): ComponentStatusKind {
  if (healthy === null) return "unknown";
  return healthy ? "ok" : "error";
}

export function ProviderBadge({ onStatusChange, realDataMode = false }: ProviderBadgeProps) {
  const { t } = useI18n();
  const [state, setState] = useState<AcceptanceHealthState>(INITIAL_STATE);
  const [retrying, setRetrying] = useState(false);
  const lastSuccessAtRef = useRef<number | null>(null);

  const check = useCallback(async () => {
    const checkedAt = Date.now();
    setRetrying(true);

    try {
      await getHealthStatus();
    } catch {
      const next: AcceptanceHealthState = {
        ...INITIAL_STATE,
        phase: "unavailable",
        backend: false,
        components: {
          backend: "error",
          postgres: "unknown",
          redis: "unknown",
          worker: "unknown",
        },
        stale: isStale(lastSuccessAtRef.current, checkedAt),
        lastSuccessAt: lastSuccessAtRef.current,
        checkedAt,
      };
      setState(next);
      onStatusChange?.(next);
      setRetrying(false);
      return;
    }

    const [readinessResult, runtimeResult] = await Promise.allSettled([
      getReadinessStatus(),
      getRuntimeStatus(),
    ]);
    const readiness: ReadinessResponse | null =
      readinessResult.status === "fulfilled" ? readinessResult.value : null;
    const runtime: RuntimeStatusResponse | null =
      runtimeResult.status === "fulfilled" ? runtimeResult.value : null;

    const deps = readiness?.dependencies ?? [];
    const depHealthy = (name: string): boolean | null => {
      const dependency = deps.find((item) => item.name === name);
      return dependency ? dependency.healthy : null;
    };
    const workerDep = deps.find((item) => item.name === "worker") ?? null;
    const workerDetail = workerDep
      ? {
          status: workerDep.status ?? (workerDep.healthy ? ("healthy" as const) : ("unavailable" as const)),
          reasonCode: workerDep.reason_code ??
            (workerDep.healthy ? ("WORKER_HEARTBEAT_OK" as const) : ("WORKER_HEARTBEAT_MISSING" as const)),
          lastSeenAt: workerDep.last_seen_at ?? null,
          ageSeconds: workerDep.age_seconds ?? null,
        }
      : null;

    const components: Record<DependencyName, ComponentStatusKind> = {
      backend: "ok",
      postgres: componentFromHealthy(depHealthy("postgres")),
      redis: componentFromHealthy(depHealthy("redis")),
      worker:
        workerDep?.status === "healthy"
          ? "ok"
          : workerDep?.status === "unknown"
            ? "unknown"
            : workerDep?.status === "unavailable"
              ? "error"
              : componentFromHealthy(depHealthy("worker")),
    };
    const allOk = Object.values(components).every((status) => status === "ok");
    const success = readiness !== null && runtime !== null;
    const lastSuccessAt = success ? checkedAt : lastSuccessAtRef.current;
    lastSuccessAtRef.current = lastSuccessAt;

    const next: AcceptanceHealthState = {
      phase: allOk && runtime ? "healthy" : "degraded",
      backend: components.backend === "ok",
      postgres: components.postgres === "ok",
      redis: components.redis === "ok",
      worker: components.worker === "ok",
      components,
      workerDetail,
      realDataGate: runtime?.real_data_gate ?? "blocked",
      runtime,
      stale: isStale(lastSuccessAt, checkedAt),
      lastSuccessAt,
      checkedAt,
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
  const providerFake = runtime?.provider !== "openai";
  const realWriteEnabled = realDataMode && state.realDataGate === "enabled";
  const statusStyle =
    state.phase === "checking"
      ? "border-slate-200 bg-slate-50"
      : state.phase === "healthy"
        ? "border-emerald-200 bg-emerald-50"
        : state.phase === "unavailable"
          ? "border-rose-200 bg-rose-50"
          : "border-amber-200 bg-amber-50";
  const title = cardTitle(t, state);
  const description = cardDescription(t, state);
  const componentLabel = (status: ComponentStatusKind): string =>
    status === "ok"
      ? t("runtime.component.ok")
      : status === "error"
        ? t("runtime.component.error")
        : status === "unknown"
          ? t("runtime.component.unknown")
          : t("runtime.component.checking");

  return (
    <section
      className={`min-w-0 rounded-2xl border p-4 ${statusStyle}`}
      data-health-phase={state.phase}
      data-testid="runtime-status-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            {state.phase === "checking" || retrying ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : state.phase === "healthy" ? (
              <CheckCircle2 className="size-4 shrink-0 text-emerald-700" />
            ) : (
              <AlertTriangle className="size-4 shrink-0 text-amber-700" />
            )}
            <span>{title}</span>
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-600">{description}</p>
          {state.phase === "unavailable" ? (
            <p className="mt-1 text-xs leading-5 text-rose-800">
              {t("runtime.target")}: {getSafeApiRequestTarget()}
            </p>
          ) : null}
          {state.stale ? (
            <p
              className="mt-1 text-xs font-semibold text-amber-800"
              data-testid="runtime-stale"
            >
              {t("runtime.stale")}
            </p>
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
        <ComponentStatus
          icon={Server}
          label="Backend"
          status={state.components.backend}
          statusLabel={componentLabel(state.components.backend)}
        />
        <ComponentStatus
          icon={Database}
          label="PostgreSQL"
          status={state.components.postgres}
          statusLabel={componentLabel(state.components.postgres)}
        />
        <ComponentStatus
          icon={Database}
          label="Redis"
          status={state.components.redis}
          statusLabel={componentLabel(state.components.redis)}
        />
        <ComponentStatus
          icon={Workflow}
          label="Worker"
          status={state.components.worker}
          statusLabel={componentLabel(state.components.worker)}
        />
      </div>

      <details className="mt-2 text-xs text-slate-600">
        <summary className="cursor-pointer font-semibold text-slate-700">
          {t("runtime.techDetails")}
        </summary>
        {state.workerDetail ? (
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px]">
            <dt>{t("runtime.worker.reasonCode")}</dt>
            <dd data-testid="runtime-worker-reason">
              {state.workerDetail.reasonCode ?? t("runtime.worker.noReason")}
            </dd>
            <dt>{t("runtime.worker.lastSeen")}</dt>
            <dd>{state.workerDetail.lastSeenAt ?? t("runtime.worker.noReason")}</dd>
            <dt>{t("runtime.worker.age")}</dt>
            <dd>
              {state.workerDetail.ageSeconds !== null
                ? `${state.workerDetail.ageSeconds}s`
                : t("runtime.worker.noReason")}
            </dd>
          </dl>
        ) : (
          <p className="mt-2 text-[11px] text-slate-500">
            {t("runtime.worker.noDetails")}
          </p>
        )}
      </details>

      <div
        className="mt-3 rounded-xl border border-slate-200 bg-white/80 p-3"
        data-testid="provider-badge"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <Sparkles className={`size-3.5 ${providerFake ? "text-slate-500" : "text-teal-700"}`} />
            {t("runtime.mode.title")}
          </p>
          <span
            className={
              realDataMode
                ? "rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-900"
                : "rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700"
            }
            data-testid="runtime-data-mode"
          >
            {realDataMode ? t("runtime.mode.real") : t("runtime.mode.synthetic")}
          </span>
        </div>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-slate-500">{t("runtime.mode.provider")}</dt>
            <dd className="font-medium text-slate-800" data-testid="runtime-provider-label">
              {runtime
                ? providerFake
                  ? t("runtime.mode.providerFake")
                  : t("runtime.mode.providerReal")
                : t("runtime.worker.noReason")}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("runtime.mode.realWrite")}</dt>
            <dd
              className={
                realWriteEnabled ? "font-medium text-emerald-800" : "font-medium text-slate-700"
              }
              data-testid="runtime-real-write"
            >
              {realWriteEnabled
                ? t("runtime.mode.enabled")
                : t("runtime.mode.disabled")}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("runtime.mode.email")}</dt>
            <dd className="font-medium text-slate-800">{t("runtime.mode.emailAlwaysOff")}</dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("runtime.mode.worker")}</dt>
            <dd className="font-medium text-slate-800" data-testid="runtime-mode-worker">
              {componentLabel(state.components.worker)}
            </dd>
          </div>
          <div className="col-span-2 sm:col-span-1">
            <dt className="text-slate-500">{t("runtime.mode.externalCalls")}</dt>
            <dd className="font-medium text-slate-800" data-testid="runtime-external-calls">
              {runtime
                ? providerFake
                  ? t("runtime.mode.externalNotCalled")
                  : t("runtime.mode.externalConfigured")
                : t("runtime.worker.noReason")}
            </dd>
          </div>
        </dl>
        {!realWriteEnabled ? (
          <p
            className="mt-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] font-medium text-amber-900"
            data-testid="runtime-no-real-writes"
          >
            {t("runtime.mode.noRealWrites")}
          </p>
        ) : null}
        <details className="mt-2 text-[11px] text-slate-500">
          <summary className="cursor-pointer font-semibold text-slate-600">
            {t("runtime.mode.providerVersion")}
          </summary>
          <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 font-mono">
            <dt>{t("runtime.mode.draftProvider")}</dt>
            <dd>{runtime ? `${runtime.provider} · ${runtime.model}` : t("runtime.worker.noReason")}</dd>
            <dt>{t("runtime.mode.researchProvider")}</dt>
            <dd>
              {runtime
                ? `${runtime.research_provider} · ${runtime.research_model}`
                : t("runtime.worker.noReason")}
            </dd>
            <dt>{t("runtime.mode.environment")}</dt>
            <dd>{runtime?.environment ?? t("runtime.worker.noReason")}</dd>
          </dl>
        </details>
      </div>
    </section>
  );
}

function cardTitle(
  t: (key: MessageKey) => string,
  state: AcceptanceHealthState,
): string {
  const { components, phase } = state;
  if (phase === "checking") return t("runtime.checking");
  if (phase === "unavailable" || components.backend !== "ok") {
    return t("runtime.card.backendUnavailable");
  }
  if (components.postgres !== "ok") return t("runtime.card.postgresUnavailable");
  if (components.redis !== "ok") return t("runtime.card.redisUnavailable");
  if (components.worker !== "ok") return t("runtime.card.workerUnavailable");
  return t("runtime.card.allHealthy");
}

function cardDescription(
  t: (key: MessageKey) => string,
  state: AcceptanceHealthState,
): string {
  const { components, phase } = state;
  if (phase === "checking") return t("runtime.checkingDescription");
  if (phase === "unavailable" || components.backend !== "ok") {
    return t("runtime.card.backendUnavailableDescription");
  }
  if (components.postgres !== "ok") {
    return t("runtime.card.postgresUnavailableDescription");
  }
  if (components.redis !== "ok") {
    return t("runtime.card.redisUnavailableDescription");
  }
  if (components.worker !== "ok") {
    return t("runtime.card.workerUnavailableDescription");
  }
  return t("runtime.card.allHealthyDescription");
}

function ComponentStatus({
  status,
  statusLabel,
  icon: Icon,
  label,
}: {
  status: ComponentStatusKind;
  statusLabel: string;
  icon: typeof Server;
  label: string;
}) {
  const tone =
    status === "ok"
      ? "text-emerald-700"
      : status === "error"
        ? "text-rose-700"
        : status === "checking"
          ? "text-slate-500"
          : "text-amber-700";
  return (
    <div className="flex items-center gap-2 rounded-lg bg-white/80 px-2.5 py-2">
      <Icon className={`size-3.5 shrink-0 ${tone}`} />
      <span className="font-medium text-slate-700">{label}</span>
      <span
        className={`ml-auto font-semibold ${tone}`}
        data-component-status={status}
        data-testid={`component-status-${label.toLowerCase()}`}
      >
        {statusLabel}
      </span>
    </div>
  );
}
