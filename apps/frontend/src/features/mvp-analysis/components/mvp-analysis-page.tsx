"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { Anchor, ExternalLink, Languages } from "lucide-react";

import {
  API_BASE_URL,
  ApiError,
  analyzeProspect,
  approveDraft,
  getClientErrorDetails,
  getImportEvidence,
  getProspect,
  uploadImportEvidence,
  type ClientErrorDetails,
  type DraftApprovalResponse,
  type EvidenceUploadResponse,
  type ProspectAnalysisRequest,
  type ProspectAnalysisResponse,
  type ProspectDetailResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MvpPageState, SubmittedProspectContext } from "../types";
import { AnalysisResult } from "./analysis-result";
import { ImportEvidencePanel } from "./import-evidence-panel";
import { ProspectForm } from "./prospect-form";
import { ProviderBadge } from "./provider-badge";
import { DiscoveryTaskPanel } from "@/features/discovery";
import { RESEARCH_ENABLED, ResearchPanel } from "@/features/research";
import type { FlowStep, StepState } from "@/features/research/step-nav";
import { ContactDiscoveryCard } from "./contact-discovery-card";
import { MissingFieldsPrompt } from "./guided-flow";
import {
  discoverContacts,
  type ContactDiscovery,
  type RankedContact,
} from "@/lib/research-api";
import {
  clearSenderProfile,
  mergeSenderProfile,
  saveSenderProfile,
  senderProfileServerSnapshot,
  senderProfileSnapshot,
  subscribeSenderProfile,
} from "../sender-profile";
import {
  EMPTY_CONTACT,
  EMPTY_SENDER,
  buildAnalysisRequest,
  missingFieldsFor,
  type MissingFields,
  type ProspectContact,
  type ProspectSender,
} from "../prospect-state";
import type { ApplicationPayload } from "@/lib/research-api";

interface MvpAnalysisPageProps {
  initialCompanyId?: string;
  initialTaskId?: string;
  initialBatchId?: string;
  initialCalibrationId?: string;
  initialResearchId?: string;
}

function pageStateForAnalysis(result: ProspectAnalysisResponse): MvpPageState {
  if (result.overall_status === "COMPLETED") return "success";
  if (result.overall_status === "PARTIAL") return "partial";
  if (result.overall_status === "REJECTED") return "rejected";
  return "error";
}

