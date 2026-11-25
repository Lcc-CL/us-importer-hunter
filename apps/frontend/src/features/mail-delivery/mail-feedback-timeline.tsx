"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { listMailDeliveryFeedback, type MailFeedbackEvent } from "@/lib/api";

const pageSize = 20;
const eventLabel: Record<MailFeedbackEvent["kind"], string> = {
  delivered: "已送达",
  hard_bounced: "硬退信",
  unsubscribed: "已退订",
  complained: "投诉",
};
const clock = new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "medium" });

function sourceLabel(source: string): string {
  if (source === "one_click") return "一键退订";
  if (source === "legacy") return "旧版回调";
  return source.startsWith("provider:") ? source.slice("provider:".length) : source;
}

export function MailFeedbackTimeline({
  campaignId, deliveryId,
}: {
  campaignId: string;
  deliveryId: string;
}) {
  const [visible, setVisible] = useState(false);
  const [events, setEvents] = useState<MailFeedbackEvent[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function load(next: number) {
    setLoading(true);
    setError(false);
    try {
      setEvents(await listMailDeliveryFeedback(campaignId, deliveryId, next));
      setOffset(next);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-3 grid gap-2 border-t pt-3">
      <Button type="button" size="sm" variant="outline" className="justify-self-start"
        disabled={loading} aria-expanded={visible} onClick={() => {
          setVisible(!visible);
          if (!visible) void load(0);
        }}>
        {visible ? "收起投递反馈" : "查看投递反馈"}
      </Button>
      {visible && (
        <div className="grid gap-2">
          {loading && <p role="status" className="text-sm">正在读取投递反馈…</p>}
          {error && <p role="status" className="text-sm text-amber-900">暂时无法读取投递反馈。</p>}
          {!loading && !error && events.length === 0 && <p className="text-sm">此页暂无反馈。</p>}
          <ul className="grid gap-2">
            {events.map((event) => (
              <li key={event.event_key} className="rounded-md bg-slate-50 p-2 text-xs text-slate-700">
                <p className="font-medium">{eventLabel[event.kind]} · {sourceLabel(event.source)}</p>
                {event.occurred_at && <p>服务商时间 {clock.format(new Date(event.occurred_at))}</p>}
                <p>系统接收 {clock.format(new Date(event.received_at))}</p>
                <p className="break-all">事件 {event.event_key}</p>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" disabled={loading}
              onClick={() => void load(offset)}>刷新</Button>
            <Button type="button" size="sm" variant="outline" disabled={loading || offset === 0}
              onClick={() => void load(offset - pageSize)}>上一页</Button>
            <Button type="button" size="sm" variant="outline" disabled={loading || events.length < pageSize}
              onClick={() => void load(offset + pageSize)}>下一页</Button>
          </div>
        </div>
      )}
    </div>
  );
}
