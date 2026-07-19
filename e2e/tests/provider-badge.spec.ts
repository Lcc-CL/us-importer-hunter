import { expect, test } from "@playwright/test";

import { attachConsoleGuard } from "../utils/console-guard";
import { getRuntimeStatus } from "../utils/api";
import { PROVIDER_MODE } from "../utils/env";

/** Patterns that must never reach the browser. */
const SECRET_PATTERNS = [
  /sk-[A-Za-z0-9_-]{12,}/, // OpenAI-style key
  /OPENAI_API_KEY/,
  /OPENAI_BASE_URL/,
];

test.describe("provider status", () => {
  test("badge reflects the running provider and leaks no configuration", async ({
    page,
  }) => {
    const guard = attachConsoleGuard(page);
    await page.goto("/");

    const runtime = await getRuntimeStatus();
    expect(runtime.provider).toBe(PROVIDER_MODE);

    if (PROVIDER_MODE === "fake") {
      await expect(page.getByText("演示模式")).toBeVisible();
      await expect(page.getByText("真实 AI")).toHaveCount(0);
    } else {
      await expect(page.getByText("真实 AI")).toBeVisible();
      await expect(page.getByText("演示模式")).toHaveCount(0);
    }

    // The badge may name provider and model — never a credential or endpoint.
    const html = await page.content();
    for (const pattern of SECRET_PATTERNS) {
      expect(html).not.toMatch(pattern);
    }

    // The runtime endpoint itself must expose only these three fields.
    expect(Object.keys(runtime).sort()).toEqual(["environment", "model", "provider"]);

    expect(guard.problems()).toEqual([]);
  });

  test("runtime endpoint response carries no credential fields", async () => {
    const raw = await fetch(
      `${process.env.E2E_API_BASE_URL ?? "http://localhost:8001"}/api/v1/health/runtime`,
    );
    const text = await raw.text();
    expect(raw.ok).toBe(true);
    for (const pattern of SECRET_PATTERNS) {
      expect(text).not.toMatch(pattern);
    }
    expect(text.toLowerCase()).not.toContain("api_key");
    expect(text.toLowerCase()).not.toContain("base_url");
  });
});