export function MvpAnalysisPage({
  initialCompanyId,
  initialTaskId,
  initialBatchId,
  initialCalibrationId,
  initialResearchId,
}: MvpAnalysisPageProps) {
  const { t, lang, setLang } = useI18n();
  const [analysis, setAnalysis] = useState<ProspectAnalysisResponse | null>(null);
  const [detail, setDetail] = useState<ProspectDetailResponse | null>(null);
  const [approval, setApproval] = useState<DraftApprovalResponse | null>(null);
  const [evidence, setEvidence] = useState<EvidenceUploadResponse | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [error, setError] = useState<ClientErrorDetails | null>(null);
  const [companyId, setCompanyId] = useState<string | null>(initialCompanyId ?? null);
  const [context, setContext] = useState<SubmittedProspectContext | null>(null);
  const [approverName, setApproverName] = useState("");
  const [pageState, setPageState] = useState<MvpPageState>(
    initialCompanyId && !initialResearchId ? "refreshing" : "idle",
  );
  // Research fills the form; it never submits it. The version counter lets the
  // same payload be applied again after the user edits the fields.
  const [appliedPayload, setAppliedPayload] = useState<{
    version: number;
    payload: ApplicationPayload;
  } | null>(null);
  // The confirmed research is held here so the guided flow can retry the
  // analysis once the user supplies whatever was missing, without asking them
  // to run the research again.
  const [pendingResearch, setPendingResearch] = useState<ApplicationPayload | null>(null);
  // Which blocks to show is snapshotted when the flow first stops. Deriving it
  // live would unmount the prompt — and its Continue button — the moment the
  // last field became valid, so the user could never actually continue.
  const [awaitingFields, setAwaitingFields] = useState<MissingFields | null>(null);
  // One contact and one sender for the whole page. The guided prompt and the
  // advanced form are two views onto these, so filling either is immediately
  // visible in the other and the analysis always reads what the user last saw.
  const [contact, setContact] = useState<ProspectContact>(EMPTY_CONTACT);
  const [sender, setSender] = useState<ProspectSender>(EMPTY_SENDER);
  // Automatic contact discovery for the confirmed research run. Failure is a
  // valid state (COMPANY_ONLY) and never blocks the analysis.
  const [discovery, setDiscovery] = useState<ContactDiscovery | null>(null);
  const [discovering, setDiscovering] = useState(false);
  // The saved profile is external state, read through useSyncExternalStore so
  // hydration sees the server's empty snapshot first and swaps in the stored
  // values afterwards — no effect, no setState-during-render.
  const storedSender = useSyncExternalStore(
    subscribeSenderProfile,
    senderProfileSnapshot,
    senderProfileServerSnapshot,
  );
  const effectiveSender = mergeSenderProfile(sender, storedSender);
  const batchReturnHref = initialBatchId
    ? `/?${new URLSearchParams({
        ...(initialTaskId ? { task_id: initialTaskId } : {}),
        batch_id: initialBatchId,
        ...(initialCalibrationId ? { calibration_id: initialCalibrationId } : {}),
      }).toString()}#prospect-batch-panel`
    : undefined;

  const patchContact = (patch: Partial<ProspectContact>) =>
    setContact((current) => ({ ...current, ...patch }));
  const patchSender = (patch: Partial<ProspectSender>) => {
    const next = { ...effectiveSender, ...patch };
    saveSenderProfile(next);
    setSender(next);
  };
  const handleClearSenderProfile = () => {
    clearSenderProfile();
    setSender(EMPTY_SENDER);
  };

  useEffect(() => {
    if (!initialCompanyId || initialResearchId) return;
    let active = true;

    async function loadInitialResult() {
      try {
        const saved = await getProspect(initialCompanyId as string);
        if (!active) return;
        setDetail(saved);
        try {
          const currentEvidence = await getImportEvidence(initialCompanyId as string);
          if (active) setEvidence(currentEvidence);
        } catch (caught: unknown) {
          if (!(caught instanceof ApiError && caught.status === 404) && active) {
            setEvidenceError(getClientErrorDetails(caught).message);
          }
        }
        setPageState("success");
      } catch (caught: unknown) {
        if (!active) return;
        setError(getClientErrorDetails(caught));
        setPageState("error");
      }
    }

    void loadInitialResult();
    return () => {
      active = false;
    };
  }, [initialCompanyId, initialResearchId]);

  const decision = analysis?.opportunity.qualification_decision ?? null;
  const missing = missingFieldsFor(contact, effectiveSender);

  // Only a missing sender blocks the flow now; a missing contact is a valid
  // COMPANY_ONLY analysis, not a blocker.
  const senderBlocks = awaitingFields !== null && missing.sender;
  const downstreamSteps: Partial<Record<FlowStep, StepState>> = {
    analysis:
      pageState === "submitting"
        ? "current"
        : senderBlocks
          ? "blocked"
          : analysis
            ? "done"
            : "todo",
    draft: analysis?.email_draft.action === "GENERATED"
      ? "done"
      : analysis && decision && decision !== "qualified"
        ? "blocked"
        : analysis?.email_draft.action === "FAILED"
          ? "blocked"
          : "todo",
  };

  const guidedNextAction = senderBlocks ? t("guided.missing.sender") : null;
  const guidedBlockedBy = (() => {
    if (senderBlocks) {
      return t("guided.missing.senderHint");
    }
    if (!analysis) return null;
    if (decision === "review") return t("guided.result.review");
    if (decision === "research_more") return t("guided.result.researchMore");
    if (decision === "disqualified") return t("guided.result.disqualified");
    if (analysis.email_draft.action === "FAILED") return t("guided.draft.failed");
    return null;
  })();

  const isBusy =
    pageState === "submitting" ||
    pageState === "refreshing" ||
    pageState === "approving";

  /**
   * The confirmed research drives the rest of the flow.
   *
   * The old behaviour stopped here — it filled the form and left the user to
   * find the submit button. Now the payload is mapped and qualification runs
   * immediately, unless a contact or sender is genuinely missing, in which
   * case only that block is asked for.
   */
  /** A discovered contact becomes the analysis contact — never invented,
   * always carrying the page it was read from as its source. A department
   * mailbox uses its salutation ("Purchasing Team") as the addressable name,
   * so DEPARTMENT_CONTACT drafts need no manual name and invent no person. */
  const applyDiscoveredContact = (ranked: RankedContact) => {
    const found = ranked.contact;
    const isDepartment = found.source_type === "department";
    setContact({
      mode: isDepartment ? "DEPARTMENT_CONTACT" : "FULL_CONTACT",
      // Department contacts carry no person name — the backend derives the
      // salutation ("Purchasing Team") from the mailbox itself.
      name: isDepartment ? "" : found.name || found.display_name,
      title: found.title,
      email: found.email,
      linkedin_url: "",
      phone: found.phone,
      source: found.source_url,
    });
  };

  async function handleResearchConfirmed(payload: ApplicationPayload, researchId: string) {
    // A different company means the contact on screen belongs to the previous
    // prospect: contacts are per-company and must never carry over.
    const isNewCompany =
      pendingResearch !== null && payload.company_name !== pendingResearch.company_name;
    setPendingResearch(payload);
    // Still applied to the old form so Advanced editing starts pre-filled.
    setAppliedPayload((current) => ({ version: (current?.version ?? 0) + 1, payload }));
    if (isNewCompany) setContact(EMPTY_CONTACT);

    // Automatic discovery first; the manual form is the fallback, not the
    // default. A failed discovery is treated as "nothing found" and the flow
    // continues — COMPANY_ONLY analysis is always available.
    setDiscovery(null);
    setDiscovering(true);
    let found: ContactDiscovery | null = null;
    try {
      found = await discoverContacts(researchId);
      // A response that is not actually a discovery result (proxy pages,
      // stubbed environments) is treated as "nothing found", never a crash.
      if (!found || typeof found.discovery_status !== "string") found = null;
    } catch {
      found = null;
    }
    setDiscovery(found);
    setDiscovering(false);
    if (found?.primary && (isNewCompany || !contact.name.trim())) {
      applyDiscoveredContact(found.primary);
    }

    // Only the sender can still block: it is user-level, restored from the
    // saved profile, and required because a draft cannot be written without
    // knowing who is writing.
    const gap = missingFieldsFor(contact, effectiveSender);
    setAwaitingFields({ contact: false, sender: gap.sender });
  }

  async function handleGuidedContinue() {
    if (!pendingResearch || isBusy) return;
    const gap = missingFieldsFor(contact, effectiveSender);
    if (gap.sender) return;
    setAwaitingFields(null);
    await handleAnalyze(buildAnalysisRequest(pendingResearch, contact, effectiveSender));
  }

  async function handleAnalyze(request: ProspectAnalysisRequest) {
    if (isBusy) return;
    setPageState("submitting");
    setError(null);
    setAnalysis(null);
    setDetail(null);
    setApproval(null);
    setCompanyId(null);
    setContext({ contact: request.contact ?? null, senderName: request.sender.name });
    setApproverName(request.sender.name);
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.delete("company_id");
    window.history.replaceState(null, "", currentUrl);

    try {
      const result = await analyzeProspect(request);
      setAnalysis(result);
      const nextCompanyId = result.company.company_id;
      setCompanyId(nextCompanyId);
      if (nextCompanyId) {
        currentUrl.searchParams.set("company_id", nextCompanyId);
        window.history.replaceState(null, "", currentUrl);
      }
      setPageState(pageStateForAnalysis(result));
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught));
      setPageState("error");
    }
  }

  async function handleRefresh() {
    if (!companyId || isBusy) return;
    setPageState("refreshing");
    setError(null);
    try {
      const saved = await getProspect(companyId);
      setDetail(saved);
      setPageState(analysis ? pageStateForAnalysis(analysis) : "success");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught));
      setPageState("error");
    }
  }

  async function handleEvidenceUpload(file: File) {
    if (!companyId || isBusy) return;
    setEvidenceError(null);
    try {
      const senderProfile = missing.sender
        ? undefined
        : {
            name: effectiveSender.name.trim(),
            company: effectiveSender.company.trim(),
            value_proposition: effectiveSender.valueProposition.trim(),
          };
      const imported = await uploadImportEvidence(companyId, file, senderProfile);
      setEvidence(imported);
      const saved = await getProspect(companyId);
      setDetail(saved);
      setPageState("success");
    } catch (caught: unknown) {
      setEvidenceError(getClientErrorDetails(caught).message);
    }
  }

  async function handleApprove(outreachId: string, version: number) {
    if (isBusy || !approverName.trim()) return;
    setPageState("approving");
    setError(null);
    try {
      const approved = await approveDraft(outreachId, version, {
        approver_name: approverName.trim(),
      });
      setApproval(approved);
      if (companyId) {
        const saved = await getProspect(companyId);
        setDetail(saved);
      }
      setPageState(analysis ? pageStateForAnalysis(analysis) : "success");
    } catch (caught: unknown) {
      setError(getClientErrorDetails(caught));
      setPageState("error");
    }
  }

  return (
    <main className="min-h-screen bg-[#f3f7f5] text-slate-950">
      <header className="border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1540px] items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-2xl bg-slate-950 text-teal-300 shadow-sm">
              <Anchor className="size-5" />
            </div>
            <div>
              <p className="font-semibold tracking-tight text-slate-950">
                US Importer Hunter
              </p>
              <p className="text-xs text-slate-500">{t("app.tagline")}</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
              onClick={() => setLang(lang === "zh" ? "en" : "zh")}
              type="button"
            >
              <Languages className="size-3.5" /> {t("header.langSwitch")}
            </button>
            <a
              className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
              href={`${API_BASE_URL}/docs`}
              rel="noreferrer"
              target="_blank"
            >
              {t("header.apiDocs")} <ExternalLink className="size-3.5" />
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1540px] px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
        <div className="mb-8 grid gap-4 border-b border-slate-200 pb-7 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-teal-700">
              {t("hero.kicker")}
            </p>
            <h1 className="mt-2 max-w-3xl text-3xl font-semibold tracking-[-0.035em] text-slate-950 sm:text-4xl">
              {t("hero.title")}
            </h1>
          </div>
          <ProviderBadge />
        </div>

        <DiscoveryTaskPanel
          initialBatchId={initialBatchId}
          initialCalibrationId={initialCalibrationId}
          initialTaskId={initialTaskId}
        />

        <div className="grid items-start gap-7 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div>
            {RESEARCH_ENABLED ? (
              <ResearchPanel
                batchReturnHref={batchReturnHref}
                blockedBy={guidedBlockedBy}
                downstreamSteps={downstreamSteps}
                initialResearchId={initialResearchId}
                nextAction={guidedNextAction}
                onConfirmed={handleResearchConfirmed}
              />
            ) : null}

            {pendingResearch ? (
              <ContactDiscoveryCard
                discovery={discovery}
                loading={discovering}
                onManualEdit={() =>
                  setAwaitingFields((current) => ({
                    contact: true,
                    sender: current?.sender ?? missing.sender,
                  }))
                }
                onSelect={applyDiscoveredContact}
                selectedEmail={contact.email}
              />
            ) : null}

            {awaitingFields ? (
              <div className="mb-6">
                <MissingFieldsPrompt
                  busy={isBusy}
                  contact={contact}
                  missing={awaitingFields}
                  onContactChange={patchContact}
                  onClearSenderProfile={handleClearSenderProfile}
                  onContinue={handleGuidedContinue}
                  onSenderChange={patchSender}
                  sender={effectiveSender}
                  stillMissing={missing}
                />
              </div>
            ) : null}

            {/* The manual form stays as the compatibility and correction path,
                but it is no longer the main road: collapsed by default so the
                guided flow does not make the user read five sections to fix
                two fields. */}
            <details
              className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
              data-testid="advanced-form"
              open={!RESEARCH_ENABLED}
            >
              <summary className="cursor-pointer px-5 py-4 text-sm font-semibold text-slate-800 sm:px-7">
                {t("advanced.title")}
                <span className="mt-1 block text-xs font-normal text-slate-500">
                  {t("advanced.hint")}
                </span>
              </summary>
              <ProspectForm
                appliedPayload={appliedPayload}
                contact={contact}
                disabled={isBusy}
                onContactChange={patchContact}
                onSenderChange={patchSender}
                onSubmit={handleAnalyze}
                sender={effectiveSender}
              />
            </details>

            {pendingResearch || companyId ? (
              <ImportEvidencePanel
                companyId={companyId}
                disabled={isBusy}
                error={evidenceError}
                onUpload={handleEvidenceUpload}
                result={evidence}
              />
            ) : null}
          </div>
          <AnalysisResult
            analysis={analysis}
            approval={approval}
            approverName={approverName}
            companyId={companyId}
            context={context}
            detail={detail}
            error={error}
            onApprove={handleApprove}
            onApproverNameChange={setApproverName}
            onRefresh={handleRefresh}
            pageState={pageState}
          />
        </div>
      </div>
    </main>
  );
}
