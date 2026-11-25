"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getMailOperations, type MailQueueStatus } from "@/lib/api";

const refreshMs = 30_000;
const dispatchLabel: Record<MailQueueStatus["dispatch_state"], string> = {
  disabled: "投递已关闭",
  not_configured: "投递配置不完整",
  worker_config_mismatch: "Worker 发送或审批配置不一致",
  no_worker: "没有匹配的投递 Worker",
  poll_stale: "Worker 在线，领取轮询已停更",
  polling: "Worker 正在轮询",
};

const clock = new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "medium" });

function stamp(value: string | null): string {
  return value ? clock.format(new Date(value)) : "—";
}

function waiting(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`;
}

export function MailOperationsPanel() {
  const [status, setStatus] = useState<MailQueueStatus>();
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;

    async function load() {
      try {
        if (document.visibilityState === "visible") {
          const snapshot = await getMailOperations();
          if (live) {
            setStatus(snapshot);
            setFailed(false);
          }
        }
      } catch {
        if (live) setFailed(true);
      } finally {
        if (live) timer = setTimeout(load, refreshMs);
      }
    }

    void load();
    return () => { live = false; clearTimeout(timer); };
  }, [refresh]);

  const queue = status?.queue;
  const metrics = queue ? [
    ["待领取", queue.ready],
    ["排程未到", queue.scheduled],
    ["活动已暂停", queue.paused],
    ["配置或历史审批拦截", queue.blocked],
    ["投递中", queue.in_flight],
    ["租约已超时", queue.expired_leases],
    ["待核对", queue.unknown],
    ["最老待领取", waiting(queue.oldest_ready_seconds)],
  ] : [];

  return (
    <section aria-labelledby="mail-operations-title" className="mb-5 rounded-xl border bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="mail-operations-title" className="text-lg font-semibold">投递运行</h2>
          {status && <p className="mt-1 text-sm text-slate-700">{dispatchLabel[status.dispatch_state]}</p>}
        </div>
        <Button type="button" size="sm" variant="outline" onClick={() => setRefresh((n) => n + 1)}>
          刷新运行状态
        </Button>
      </div>
      {failed && (
        <p role="status" className="mt-2 text-sm text-amber-900">
          {queue ? "刷新失败，当前显示上次采样。" : "暂时无法读取投递运行状态。"}
        </p>
      )}
      {!queue && !failed && <p className="mt-2 text-sm text-slate-500">正在读取队列…</p>}
      {queue && (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
            {metrics.map(([name, value]) => (
              <div className="rounded-lg bg-slate-50 px-3 py-2" key={name}>
                <dt className="text-xs text-slate-600">{name}</dt>
                <dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-600">
            <div><dt className="inline">Worker 在线 </dt><dd className="inline">{queue.live_workers}</dd></div>
            <div><dt className="inline">配置匹配 </dt><dd className="inline">{queue.compatible_workers}</dd></div>
            <div><dt className="inline">近期轮询 </dt><dd className="inline">{queue.polling_workers}</dd></div>
            <div><dt className="inline">最近轮询 </dt><dd className="inline">{stamp(queue.last_poll_at)}</dd></div>
            <div><dt className="inline">最近完成 SMTP 尝试 </dt><dd className="inline">{stamp(queue.last_completion_at)}</dd></div>
            <div><dt className="inline">采样时间 </dt><dd className="inline">{stamp(queue.observed_at)}</dd></div>
          </dl>
        </>
      )}
    </section>
  );
}
