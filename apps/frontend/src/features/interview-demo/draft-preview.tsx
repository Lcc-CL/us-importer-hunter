"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { generateInterviewDraft, getInterviewDemoCapability, type InterviewDraft } from "@/lib/api";

const preset = {
  subject: "Inbound freight planning for Cedar Harbor",
  body: "Hi Logistics Team,\n\nI’m with Example Freight. Could we schedule a brief call to discuss routing and delivery planning for your home storage shipments through Long Beach?\n\nBest,\nDemo operator",
};

export function DraftPreview() {
  const [enabled, setEnabled] = useState(false);
  const [draft, setDraft] = useState<InterviewDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getInterviewDemoCapability(controller.signal)
      .then((result) => setEnabled(result.live_enabled))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  async function requestDraft() {
    setBusy(true);
    setMessage("");
    try {
      setDraft(await generateInterviewDraft());
    } catch {
      setMessage("Kimi draft unavailable. The preset is available below.");
      setDraft(null);
    } finally {
      setBusy(false);
    }
  }

  const current = draft ?? preset;
  return (
    <section aria-labelledby="draft-title" className="space-y-4 rounded-xl border p-5">
      <h2 id="draft-title" className="text-xl font-semibold">Outreach draft</h2>
      <div aria-live="polite" className="space-y-3">
        <p className="text-sm font-medium text-muted-foreground">
          {draft
            ? `${draft.source === "cached" ? "Cached Kimi result" : "Live Kimi generation"} · ${draft.model}`
            : "Preset draft · Written for this demo"}
        </p>
        <p className="font-semibold">{current.subject}</p>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{current.body}</p>
      </div>
      {enabled ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={requestDraft} disabled={busy}>
            {busy ? "Requesting draft…" : "Request Kimi draft"}
          </Button>
          {draft && <Button variant="outline" onClick={() => setDraft(null)}>Show preset</Button>}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Live generation is unavailable in this deployment.</p>
      )}
      {message && <p role="status" className="text-sm text-muted-foreground">{message}</p>}
    </section>
  );
}
