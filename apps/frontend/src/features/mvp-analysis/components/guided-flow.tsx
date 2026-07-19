"use client";

import { LoaderCircle, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import type { MissingFields, ProspectContact, ProspectSender } from "../prospect-state";

const inputClass =
  "h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 " +
  "shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-600 " +
  "focus:ring-3 focus:ring-teal-600/10 disabled:bg-slate-100";
const labelClass = "mb-1.5 block text-xs font-semibold tracking-wide text-slate-700";

interface MissingFieldsPromptProps {
  /** Clears the browser-stored sender profile. */
  onClearSenderProfile?: () => void;
  /** Which blocks to render — snapshotted when the flow stopped. */
  missing: MissingFields;
  /** What is still incomplete right now, which gates the Continue button. */
  stillMissing: MissingFields;
  contact: ProspectContact;
  sender: ProspectSender;
  busy: boolean;
  onContactChange: (patch: Partial<ProspectContact>) => void;
  onSenderChange: (patch: Partial<ProspectSender>) => void;
  onContinue: () => void;
}

/**
 * Asks for exactly what is missing.
 *
 * The old flow sent the user back into a five-section form to supply two
 * fields. Expanding only the blocked group is the difference between
 * "finish this" and "start over".
 */
export function MissingFieldsPrompt({
  onClearSenderProfile,
  missing,
  stillMissing,
  contact,
  sender,
  busy,
  onContactChange,
  onSenderChange,
  onContinue,
}: MissingFieldsPromptProps) {
  const { t } = useI18n();
  const ready = !stillMissing.contact && !stillMissing.sender;

  return (
    <section
      className="rounded-2xl border border-amber-200 bg-amber-50/60 px-4 py-4"
      data-testid="guided-missing"
    >
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
        <TriangleAlert className="size-4" />
        {t("guided.missing.title")}
      </p>
      <p className="mt-1 text-xs leading-5 text-amber-900/80">{t("guided.missing.note")}</p>

      {missing.contact ? (
        <div className="mt-4" data-testid="guided-missing-contact">
          <p className="text-xs font-semibold text-slate-700">
            {t("guided.missing.contact")}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">{t("guided.missing.contactHint")}</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <label>
              <span className={labelClass}>{t("guided.contact.name")}</span>
              <input
                className={inputClass}
                data-testid="guided-contact-name"
                disabled={busy}
                onChange={(event) => onContactChange({ name: event.target.value })}
                value={contact.name}
              />
            </label>
            <label>
              <span className={labelClass}>{t("guided.contact.title")}</span>
              <input
                className={inputClass}
                disabled={busy}
                onChange={(event) => onContactChange({ title: event.target.value })}
                value={contact.title}
              />
            </label>
            <label>
              <span className={labelClass}>{t("guided.contact.email")}</span>
              <input
                className={inputClass}
                data-testid="guided-contact-email"
                disabled={busy}
                onChange={(event) => onContactChange({ email: event.target.value })}
                value={contact.email}
              />
            </label>
            <label>
              <span className={labelClass}>{t("guided.contact.source")}</span>
              <input
                className={inputClass}
                data-testid="guided-contact-source"
                disabled={busy}
                onChange={(event) => onContactChange({ source: event.target.value })}
                value={contact.source}
              />
            </label>
          </div>
        </div>
      ) : null}

      {missing.sender ? (
        <div className="mt-4" data-testid="guided-missing-sender">
          <p className="text-xs font-semibold text-slate-700">{t("guided.missing.sender")}</p>
          <p className="mt-0.5 text-xs text-slate-500">{t("guided.missing.senderHint")}</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <label>
              <span className={labelClass}>{t("guided.sender.name")}</span>
              <input
                className={inputClass}
                data-testid="guided-sender-name"
                disabled={busy}
                onChange={(event) => onSenderChange({ name: event.target.value })}
                value={sender.name}
              />
            </label>
            <label>
              <span className={labelClass}>{t("guided.sender.company")}</span>
              <input
                className={inputClass}
                data-testid="guided-sender-company"
                disabled={busy}
                onChange={(event) => onSenderChange({ company: event.target.value })}
                value={sender.company}
              />
            </label>
            <label className="sm:col-span-2">
              <span className={labelClass}>{t("guided.sender.value")}</span>
              <input
                className={inputClass}
                data-testid="guided-sender-value"
                disabled={busy}
                onChange={(event) =>
                  onSenderChange({ valueProposition: event.target.value })
                }
                value={sender.valueProposition}
              />
            </label>
          </div>
        </div>
      ) : null}

      {missing.sender ? null : (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span data-testid="sender-saved-note">{t("sender.saved")}</span>
          {onClearSenderProfile ? (
            <button
              className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
              data-testid="sender-clear"
              onClick={onClearSenderProfile}
              type="button"
            >
              {t("sender.clear")}
            </button>
          ) : null}
        </p>
      )}

      <Button
        className="mt-4 h-10 bg-teal-700 text-white hover:bg-teal-800"
        data-testid="guided-continue"
        disabled={busy || !ready}
        onClick={onContinue}
        type="button"
      >
        {busy ? <LoaderCircle className="animate-spin" /> : null}
        {busy ? t("guided.analyzing") : t("guided.continue")}
      </Button>
    </section>
  );
}
