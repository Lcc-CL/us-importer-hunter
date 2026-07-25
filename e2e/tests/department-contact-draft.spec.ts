/**
 * DEPARTMENT_CONTACT 主链路：研究完成 → 自动发现部门邮箱（无具名联系人）→
 * 不展开手填表单 → Qualification → 部门级 Draft（称呼 Purchasing Team，
 * 不虚构姓名）→ 刷新后 Draft、部门邮箱与 Sender Profile 全部恢复。
 *
 * Fixture 驱动，全程 route mock：不触公网、不等待真实 Provider。
 */

import { expect, test, type Page } from "@playwright/test";

import { COMPLETED_RUN, confirmResponse } from "../fixtures/research";
import { attachConsoleGuard } from "../utils/console-guard";

const COMPANY_ID = "88888888-8888-8888-8888-888888888888";
const SOURCE_URL = "https://acme.example/contact";
const DEPT_EMAIL = "purchasing@example.com";
const SUBJECT = "Freight partnership for Acme Hardware";

const discovery = {
  discovery_status: "DEPARTMENT_CONTACT",
  pages_scanned: 3,
  pages_failed: 0,
  primary: {
    contact: {
      name: "",
      title: "",
      email: DEPT_EMAIL,
      phone: "",
      source_url: SOURCE_URL,
      source_type: "department",
      display_name: "Purchasing Team",
      evidence_snippet: `Contact our buyers at ${DEPT_EMAIL}`,
      confidence: 0.6,
    },
    score: 0.5,
    reasons: ["department_mailbox=purchasing"],
  },
  alternatives: [],
  supporting: [],
  rejected: [],
  review_required: true,
  selection_reasons: ["no named decision-maker on the researched pages"],
};

const analysis = {
  request_id: "11111111-1111-1111-1111-111111111111",
  overall_status: "COMPLETED",
  company: { action: "CREATED", company_id: COMPANY_ID, name: "Acme Hardware", notes: [] },
  opportunity: {
    action: "QUALIFIED",
    opportunity_id: "33333333-3333-3333-3333-333333333333",
    score: 72.5,
    confidence: 0.8,
    data_completeness: 1,
    qualification_decision: "qualified",
    recommended_action: "prepare_outreach",
    reasons: ["import signal confirmed"],
  },
  contact: { action: "CREATED", contact_id: "44444444-4444-4444-4444-444444444444", notes: [] },
  decision_maker: {
    action: "SELECTED",
    selected_contact_id: "44444444-4444-4444-4444-444444444444",
    recommended_channel: "email",
    confidence: 0.7,
    reasons: [],
  },
  email_draft: {
    action: "GENERATED",
    outreach_id: "55555555-5555-5555-5555-555555555555",
    version: 1,
    subject: SUBJECT,
    body: "Hi Purchasing Team,\n\nWe help importers simplify Asia–US freight.\n\nBest regards,",
    status: "generated",
    notes: [],
  },
  warnings: [],
  created_at: "2026-07-25T12:00:00Z",
};

const detail = {
  company: {
    company_id: COMPANY_ID,
    name: "Acme Hardware",
    website: "https://acme.example",
    verified: true,
    sources: [{ source: "company_website", reference_count: 1 }],
    signals: ["import_activity: imports hardware from Asia"],
  },
  latest_assessment: {
    opportunity_id: "33333333-3333-3333-3333-333333333333",
    score: 72.5,
    confidence: 0.8,
    data_completeness: 1,
    qualification_decision: "qualified",
    recommended_action: "prepare_outreach",
    reasons: ["import signal confirmed"],
    scoring_version: "mvp-explainable-scoring-v1",
    policy_version: "mvp-qualification-policy-v1",
    assessed_at: "2026-07-25T12:05:00Z",
    explanation: null,
  },
  qualification_decision: "qualified",
  contacts: [
    {
      contact_id: "44444444-4444-4444-4444-444444444444",
      name: "Purchasing Team",
      title: null,
      department: "purchasing",
      seniority: "unknown",
      status: "active",
      channels: [{ type: "email", value: DEPT_EMAIL, verification_status: "unverified" }],
    },
  ],
  decision_maker: {
    selected_contact_id: "44444444-4444-4444-4444-444444444444",
    rankings: [],
    selection: null,
  },
  latest_email_draft: {
    outreach_id: "55555555-5555-5555-5555-555555555555",
    version: 1,
    subject: SUBJECT,
    body: "Hi Purchasing Team,\n\nWe help importers simplify Asia–US freight.\n\nBest regards,",
    status: "generated",
    approval_status: "generated",
    approved_at: null,
    approved_by_name: null,
    provider: "fake",
    model: "fake-deterministic-v1",
    prompt_version: "mvp-email-v1",
    generated_at: "2026-07-25T12:06:00Z",
  },
  draft_history: [],
};

interface Captured {
  analyzeBodies: unknown[];
  sendAttempts: number;
}

