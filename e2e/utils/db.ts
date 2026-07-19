/**
 * Database assertions against the throwaway E2E database.
 *
 * Runs psql inside the compose postgres container so the harness needs no
 * Postgres client and no driver dependency on the host.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { DEV_DB, E2E_DB } from "./env";

/** Walk up from the working directory to the repo root (where compose lives). */
function repoRoot(): string {
  let current = process.cwd();
  for (let depth = 0; depth < 8; depth++) {
    if (existsSync(resolve(current, "docker-compose.yml"))) return current;
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }
  throw new Error(`could not locate docker-compose.yml above ${process.cwd()}`);
}

function psql(database: string, sql: string): string {
  return execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "postgres",
      "psql",
      "-U",
      process.env.POSTGRES_USER ?? "app",
      "-d",
      database,
      "-tAX",
      "-c",
      sql,
    ],
    { encoding: "utf8", cwd: repoRoot() },
  ).trim();
}

/** Query the E2E database. */
export function queryE2e(sql: string): string {
  return psql(E2E_DB, sql);
}

/** Read-only probe of the dev database, used to prove it stayed untouched. */
export function queryDev(sql: string): string {
  return psql(DEV_DB, sql);
}

export function databaseExists(name: string): boolean {
  const out = psql("postgres", `SELECT 1 FROM pg_database WHERE datname = '${name}'`);
  return out === "1";
}

export interface DraftRow {
  version: number;
  approvalStatus: string;
  provider: string;
  model: string;
  promptVersion: string;
}

export function latestDraftForCompany(companyId: string): DraftRow | null {
  const row = queryE2e(`
    SELECT d.version, d.approval_status, d.provider, d.model, d.prompt_version
    FROM email_drafts d
    JOIN outreaches o ON o.id = d.outreach_id
    JOIN opportunities op ON op.id = o.opportunity_id
    WHERE op.company_id = '${companyId}'
    ORDER BY d.version DESC LIMIT 1
  `);
  if (!row) return null;
  const [version, approvalStatus, provider, model, promptVersion] = row.split("|");
  return {
    version: Number(version),
    approvalStatus,
    provider,
    model,
    promptVersion,
  };
}

export function draftCountForCompany(companyId: string): number {
  return Number(
    queryE2e(`
      SELECT COUNT(*) FROM email_drafts d
      JOIN outreaches o ON o.id = d.outreach_id
      JOIN opportunities op ON op.id = o.opportunity_id
      WHERE op.company_id = '${companyId}'
    `),
  );
}

export function latestAssessmentForCompany(companyId: string): {
  score: number;
  completeness: number;
  decision: string;
} | null {
  const row = queryE2e(`
    SELECT a.new_score, a.data_completeness, a.qualification_decision
    FROM opportunity_assessments a
    JOIN opportunities o ON o.id = a.opportunity_id
    WHERE o.company_id = '${companyId}'
    ORDER BY a.position DESC LIMIT 1
  `);
  if (!row) return null;
  const [score, completeness, decision] = row.split("|");
  return { score: Number(score), completeness: Number(completeness), decision };
}

export function signalCountForCompany(companyId: string): number {
  return Number(
    queryE2e(`SELECT COUNT(*) FROM company_signals WHERE company_id = '${companyId}'`),
  );
}

/**
 * Explicit per-company cleanup. The whole E2E database is dropped at teardown,
 * so this is defense in depth for anyone pointing the suite at a database they
 * intend to keep. FK delete rules force this order: outreaches RESTRICT against
 * both opportunities and contacts, so they go first; drafts and assessments
 * cascade; contacts/signals/sources/aliases cascade from the company.
 */
export function deleteCompany(companyId: string): void {
  queryE2e(`
    DELETE FROM outreaches WHERE opportunity_id IN
      (SELECT id FROM opportunities WHERE company_id = '${companyId}');
    DELETE FROM opportunities WHERE company_id = '${companyId}';
    DELETE FROM companies WHERE id = '${companyId}';
  `);
}
