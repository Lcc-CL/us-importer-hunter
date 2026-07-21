"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";

import { getRuntimeStatus, type RuntimeStatusResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type BadgeState =
  | { phase: "loading" }
  | { phase: "ready"; runtime: RuntimeStatusResponse }
  | { phase: "unavailable" };

/**
 * Live provider/model badge fed by GET /health/runtime — never renders
 * credentials or endpoint URLs because the API does not return them.
 */
export function ProviderBadge() {
  const { t } = useI18n();
  const [state, setState] = useState<BadgeState>({ phase: "loading" });

  useEffect(() => {
    let active = true;
    getRuntimeStatus()
      .then((runtime) => {
        if (active) setState({ phase: "ready", runtime });
      })
      .catch(() => {
        if (active) setState({ phase: "unavailable" });
      });
    return () => {
      active = false;
    };
  }, []);

  if (state.phase === "loading") {
    return (
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <LoaderCircle className="size-4 animate-spin" /> {t("provider.checking")}
      </div>
    );
  }

  if (state.phase === "unavailable") {
    return (
      <div className="flex items-center gap-2 text-xs font-medium text-rose-700">
        <ShieldAlert className="size-4" /> {t("provider.unavailable")}
      </div>
    );
  }

  const { provider, model } = state.runtime;
  const isLive = provider === "openai";

  return (
    <div
      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${
        isLive
          ? "border-teal-200 bg-teal-50 text-teal-800"
          : "border-slate-200 bg-slate-50 text-slate-600"
      }`}
      data-testid="provider-badge"
    >
      {isLive ? (
        <Sparkles className="size-4 text-teal-700" />
      ) : (
        <ShieldCheck className="size-4 text-slate-500" />
      )}
      <span>{isLive ? t("provider.live") : t("provider.demo")}</span>
      <span className="font-mono text-[11px] text-slate-500">
        {provider} · {model}
      </span>
    </div>
  );
}
