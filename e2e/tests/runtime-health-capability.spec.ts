import { expect, test, type Page } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";

type MockDependency = {
  name: string;
  healthy: boolean;
  detail?: string | null;
  status?: "healthy" | "unavailable" | "unknown";
  reason_code?: string;
  last_seen_at?: string | null;
  age_seconds?: number | null;
};

const FAKE_RUNTIME = {
  provider: "fake",
  model: "fake-static-v1",
  research_provider: "fake",
  research_model: "fake-research-v1",
  environment: "test",
  real_data_gate: "blocked",
};

async function mockReadiness(
  page: Page,
  deps: MockDependency[],
  status: "ready" | "degraded" = "degraded",
) {
  await page.route(/\/api\/v1\/health\/ready$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status, dependencies: deps }),
    }),
  );
}

async function mockRuntime(page: Page, runtime: Record<string, unknown>) {
  await page.route(/\/api\/v1\/health\/runtime$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(runtime),
    }),
  );
}

async function mockLiveness(page: Page, ok: boolean) {
  await page.route(/\/api\/v1\/health$/, (route) =>
    route.fulfill({
      status: ok ? 200 : 503,
      contentType: "application/json",
      body: ok
        ? JSON.stringify({ status: "ok", app: "us-importer-hunter", environment: "test" })
        : JSON.stringify({
            code: "backend_unavailable",
            message: "Backend unavailable",
            request_id: "test-request",
          }),
    }),
  );
}

const healthyDeps: MockDependency[] = [
  { name: "postgres", healthy: true, detail: null },
  { name: "redis", healthy: true, detail: null },
  {
    name: "worker",
    healthy: true,
    detail: null,
    status: "healthy",
    reason_code: "WORKER_HEARTBEAT_OK",
    last_seen_at: new Date().toISOString(),
    age_seconds: 0.4,
  },
];

async function expectHealthyCard(page: Page) {
  const card = page.getByTestId("runtime-status-card");
  await expect(card).toHaveAttribute("data-health-phase", "healthy");
  await expect(card).toContainText("系统运行正常");
  for (const label of ["backend", "postgresql", "redis", "worker"]) {
    await expect(page.getByTestId(`component-status-${label}`)).toHaveText("正常");
  }
}

test("all four components healthy: card, same-origin proxy, and refresh recovery", async ({
  page,
}) => {
  const consoleGuard = attachConsoleGuard(page);
  await mockLiveness(page, true);
  await mockReadiness(page, healthyDeps, "ready");
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  const readinessRequest = page.waitForRequest(/\/api\/v1\/health\/ready$/);
  await readinessRequest;
  await expectHealthyCard(page);
  await expect(page.getByTestId("runtime-no-real-writes")).toBeVisible();

  const requests = await page.evaluate(() =>
    performance.getEntriesByType("resource").map((entry) => entry.name),
  );
  const healthUrls = requests.filter((url) => url.includes("/api/v1/health"));
  expect(healthUrls.length).toBeGreaterThan(0);
  for (const url of healthUrls) {
    expect(new URL(url).origin).toBe(new URL(page.url()).origin);
  }

  await page.reload({ waitUntil: "networkidle" });
  await expectHealthyCard(page);
  expect(consoleGuard.problems()).toEqual([]);
});

