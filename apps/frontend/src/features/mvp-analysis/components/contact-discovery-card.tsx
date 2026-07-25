"use client";

import { CheckCircle2, LoaderCircle, Mail, SearchX, UserRound } from "lucide-react";

import { useI18n } from "@/lib/i18n";
import type { ContactDiscovery, RankedContact } from "@/lib/research-api";

interface ContactDiscoveryCardProps {
  discovery: ContactDiscovery | null;
  /** null while the discovery request is in flight. */
  loading: boolean;
  /** email of the ranked contact currently applied to the analysis. */
  selectedEmail: string;
  onSelect: (ranked: RankedContact) => void;
  onManualEdit: () => void;
}

function ContactLine({
  ranked,
  active,
  onSelect,
  switchLabel,
}: {
  ranked: RankedContact;
  active: boolean;
  onSelect: () => void;
  switchLabel: string;
}) {
  const { contact } = ranked;
  return (
    <li
      className={`rounded-xl border px-3 py-2 text-sm ${
        active ? "border-teal-600 bg-teal-50/60" : "border-slate-200 bg-white"
      }`}
      data-testid="discovered-contact"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium text-slate-900">
            {contact.name || contact.email || contact.phone}
            {contact.title ? (
              <span className="ml-2 text-xs font-normal text-slate-500">{contact.title}</span>
            ) : null}
          </p>
          {contact.email ? (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-600">
              <Mail className="size-3" /> {contact.email}
            </p>
          ) : null}
          <a
            className="mt-0.5 block truncate text-xs text-teal-700 underline-offset-2 hover:underline"
            href={contact.source_url}
            rel="noreferrer"
            target="_blank"
          >
            {contact.source_url}
          </a>
        </div>
        {active ? (
          <CheckCircle2 className="size-4 shrink-0 text-teal-700" />
        ) : (
          <button
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
            onClick={onSelect}
            type="button"
          >
            {switchLabel}
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * What discovery found, in one of three honest states: a named person, only
 * department mailboxes, or nothing. "Nothing" never blocks the analysis — it
 * just says so and offers the manual path.
 */
export function ContactDiscoveryCard({
  discovery,
  loading,
  selectedEmail,
  onSelect,
  onManualEdit,
}: ContactDiscoveryCardProps) {
  const { t } = useI18n();

  if (loading) {
    return (
      <section
        className="mb-6 flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-4 text-sm text-slate-600"
        data-testid="contact-discovery-loading"
      >
        <LoaderCircle className="size-4 animate-spin" /> {t("discovery.loading")}
      </section>
    );
  }
  if (!discovery) return null;

  const found = [
    ...(discovery.primary ? [discovery.primary] : []),
    ...discovery.alternatives,
  ];

  if (discovery.discovery_status === "COMPANY_ONLY") {
    return (
      <section
        className="mb-6 rounded-2xl border border-slate-200 bg-white px-4 py-4"
        data-testid="contact-discovery-none"
      >
        <p className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <SearchX className="size-4 text-slate-400" /> {t("discovery.none.title")}
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-500">{t("discovery.none.note")}</p>
        <button
          className="mt-3 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
          data-testid="discovery-manual-edit"
          onClick={onManualEdit}
          type="button"
        >
          {t("discovery.manualEdit")}
        </button>
      </section>
    );
  }

  const isDepartment = discovery.discovery_status === "DEPARTMENT_CONTACT";
  return (
    <section
      className="mb-6 rounded-2xl border border-slate-200 bg-white px-4 py-4"
      data-testid={isDepartment ? "contact-discovery-partial" : "contact-discovery-found"}
    >
      <p className="flex items-center gap-2 text-sm font-semibold text-slate-800">
        <UserRound className="size-4 text-teal-700" />
        {isDepartment
          ? t("discovery.partial.title")
          : t("discovery.found.title").replace("{count}", String(found.length))}
      </p>
      <p className="mt-1 text-xs leading-5 text-slate-500">
        {isDepartment ? t("discovery.partial.note") : t("discovery.found.note")}
      </p>
      <ul className="mt-3 space-y-2">
        {found.map((ranked) => (
          <ContactLine
            active={
              Boolean(ranked.contact.email) && ranked.contact.email === selectedEmail
            }
            key={`${ranked.contact.email}|${ranked.contact.name}|${ranked.contact.source_url}`}
            onSelect={() => onSelect(ranked)}
            ranked={ranked}
            switchLabel={t("discovery.switch")}
          />
        ))}
      </ul>
      {discovery.selection_reasons.length ? (
        <p className="mt-2 text-xs text-slate-400">
          {t("discovery.reasons")}: {discovery.selection_reasons.join(" · ")}
        </p>
      ) : null}
      <button
        className="mt-3 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
        data-testid="discovery-manual-edit"
        onClick={onManualEdit}
        type="button"
      >
        {t("discovery.manualEdit")}
      </button>
    </section>
  );
}
