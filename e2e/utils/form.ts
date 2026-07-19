/**
 * Drives the prospect form. Field aria-labels are English and stable; visible
 * button text is localized, so buttons are addressed by their Chinese label
 * (the default UI language).
 */

import type { Page } from "@playwright/test";
import type { ProspectPayload } from "../fixtures/prospects";

export async function fillProspectForm(
  page: Page,
  payload: ProspectPayload,
): Promise<void> {
  await page.getByLabel("Company name").fill(payload.company.name);
  await page.getByLabel("Company website").fill(payload.company.website);

  // The form ships with two source rows; add more only if the fixture needs them.
  for (let i = 2; i < payload.company.sources.length; i++) {
    await page.getByRole("button", { name: "添加来源" }).click();
  }
  for (const [index, source] of payload.company.sources.entries()) {
    await page.getByLabel(`Source ${index + 1} name`).fill(source.source);
    await page.getByLabel(`Source ${index + 1} reference`).fill(source.reference);
  }

  for (const [index, signal] of payload.company.signals.entries()) {
    await page.getByRole("button", { name: "添加信号" }).click();
    await page.getByLabel(`Signal ${index + 1} kind`).selectOption(signal.kind);
    await page.getByLabel(`Signal ${index + 1} detail`).fill(signal.detail);
  }

  await page.getByLabel("Contact name").fill(payload.contact.name);
  await page.getByLabel("Contact title").fill(payload.contact.title);
  await page.getByLabel("Contact email").fill(payload.contact.email);
  await page.getByLabel("Contact source").fill(payload.contact.source);

  await page.getByLabel("Sender name").fill(payload.sender.name);
  await page.getByLabel("Sender company").fill(payload.sender.company);
  await page.getByLabel("Value proposition").fill(payload.sender.value_proposition);
}

export async function submitAnalysis(page: Page): Promise<void> {
  await page.getByRole("button", { name: "分析潜在客户" }).click();
}

/** Company id is surfaced in the URL once the analysis lands. */
export async function companyIdFromUrl(page: Page): Promise<string> {
  await page.waitForURL(/company_id=/, { timeout: 90_000 });
  const id = new URL(page.url()).searchParams.get("company_id");
  if (!id) throw new Error(`no company_id in URL: ${page.url()}`);
  return id;
}