test("worker unavailable: preflight stays enabled and formal import is disabled", async ({
  page,
}) => {
  const consoleGuard = attachConsoleGuard(page);
  await mockLiveness(page, true);
  await mockReadiness(page, [
    { name: "postgres", healthy: true, detail: null },
    { name: "redis", healthy: true, detail: null },
    {
      name: "worker",
      healthy: false,
      detail: "worker heartbeat missing",
      status: "unavailable",
      reason_code: "WORKER_HEARTBEAT_MISSING",
      last_seen_at: null,
      age_seconds: null,
    },
  ]);
  await mockRuntime(page, FAKE_RUNTIME);
  await page.route("**/api/v1/acceptance/netease-preflight", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        file_type: "csv",
        file_size_bytes: 128,
        file_sha256: "a".repeat(64),
        encoding: "utf-8",
        sheets: ["CSV"],
        selected_sheet: "CSV",
        total_rows: 2,
        analyzed_rows: 2,
        inferred_data_type: "mixed",
        mapping_profile: "netease-foreign-trade-v1",
        suggested_mapping: {
          company_name: "公司名称",
          contact_email: "邮箱",
          product_description: "产品",
        },
        mapping_confidence: {
          company_name: "high",
          contact_email: "medium",
          product_description: "medium",
        },
        source_columns: ["公司名称", "邮箱", "产品", "未识别列"],
        sample_values: {
          company_name: "A••••s",
          contact_email: "a•a@e•••••e.test",
          product_description: "h••••s",
        },
        manual_mapping_applied: false,
        unknown_fields: ["未识别列"],
        missing_required_fields: [],
        duplicate_columns: [],
        empty_rows: 0,
        invalid_rows: 0,
        estimated_company_count: 1,
        estimated_contact_count: 2,
        estimated_trade_record_count: 2,
        coverage: {},
        estimated_high_confidence_reviews: 0,
        estimated_medium_confidence_reviews: 0,
        no_business_side_effects: true,
        real_data_gate: "blocked",
      }),
    }),
  );

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(card).toContainText("后台任务暂不可用");
  await expect(page.getByTestId("component-status-worker")).toHaveText("异常");
  await expect(page.getByTestId("runtime-worker-reason")).toContainText(
    "WORKER_HEARTBEAT_MISSING",
  );

  await page.getByTestId("bulk-import-file").setInputFiles({
    name: "acceptance.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("公司名称,邮箱,产品\nAtlas,a@example.test,hinges\n"),
  });
  const preflight = page.getByTestId("netease-preflight");
  await expect(preflight).toBeEnabled();
  await preflight.click();
  await expect(page).toHaveURL(/step=2/);
  await page.getByTestId("netease-mapping-confirmed").check();
  const upload = page.getByTestId("bulk-import-upload");
  await expect(upload).toBeDisabled();
  await expect(page.getByTestId("bulk-import-disabled-reason")).toContainText(
    "后台 Worker 不可用",
  );
  expect(consoleGuard.problems()).toEqual([]);
});

test("backend unavailable: all API operations disabled but file selection remains", async ({
  page,
}) => {
  await mockLiveness(page, false);
  await mockReadiness(page, healthyDeps, "ready");
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(card).toHaveAttribute("data-health-phase", "unavailable");
  await expect(card).toContainText("无法连接后端服务");
  await expect(page.getByTestId("bulk-import-file")).toBeEnabled();
  await expect(page.getByTestId("netease-preflight")).toBeDisabled();
  await expect(page.getByTestId("bulk-import-upload")).toHaveCount(0);
});

test("postgres unavailable: read-only preflight works, writes disabled", async ({
  page,
}) => {
  await mockLiveness(page, true);
  await mockReadiness(page, [
    { name: "postgres", healthy: false, detail: "database connection check failed" },
    { name: "redis", healthy: true, detail: null },
    { name: "worker", healthy: true, detail: null },
  ]);
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(card).toContainText("数据库暂不可用");
  await expect(page.getByTestId("component-status-postgresql")).toHaveText("异常");

  await page.getByTestId("bulk-import-file").setInputFiles({
    name: "acceptance.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("公司名称,邮箱,产品\nAtlas,a@example.test,hinges\n"),
  });
  await expect(page.getByTestId("netease-preflight")).toBeEnabled();
  await page.getByTestId("acceptance-real-data-mode").check();
  const realWrite = page.getByTestId("runtime-real-write");
  await expect(realWrite).toHaveText("禁用");
});

test("redis unavailable: worker unknown with reason, background tasks disabled", async ({
  page,
}) => {
  await mockLiveness(page, true);
  await mockReadiness(page, [
    { name: "postgres", healthy: true, detail: null },
    { name: "redis", healthy: false, detail: "cache connection check failed" },
    {
      name: "worker",
      healthy: false,
      detail: "worker status unknown because Redis is unavailable",
      status: "unknown",
      reason_code: "REDIS_UNAVAILABLE",
      last_seen_at: null,
      age_seconds: null,
    },
  ]);
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(card).toContainText("任务协调服务暂不可用");
  await expect(page.getByTestId("component-status-worker")).toHaveText("未知");
  await expect(page.getByTestId("runtime-worker-reason")).toContainText(
    "REDIS_UNAVAILABLE",
  );
});

