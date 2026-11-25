"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  changeMailCampaign, createMailCampaign, getMailCampaign, getMailConfig,
  listMailCampaigns, listMailMessages, type MailCampaign, type MailCampaignAction,
  type MailPreview,
} from "@/lib/api";

const label: Record<string, string> = {
  draft: "待审批", active: "已启用", paused: "已暂停", cancelled: "已取消",
  pending: "排队中", sending: "投递中", accepted: "服务商已接受", failed: "失败",
  unknown: "待核对", suppressed: "已拦截", delivered: "已送达",
  hard_bounced: "硬退信", unsubscribed: "已退订", complained: "投诉",
};

const input = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2";
const pageSize = 20;

function InputField({
  name, title, defaultValue, required,
}: {
  name: string; title: string; defaultValue?: string; required?: boolean;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium">
      {title}
      <input className={input} name={name} defaultValue={defaultValue} required={required} />
    </label>
  );
}

function numbers(values: Record<string, number>) {
  return Object.entries(values).map(([status, count]) => (
    <span className="rounded-md bg-slate-100 px-2 py-1 text-sm tabular-nums" key={status}>
      {label[status] ?? status} {count}
    </span>
  ));
}

export function MailCampaignWorkspace({
  initialExport, initialOutreach, initialVersion,
}: {
  initialExport: string; initialOutreach: string; initialVersion: string;
}) {
  const [mode, setMode] = useState<"template" | "draft">(initialOutreach ? "draft" : "template");
  const [campaigns, setCampaigns] = useState<MailCampaign[]>([]);
  const [selected, setSelected] = useState<MailCampaign | null>(null);
  const [messages, setMessages] = useState<MailPreview[]>([]);
  const [offset, setOffset] = useState(0);
  const [campaignOffset, setCampaignOffset] = useState(0);
  const [actor, setActor] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [configured, setConfigured] = useState<Awaited<ReturnType<typeof getMailConfig>>>();
  const hasActor = Boolean(configured?.operator_name || actor.trim());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const draftRequest = useRef<{ payload: string; id: string } | null>(null);

  function report(cause: unknown) {
    setError(cause instanceof Error ? cause.message : "操作失败");
  }

  useEffect(() => {
    let active = true;
    Promise.all([getMailConfig(), listMailCampaigns()]).then(([config, items]) => {
      if (active) {
        setConfigured(config);
        setCampaigns(items);
      }
    }).catch((cause: unknown) => { if (active) report(cause); });
    return () => { active = false; };
  }, []);

  async function select(id: string, nextOffset = 0) {
    const [campaign, rows] = await Promise.all([
      getMailCampaign(id), listMailMessages(id, nextOffset),
    ]);
    setSelected(campaign);
    setMessages(rows);
    setOffset(nextOffset);
    setConfirmed(false);
  }

  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await operation();
    } catch (cause) {
      report(cause);
    } finally {
      setBusy(false);
    }
  }

  function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const shared = {
      name: value("name"), subject: value("subject") || undefined, body: value("body") || undefined,
    };
    const payload = mode === "template"
      ? { ...shared, export_id: value("export_id") }
      : {
          ...shared, outreach_id: value("outreach_id"),
          draft_version: Number(value("version")), recipient: value("recipient"),
        };
    const serialized = JSON.stringify(payload);
    if (draftRequest.current?.payload !== serialized) {
      draftRequest.current = { payload: serialized, id: crypto.randomUUID() };
    }
    const id = draftRequest.current.id;
    void run(async () => {
      const created = await createMailCampaign({ id, ...payload });
      await select(created.id);
      setCampaigns(await listMailCampaigns());
      setCampaignOffset(0);
      draftRequest.current = null;
    });
  }

  function act(action: MailCampaignAction) {
    if (!selected) return;
    const id = selected.id;
    void run(async () => {
      await changeMailCampaign(id, action, configured?.operator_name ? undefined : actor.trim());
      await select(id, offset);
      setCampaigns(await listMailCampaigns(campaignOffset));
    });
  }

  function campaignPage(next: number) {
    void run(async () => {
      setCampaigns(await listMailCampaigns(next));
      setCampaignOffset(next);
    });
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-8 text-slate-900">
      <Link className="text-sm text-teal-800 underline" href="/">返回获客工作台</Link>
      <div className="my-5 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-3xl font-semibold">开发信投递</h1>
        {configured && (
          <p className="text-sm text-slate-600">
            {configured.sender ?? "待配置发件人"} · {configured.send_ready ? "投递已启用" : "投递已关闭"}
          </p>
        )}
      </div>
      {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-900">{error}</p>}
      <div className="grid items-start gap-5 lg:grid-cols-[22rem_1fr]">
        <div className="grid gap-5">
          {configured?.can_create && (
            <form className="grid gap-3 rounded-xl border bg-white p-5" onSubmit={prepare}>
              <h2 className="text-lg font-semibold">新建投递活动</h2>
              <label className="grid gap-1 text-sm font-medium">
                类型
                <select className={input} value={mode} onChange={(event) =>
                  setMode(event.target.value === "draft" ? "draft" : "template")}>
                  <option value="template">B 类 · 批量模板</option>
                  <option value="draft">A 类 · 定制草稿</option>
                </select>
              </label>
              <InputField name="name" title="活动名称" required />
              {mode === "template" ? (
                <InputField name="export_id" title="Umail 导出批次 ID" defaultValue={initialExport} required />
              ) : (
                <div className="grid gap-3">
                  <InputField name="outreach_id" title="草稿所属 Outreach ID" defaultValue={initialOutreach} required />
                  <label className="grid gap-1 text-sm font-medium">
                    草稿版本
                    <input className={input} name="version" type="number" min="1" defaultValue={initialVersion} required />
                  </label>
                  <label className="grid gap-1 text-sm font-medium">
                    收件人邮箱
                    <input className={input} name="recipient" type="email" required />
                  </label>
                </div>
              )}
              <InputField name="subject" title={mode === "template" ? "邮件主题" : "编辑主题（可选）"}
                required={mode === "template"} />
              <label className="grid gap-1 text-sm font-medium">
                {mode === "template" ? "邮件正文" : "编辑正文（可选）"}
                <textarea className={input} name="body" rows={5} maxLength={20000} required={mode === "template"} />
              </label>
              {mode === "template" && (
                <p className="text-xs text-slate-600">变量 { "{first_name}、{company}、{job_title}" }</p>
              )}
              <Button type="submit" disabled={busy || !configured?.sender}>生成预览</Button>
            </form>
          )}

          <section className="grid gap-2 rounded-xl border bg-white p-5">
            <h2 className="text-lg font-semibold">投递活动</h2>
            {campaigns.length === 0 && <p className="text-sm text-slate-600">此页暂无活动</p>}
            {campaigns.map((item) => (
              <button key={item.id} type="button" disabled={busy}
                className={`rounded-lg border px-3 py-2 text-left text-sm ${selected?.id === item.id ? "bg-teal-50" : ""}`}
                onClick={() => void run(() => select(item.id))}>
                {item.name} · {label[item.status]}
              </button>
            ))}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={busy || campaignOffset === 0}
                onClick={() => campaignPage(campaignOffset - pageSize)}>上一页</Button>
              <Button variant="outline" size="sm" disabled={busy || campaigns.length < pageSize}
                onClick={() => campaignPage(campaignOffset + pageSize)}>下一页</Button>
            </div>
          </section>
        </div>

        {selected && (
          <section className="grid gap-4 rounded-xl border bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-xl font-semibold">{selected.name}</h2>
                <p className="text-sm text-slate-600">{label[selected.status]} · {selected.sender_address}</p>
                {selected.approved_by && <p className="text-sm">审批人 {selected.approved_by}</p>}
              </div>
              <Button variant="outline" size="sm" disabled={busy}
                onClick={() => void run(() => select(selected.id, offset))}>刷新</Button>
            </div>
            <div className="flex flex-wrap gap-2">{numbers(selected.counts)}{numbers(selected.feedback)}</div>
            {configured?.can_approve && (
              <Link className="text-sm text-teal-800 underline"
                href={`/api/v1/mail-campaigns/${selected.id}/audit`}>
                查看活动操作记录
              </Link>
            )}
            {selected.status !== "cancelled" && (configured?.can_approve || configured?.can_manage) && (
              <div className="grid gap-2 border-b pb-4">
                {configured.operator_name ? (
                  <p className="text-sm">当前操作人 {configured.operator_name}</p>
                ) : (
                  <label className="grid max-w-xs gap-1 text-sm font-medium">
                    操作署名
                    <input className={input} value={actor} maxLength={160}
                      onChange={(event) => setActor(event.target.value)} />
                  </label>
                )}
                {selected.status === "draft" && configured.can_approve && (
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                    已核对收件人和正文，批准投递此活动
                  </label>
                )}
                <div className="flex flex-wrap gap-2">
                  {selected.status === "draft" && configured.can_approve && (
                    <Button disabled={busy || !hasActor || !confirmed || !configured.send_ready}
                      onClick={() => act("approve")}>审批并加入投递队列</Button>
                  )}
                  {selected.status === "active" && configured.can_pause && (
                    <Button disabled={busy || !hasActor} onClick={() => act("pause")}>暂停</Button>
                  )}
                  {selected.status === "paused" && configured.can_manage && (
                    <Button disabled={busy || !hasActor || !configured.send_ready}
                      onClick={() => act("resume")}>恢复</Button>
                  )}
                  {configured.can_manage && (
                    <Button variant="outline" disabled={busy || !hasActor} onClick={() => {
                      if (window.confirm("取消后将停止领取剩余邮件，已领取的邮件仍可能送出。")) act("cancel");
                    }}>取消活动</Button>
                  )}
                </div>
              </div>
            )}
            <h3 className="font-semibold">逐封预览与投递状态</h3>
            <p className="text-sm text-slate-600">投递时，每封信末尾会附上该收件人的退订链接。</p>
            {messages.map((mail) => (
              <details key={mail.id} className="rounded-lg border p-3">
                <summary className="cursor-pointer break-words text-sm">
                  {mail.recipient} · {label[mail.status] ?? mail.status} · {mail.subject}
                </summary>
                <p className="mt-2 break-words text-xs text-slate-600">
                  投递 ID {mail.id} · 尝试 {mail.attempt} 次 {mail.result_code ?? ""}
                </p>
                <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm">{mail.body}</pre>
              </details>
            ))}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={busy || offset === 0}
                onClick={() => void run(() => select(selected.id, offset - pageSize))}>上一页</Button>
              <Button variant="outline" size="sm" disabled={busy || messages.length < pageSize}
                onClick={() => void run(() => select(selected.id, offset + pageSize))}>下一页</Button>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
