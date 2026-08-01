import { MvpAnalysisPage } from "@/features/mvp-analysis";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{
    company_id?: string | string[];
    task_id?: string | string[];
    batch_id?: string | string[];
    research_id?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const companyId = params.company_id;
  const taskId = params.task_id;
  const batchId = params.batch_id;
  const researchId = params.research_id;
  return (
    <MvpAnalysisPage
      initialCompanyId={typeof companyId === "string" ? companyId : undefined}
      initialBatchId={typeof batchId === "string" ? batchId : undefined}
      initialResearchId={typeof researchId === "string" ? researchId : undefined}
      initialTaskId={typeof taskId === "string" ? taskId : undefined}
    />
  );
}