test("unknown worker is never rendered as a dash and never treated as healthy", async ({
  page,
}) => {
  await mockLiveness(page, true);
  // Backend omits the worker dependency entirely (older/partial payload).
  await mockReadiness(page, [
    { name: "postgres", healthy: true, detail: null },
    { name: "redis", healthy: true, detail: null },
  ]);
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(page.getByTestId("component-status-worker")).toHaveText("未知");
  await expect(card).not.toContainText("—");
  await expect(page.getByTestId("runtime-mode-worker")).toHaveText("未知");
});

test("fake mode states clearly that no real writes are produced", async ({
  page,
}) => {
  await mockLiveness(page, true);
  await mockReadiness(page, healthyDeps, "ready");
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  await expectHealthyCard(page);
  await expect(page.getByTestId("runtime-data-mode")).toHaveText("合成测试");
  await expect(page.getByTestId("runtime-provider-label")).toContainText("Fake");
  await expect(page.getByTestId("runtime-external-calls")).toContainText("未调用");
  await expect(page.getByTestId("runtime-no-real-writes")).toContainText(
    "当前不会产生真实业务写入",
  );
});

test("real mode never shows fake-static-v1 as main copy", async ({ page }) => {
  await mockLiveness(page, true);
  await mockReadiness(page, healthyDeps, "ready");
  await mockRuntime(page, {
    ...FAKE_RUNTIME,
    provider: "openai",
    model: "gpt-test-model",
    real_data_gate: "enabled",
  });

  await page.goto("/");
  await expectHealthyCard(page);
  await page.getByTestId("acceptance-real-data-mode").check();
  await expect(page.getByTestId("runtime-data-mode")).toHaveText("真实数据");
  await expect(page.getByTestId("runtime-provider-label")).toContainText("真实 AI");
  await expect(page.getByTestId("runtime-real-write")).toHaveText("启用");
  const card = page.getByTestId("runtime-status-card");
  await expect(card).not.toContainText("fake-static-v1");
  await expect(page.getByTestId("runtime-no-real-writes")).toHaveCount(0);
});

test("layout: health card never overlaps the hero, desktop and mobile", async ({
  page,
}) => {
  await mockLiveness(page, true);
  await mockReadiness(page, healthyDeps, "ready");
  await mockRuntime(page, FAKE_RUNTIME);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expectHealthyCard(page);
  const heroBox = await page.getByRole("heading", { level: 1 }).boundingBox();
  const cardBox = await page.getByTestId("runtime-status-card").boundingBox();
  expect(heroBox).not.toBeNull();
  expect(cardBox).not.toBeNull();
  expect(cardBox!.y >= heroBox!.y + heroBox!.height || cardBox!.x >= heroBox!.x + heroBox!.width).toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("runtime-status-card")).toBeVisible();
  const mobileHeroBox = await page.getByRole("heading", { level: 1 }).boundingBox();
  const mobileCardBox = await page.getByTestId("runtime-status-card").boundingBox();
  expect(mobileHeroBox).not.toBeNull();
  expect(mobileCardBox).not.toBeNull();
  expect(mobileCardBox!.y).toBeGreaterThanOrEqual(mobileHeroBox!.y + mobileHeroBox!.height);
});

test("worker recovers to healthy after heartbeat returns", async ({ page }) => {
  let workerHealthy = false;
  await mockLiveness(page, true);
  await page.route(/\/api\/v1\/health\/ready$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: workerHealthy ? "ready" : "degraded",
        dependencies: workerHealthy
          ? healthyDeps
          : [
              { name: "postgres", healthy: true, detail: null },
              { name: "redis", healthy: true, detail: null },
              {
                name: "worker",
                healthy: false,
                detail: "worker heartbeat missing",
                status: "unavailable",
                reason_code: "WORKER_HEARTBEAT_MISSING",
                last_seen_at: null,
                age_seconds: null,
              },
            ],
      }),
    }),
  );
  await mockRuntime(page, FAKE_RUNTIME);

  await page.goto("/");
  const card = page.getByTestId("runtime-status-card");
  await expect(page.getByTestId("component-status-worker")).toHaveText("异常");

  workerHealthy = true;
  await page.getByTestId("runtime-retry").click();
  await expectHealthyCard(page);
});
