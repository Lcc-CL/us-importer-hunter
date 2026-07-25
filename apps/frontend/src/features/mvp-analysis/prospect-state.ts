/**
 * The single source of truth for the contact and the sender.
 *
 * These used to live twice: once inside ProspectForm's own useState and once
 * inside the guided flow's. Two independent state trees meant filling a
 * contact in one view left the other still believing it was missing, and the
 * analysis read whichever copy happened to be wired to it. The guided flow and
 * the advanced editor are two *views*; the data lives here.
 *
 * `linkedin_url` rather than `linkedin`: this shape maps straight onto the
 * analyze contract, so no view has to translate field names on the way out.
 */

import type { ProspectAnalysisRequest } from "@/lib/api";
import type { ApplicationPayload } from "@/lib/research-api";

export interface ProspectContact {
  name: string;
  title: string;
  email: string;
  linkedin_url: string;
  phone: string;
  source: string;
}

export interface ProspectSender {
  name: string;
  company: string;
  valueProposition: string;
}

export const EMPTY_CONTACT: ProspectContact = {
  name: "",
  title: "",
  email: "",
  linkedin_url: "",
  phone: "",
  source: "",
};

export const EMPTY_SENDER: ProspectSender = {
  name: "",
  company: "",
  valueProposition: "",
};

/** What the guided flow still needs before qualification can run. */
export interface MissingFields {
  contact: boolean;
  sender: boolean;
}

/**
 * A contact is usable when it has a name, a source, and at least one way to
 * reach the person — the same rule the backend applies when it builds the
 * source reference, checked here so the user hears about it before a request
 * is spent.
 */
export function contactIsComplete(contact: ProspectContact): boolean {
  const reachable = [contact.email, contact.linkedin_url, contact.phone].some((value) =>
    value.trim(),
  );
  return Boolean(contact.name.trim()) && reachable && Boolean(contact.source.trim());
}

export function senderIsComplete(sender: ProspectSender): boolean {
  return [sender.name, sender.company, sender.valueProposition].every((value) =>
    value.trim(),
  );
}

export function missingFieldsFor(
  contact: ProspectContact,
  sender: ProspectSender,
): MissingFields {
  return { contact: !contactIsComplete(contact), sender: !senderIsComplete(sender) };
}

/** Research payload + the shared contact/sender → the existing analyze contract. */
export function buildAnalysisRequest(
  payload: ApplicationPayload,
  contact: ProspectContact,
  sender: ProspectSender,
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
    // COMPANY_ONLY mode: an incomplete contact is sent as null, never as a
    // half-filled record. The backend saves the analysis as PARTIAL and the
    // draft simply waits for a contact — analysis is not blocked.
    contact: contactIsComplete(contact)
      ? {
          name: contact.name.trim(),
          source: contact.source.trim(),
          title: contact.title.trim() || null,
          email: contact.email.trim() || null,
          linkedin_url: contact.linkedin_url.trim() || null,
          phone: contact.phone.trim() || null,
        }
      : null,
    sender: {
      name: sender.name.trim(),
      company: sender.company.trim(),
      value_proposition: sender.valueProposition.trim(),
    },
    options: { generate_email: true },
  };
}
