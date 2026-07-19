"use client";

import { useState } from "react";
import { LoaderCircle, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import type { ProspectAnalysisRequest } from "@/lib/api";
import type { ApplicationPayload } from "@/lib/research-api";

/** What the guided flow still needs before it can run qualification. */
export interface MissingFields {
  contact: boolean;
  sender: boolean;
}

export interface GuidedContact {
  name: string;
  title: string;
  email: string;
  linkedin: string;
  phone: string;
  source: string;
}

export interface GuidedSender {
  name: string;
  company: string;
  valueProposition: string;
}

export const EMPTY_CONTACT: GuidedContact = {
  name: "",
  title: "",
  email: "",
  linkedin: "",
  phone: "",
  source: "company_website",
};

export const EMPTY_SENDER: GuidedSender = { name: "", company: "", valueProposition: "" };

/**
 * A contact is usable when it has a name and at least one way to reach the
 * person — the same rule the backend enforces when it builds the source
 * reference, checked here so the user is told before a request is spent.
 */
export function contactIsComplete(contact: GuidedContact): boolean {
  const reachable = [contact.email, contact.linkedin, contact.phone].some((value) =>
    value.trim(),
  );
  return Boolean(contact.name.trim()) && reachable && Boolean(contact.source.trim());
}

export function senderIsComplete(sender: GuidedSender): boolean {
  return [sender.name, sender.company, sender.valueProposition].every((value) =>
    value.trim(),
  );
}

export function missingFieldsFor(
  contact: GuidedContact,
  sender: GuidedSender,
): MissingFields {
  return { contact: !contactIsComplete(contact), sender: !senderIsComplete(sender) };
}

/** Research payload + collected fields → the existing analyze contract. */
export function buildAnalysisRequest(
  payload: ApplicationPayload,
  contact: GuidedContact,
  sender: GuidedSender,
): ProspectAnalysisRequest {
  return {
    company: {
      name: payload.company_name,
      website: payload.website || null,
      sources: payload.sources.map((source) => ({
        source: source.source,
        reference: source.reference,
      })),
      signals: payload.signals.map((signal) => ({
        kind: signal.kind,
        detail: signal.detail,
      })),
    },
    contact: {
      name: contact.name.trim(),
      source: contact.source.trim(),
      title: contact.title.trim() || null,
      email: contact.email.trim() || null,
      linkedin_url: contact.linkedin.trim() || null,
      phone: contact.phone.trim() || null,
    },
    sender: {
      name: sender.name.trim(),
      company: sender.company.trim(),
      value_proposition: sender.valueProposition.trim(),
    },
    options: { generate_email: true },
  };
}

const inputClass =
  "h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 " +
  "shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-600 " +
  "focus:ring-3 focus:ring-teal-600/10 disabled:bg-slate-100";
const labelClass = "mb-1.5 block text-xs font-semibold tracking-wide text-slate-700";

interface MissingFieldsPromptProps {
  /** Which blocks to render — snapshotted when the flow stopped. */
  missing: MissingFields;
  /** What is still incomplete right now, which gates the Continue button. */
  stillMissing: MissingFields;
  contact: GuidedContact;
  sender: GuidedSender;
  busy: boolean;
  onContactChange: (patch: Partial<GuidedContact>) => void;
  onSenderChange: (patch: Partial<GuidedSender>) => void;
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

/** Local state helper so the page keeps one source of truth for both blocks. */
export function useGuidedFields() {
  const [contact, setContact] = useState<GuidedContact>(EMPTY_CONTACT);
  const [sender, setSender] = useState<GuidedSender>(EMPTY_SENDER);

  return {
    contact,
    sender,
    patchContact: (patch: Partial<GuidedContact>) =>
      setContact((current) => ({ ...current, ...patch })),
    patchSender: (patch: Partial<GuidedSender>) =>
      setSender((current) => ({ ...current, ...patch })),
    /**
     * The sender is who you are and carries across companies; the contact
     * belongs to one company and must not. Reusing the previous prospect's
     * contact would silently address the wrong person.
     */
    resetContact: () => setContact(EMPTY_CONTACT),
  };
}
