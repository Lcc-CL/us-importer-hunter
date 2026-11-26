import type { Metadata } from "next";
import { DraftPreview } from "@/features/interview-demo/draft-preview";

export const metadata: Metadata = {
  title: "Interview Demo | US Importer Hunter",
  description: "Review a freight prospect and an outreach draft using a synthetic case.",
};

export default function InterviewDemoPage() {
  return (
    <main lang="en" className="mx-auto w-full max-w-3xl space-y-8 px-6 py-12">
      <header className="space-y-3 border-b pb-6">
        <p className="text-sm font-medium text-muted-foreground">US Importer Hunter</p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Interview Demo</h1>
        <p className="text-muted-foreground">
          Walk through a synthetic freight opportunity. The preset is available offline
          from the model provider and uses no customer records.
        </p>
      </header>
      <section aria-labelledby="case-title" className="space-y-3 rounded-xl border p-5">
        <p className="text-sm font-medium">Preset · Synthetic case</p>
        <h2 id="case-title" className="text-xl font-semibold">Cedar Harbor Demo Imports</h2>
        <dl className="space-y-2 text-sm">
          <div><dt className="font-medium">Scenario evidence</dt><dd>Inbound home storage products through Long Beach.</dd></div>
          <div><dt className="font-medium">Missing evidence</dt><dd>Shipment volume, carrier and decision-maker identity are unknown.</dd></div>
          <div><dt className="font-medium">Qualification</dt><dd>Manual review required.</dd></div>
        </dl>
      </section>
      <DraftPreview />
      <p className="text-sm text-muted-foreground">Drafts are for human review. This demo has no sending action.</p>
    </main>
  );
}
