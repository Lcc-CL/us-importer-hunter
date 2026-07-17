import { MvpAnalysisPage } from "@/features/mvp-analysis";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ company_id?: string | string[] }>;
}) {
  const companyId = (await searchParams).company_id;
  return (
    <MvpAnalysisPage
      initialCompanyId={typeof companyId === "string" ? companyId : undefined}
    />
  );
}
