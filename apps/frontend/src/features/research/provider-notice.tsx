"use client";

import { useEffect, useState } from "react";
import { Sparkles, TriangleAlert } from "lucide-react";

import { getRuntimeStatus, type RuntimeStatusResponse } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/**
 * Says which extractor produced what you are looking at.
 *
 * The Fake extractor is the safe default, and it looks convincing: it returns
 * real sentences from the real page. A reviewer judging extraction quality
 * from a demo run would draw conclusions about a model that never ran. So the
 * warning is text, not just a colour — colour alone would fail anyone who
 * cannot distinguish it, and this is the one message that must not be missed.
 *
 * Names only. The key and the base URL are never fetched here, and the runtime
 * endpoint does not expose them.
 */
export function ProviderNotice() {
  const { t } = useI18n();
  const [runtime, setRuntime] = useState<RuntimeStatusResponse | null>(null);

  useEffect(() => {
    let active = true;
    getRuntimeStatus()
      .then((status) => {
        if (active) setRuntime(status);
      })
      .catch(() => {
        // A badge is not worth an error state; staying silent is correct.
      });
    return () => {
      active = false;
    };
  }, []);

  if (!runtime) return null;

  if (runtime.research_provider === "fake") {
    return (
      <p
        className="mt-2 flex items-start gap-2 rounded-xl bg-amber-400/20 px-3 py-2 text-xs
                   font-medium leading-5 text-amber-100"
        data-testid="research-provider-fake"
      >
        <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
        <span>
          <strong className="font-semibold">{t("research.provider.fake")}</strong>
          {" — "}
          {t("research.provider.fakeNotice")}
        </span>
      </p>
    );
  }

  return (
    <p
      className="mt-2 flex items-center gap-2 rounded-xl bg-teal-400/15 px-3 py-2 text-xs
                 font-medium leading-5 text-teal-100"
      data-testid="research-provider-real"
    >
      <Sparkles className="size-3.5 shrink-0" />
      {t("research.provider.real", {
        provider: runtime.research_provider,
        model: runtime.research_model,
      })}
    </p>
  );
}
