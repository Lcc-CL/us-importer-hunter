"use client";

import { useEffect, useState } from "react";
import { Anchor, ExternalLink, Languages } from "lucide-react";

import {
  API_BASE_URL,
  analyzeProspect,
  approveDraft,
  getClientErrorDetails,
  getProspect,
  type ClientErrorDetails,
  type DraftApprovalResponse,
  type ProspectAnalysisRequest,
  type ProspectAnalysisResponse,
  type ProspectDetailResponse,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MvpPageState, SubmittedProspectContext } from "../types";
import { AnalysisResult } from "./analysis-result";
import { ProspectForm } from "./prospect-form";
import { ProviderBadge } from "./provider-badge";
import { RESEARCH_ENABLED, ResearchPanel } from "@/features/research";
import type { ApplicationPayload } from "@/lib/research-api";

interface MvpAnalysisPageProps {
  initialCompanyId?: string;
}

function pageStateForAnalysis(result: ProspectAnalysisResponse): MvpPageState {
  if (result.overall_status === "COMPLETED") return "success";
  if (result.overall_status === "PARTIAL") return "partial";
  if (result.overall_status === "REJECTED") return "rejected";
  return "error";
}

export function MvpAnalysisPage({ initialCompanyId }: MvpAnalysisPageProps) {
  const { t, lang, setLang } = useI18n();
  const [analysis, setAnalysis] = useState<ProspectAnalysisResponse | null>(null);
  const [detail, setDetail] = useState<ProspectDetailResponse | null>(null);
  const [approval, setApproval] = useState<DraftApprovalResponse | null>(null);
  const [error, setError] = useState<ClientErrorDetails | null>(null);
  const [companyId, setCompanyId] = useState<string | null>(initialCompanyId ?? null);
  const [context, setContext] = useState<SubmittedProspectContext | null>(null);
  const [approverName, setApproverName] = useState("");
  const [pageState, setPageState] = useState<MvpPageState>(
    initialCompanyId ? "refreshing" : "idle",
  );
  // Research fills the form; it never submits it. The version counter lets the
  // same payload be applied again after the user edits the fields.
  const [appliedPayload, setAppliedPayload] = useState<{
    version: number;
    payload: ApplicationPayload;
  } | null>(null);

  useEffect(() => {
    if (!initialCompanyId) return;
    let active = true;

    async function loadInitialResult() {
      try {
        const saved = await getProspect(initialCompanyId as string);
        if (!active) return;
        setDetail(saved);
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
  }, [initialCompanyId]);

  const isBusy =
    pageState === "submitting" ||
    pageState === "refreshing" ||
    pageState === "approving";

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

        <div className="grid items-start gap-7 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div>
            {RESEARCH_ENABLED ? (
              <ResearchPanel
                onApply={(payload) =>
                  setAppliedPayload((current) => ({
                    version: (current?.version ?? 0) + 1,
                    payload,
                  }))
                }
              />
            ) : null}
            <ProspectForm
              appliedPayload={appliedPayload}
              disabled={isBusy}
              onSubmit={handleAnalyze}
            />
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
