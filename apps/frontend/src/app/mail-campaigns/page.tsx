import { MailCampaignWorkspace } from "@/features/mail-delivery/mail-campaign-workspace";

export default async function MailCampaignPage({
  searchParams,
}: {
  searchParams: Promise<{ export_id?: string; outreach_id?: string; version?: string }>;
}) {
  const params = await searchParams;
  return (
    <MailCampaignWorkspace
      initialExport={typeof params.export_id === "string" ? params.export_id : ""}
      initialOutreach={typeof params.outreach_id === "string" ? params.outreach_id : ""}
      initialVersion={typeof params.version === "string" ? params.version : "1"}
    />
  );
}
