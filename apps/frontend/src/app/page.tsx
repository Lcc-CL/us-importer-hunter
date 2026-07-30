import { MvpAnalysisPage } from "@/features/mvp-analysis";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{
    company_id?: string | string[];
    task_id?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const companyId = params.company_id;
  const taskId = params.task_id;
  return (
    <MvpAnalysisPage
      initialCompanyId={typeof companyId === "string" ? companyId : undefined}
      initialTaskId={typeof taskId === "string" ? taskId : undefined}
    />
  );
}