async function stubJourney(page: Page): Promise<Captured> {
  const captured: Captured = { analyzeBodies: [], sendAttempts: 0 };
  const confirm = confirmResponse(
    [
      { kind: "import_activity", detail: "进口五金，来自亚洲" },
      { kind: "company_scale", detail: "自有仓库约 12 万平方英尺" },
    ],
    [{ source: "company_website", reference: "https://acme.example/" }],
  );

  // Sender Profile 已保存：这是用户级资料，进入页面前就存在。
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "sender_profile_v1",
      JSON.stringify({
        sender_name: "Alex Morgan",
        sender_company: "Harbor Bridge Logistics",
        value_proposition: "我们简化亚洲到美国的进口运输。",
      }),
    );
  });

  await page.route("**/api/v1/research/**", async (route) => {
    if (route.request().url().includes("/confirm")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(confirm),
      });
      return;
    }
    await route.fulfill({
      status: route.request().method() === "POST" ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(COMPLETED_RUN),
    });
  });
  // 注册在通配之后：Playwright 后注册的 handler 优先匹配。
  await page.route("**/api/v1/research/runs/*/contacts/discover", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(discovery),
    }),
  );
  await page.route("**/api/v1/mvp/prospects/analyze", async (route) => {
    captured.analyzeBodies.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(analysis),
    });
  });
  await page.route(`**/api/v1/mvp/prospects/${COMPANY_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(detail),
    }),
  );
  // 200 + 空态而不是 404：浏览器会把 404 资源记为 console error，
  // 而本 spec 要求 Console 零红色错误。
  await page.route(`**/api/v1/companies/${COMPANY_ID}/import-evidence`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "completed",
        company_id: COMPANY_ID,
        import_job_id: "99999999-9999-9999-9999-999999999999",
        aggregate_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        records_received: 0,
        records_normalized: 0,
        shipments_matched: 0,
        quality_status: "PENDING",
        quality_score: 0,
        promoted_signals: [],
        previous_qualification_score: 72.5,
        qualification_score: 72.5,
        qualification_status: "qualified",
        qualification_reasons: [],
        draft_status: "generated",
        warnings: [],
      }),
    }),
  );
  // 任何发送端点都不允许被触达。
  await page.route("**/send**", async (route) => {
    captured.sendAttempts += 1;
    await route.fulfill({ status: 500, body: "{}" });
  });

  return captured;
}

test("部门邮箱直达部门级草稿并可刷新恢复", async ({ page }) => {
  const guard = attachConsoleGuard(page);
  const captured = await stubJourney(page);
  await page.goto("/");

  // 研究完成并确认
  await page.getByLabel("Research target name").fill("Acme Hardware");
  await page.getByLabel("Research target website").fill("https://acme.example");
  await page.getByRole("button", { name: "开始自动研究" }).click();
  await expect(page.getByTestId("research-result")).toBeVisible();
  await page.getByTestId("accept-0").click();
  await page.getByTestId("accept-1").click();
  await page.getByTestId("research-confirm").click();

  // 联系人阶段：显示部门邮箱发现结果，而不是手填表单
  await expect(page.getByTestId("contact-discovery-partial")).toBeVisible();
  await expect(page.getByText(DEPT_EMAIL).first()).toBeVisible();
  await expect(page.getByRole("link", { name: SOURCE_URL })).toBeVisible();
  await expect(page.getByTestId("guided-missing-contact")).toBeHidden();
  await expect(page.getByTestId("advanced-form")).not.toHaveAttribute("open", "");

  // Sender Profile 自动恢复 → 可直接继续
  await expect(page.getByTestId("guided-continue")).toBeEnabled();
  await page.getByTestId("guided-continue").click();

  // Qualification 成功并自动生成部门级草稿
  await expect(page.getByTestId("research-step-draft")).toHaveAttribute(
    "data-state",
    "done",
  );
  await expect(page.getByText(SUBJECT)).toBeVisible();
  await expect(page.getByText("Hi Purchasing Team,")).toBeVisible();

  // 请求里的联系人是部门称呼 + 部门邮箱，没有虚构的具名联系人
  const body = captured.analyzeBodies[0] as {
    contact: { name: string; email: string; source: string };
  };
  expect(body.contact.name).toBe("Purchasing Team");
  expect(body.contact.email).toBe(DEPT_EMAIL);
  expect(body.contact.source).toBe(SOURCE_URL);

  // 刷新：Draft、部门联系人与 Sender Profile 全部恢复
  // （联系人区域按姓名/称呼展示；邮箱地址本身不在该视图渲染。）
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText(SUBJECT)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Purchasing Team" }),
  ).toBeVisible();
  const storedSender = await page.evaluate(() =>
    window.localStorage.getItem("sender_profile_v1"),
  );
  expect(storedSender).toContain("Alex Morgan");

  expect(captured.sendAttempts).toBe(0);
  expect(guard.problems()).toEqual([]);
});
