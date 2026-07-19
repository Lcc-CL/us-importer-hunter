import { useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  Building2,
  Database,
  LoaderCircle,
  Plus,
  Send,
  SlidersHorizontal,
  Trash2,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ProspectAnalysisRequest } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  isCanonicalSignalKind,
  LEGACY_SIGNAL_KINDS,
  SIGNAL_KINDS,
} from "../signal-kinds";

interface EditableSource {
  id: number;
  source: string;
  reference: string;
}

interface EditableSignal {
  id: number;
  kind: string;
  detail: string;
}

interface EditableContact {
  name: string;
  title: string;
  email: string;
  linkedin_url: string;
  phone: string;
  source: string;
}

interface ProspectFormProps {
  disabled: boolean;
  onSubmit: (request: ProspectAnalysisRequest) => Promise<void>;
}

const inputClass =
  "h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-600 focus:ring-3 focus:ring-teal-600/10 disabled:bg-slate-100";
const labelClass = "mb-1.5 block text-xs font-semibold tracking-wide text-slate-700";

function FormSection({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="border-b border-slate-200 px-5 py-6 last:border-b-0 sm:px-7">
      <div className="mb-5 flex items-start gap-3">
        <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
          {icon}
        </div>
        <div>
          <h2 className="font-semibold text-slate-950">{title}</h2>
          <p className="mt-0.5 text-xs leading-5 text-slate-500">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export function ProspectForm({ disabled, onSubmit }: ProspectFormProps) {
  const { t, label } = useI18n();
  const nextSourceId = useRef(3);
  const nextSignalId = useRef(1);
  const [companyName, setCompanyName] = useState("");
  const [website, setWebsite] = useState("");
  const [sources, setSources] = useState<EditableSource[]>([
    { id: 1, source: "", reference: "" },
    { id: 2, source: "", reference: "" },
  ]);
  const [signals, setSignals] = useState<EditableSignal[]>([]);
  const [includeContact, setIncludeContact] = useState(true);
  const [contact, setContact] = useState<EditableContact>({
    name: "",
    title: "",
    email: "",
    linkedin_url: "",
    phone: "",
    source: "",
  });
  const [sender, setSender] = useState({
    name: "",
    company: "",
    valueProposition: "",
  });
  const [generateEmail, setGenerateEmail] = useState(true);

  function updateSource(
    id: number,
    field: "source" | "reference",
    value: string,
  ) {
    setSources((current) =>
      current.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
    );
  }

  function addSource() {
    const id = nextSourceId.current++;
    setSources((current) => [...current, { id, source: "", reference: "" }]);
  }

  function removeSource(id: number) {
    setSources((current) =>
      current.length === 1 ? current : current.filter((item) => item.id !== id),
    );
  }

  function updateSignal(
    id: number,
    field: "kind" | "detail",
    value: string,
  ) {
    setSignals((current) =>
      current.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
    );
  }

  function addSignal() {
    const id = nextSignalId.current++;
    setSignals((current) => [...current, { id, kind: "", detail: "" }]);
  }

  function removeSignal(id: number) {
    setSignals((current) => current.filter((item) => item.id !== id));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const request: ProspectAnalysisRequest = {
      company: {
        name: companyName.trim(),
        website: website.trim() || null,
        sources: sources.map((item) => ({
          source: item.source.trim(),
          reference: item.reference.trim(),
        })),
        signals: signals.map((item) => ({
          kind: item.kind.trim(),
          detail: item.detail.trim(),
        })),
      },
      contact: includeContact
        ? {
            name: contact.name.trim(),
            title: contact.title.trim() || null,
            email: contact.email.trim() || null,
            linkedin_url: contact.linkedin_url.trim() || null,
            phone: contact.phone.trim() || null,
            source: contact.source.trim(),
          }
        : null,
      sender: {
        name: sender.name.trim(),
        company: sender.company.trim(),
        value_proposition: sender.valueProposition.trim(),
      },
      options: { generate_email: generateEmail },
    };
    await onSubmit(request);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_24px_70px_-35px_rgba(15,23,42,0.35)]"
    >
      <div className="border-b border-slate-200 bg-slate-950 px-5 py-5 text-white sm:px-7">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-300">
          {t("form.kicker")}
        </p>
        <h1 className="mt-1.5 text-xl font-semibold tracking-tight">
          {t("form.title")}
        </h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">
          {t("form.intro")}
        </p>
      </div>

      <fieldset disabled={disabled}>
        <FormSection
          icon={<Building2 className="size-4" />}
          title={t("form.company.title")}
          description={t("form.company.desc")}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label>
              <span className={labelClass}>{t("form.company.name")}</span>
              <input
                aria-label="Company name"
                className={inputClass}
                value={companyName}
                onChange={(event) => setCompanyName(event.target.value)}
                placeholder="Pacific Home Goods Inc."
                required
              />
            </label>
            <label>
              <span className={labelClass}>{t("form.company.website")}</span>
              <input
                aria-label="Company website"
                className={inputClass}
                value={website}
                onChange={(event) => setWebsite(event.target.value)}
                placeholder="https://company.example"
                type="url"
              />
            </label>
          </div>
        </FormSection>

        <FormSection
          icon={<Database className="size-4" />}
          title={t("form.sources.title")}
          description={t("form.sources.desc")}
        >
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">
            {t("form.sources.tip")}
          </div>
          <div className="space-y-3">
            {sources.map((item, index) => (
              <div
                className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-3 sm:grid-cols-[0.75fr_1.25fr_auto]"
                key={item.id}
              >
                <label>
                  <span className={labelClass}>
                    {t("form.sources.name", { n: index + 1 })}
                  </span>
                  <input
                    aria-label={`Source ${index + 1} name`}
                    className={inputClass}
                    value={item.source}
                    onChange={(event) =>
                      updateSource(item.id, "source", event.target.value)
                    }
                    placeholder="importyeti"
                    required
                  />
                </label>
                <label>
                  <span className={labelClass}>{t("form.sources.reference")}</span>
                  <input
                    aria-label={`Source ${index + 1} reference`}
                    className={inputClass}
                    value={item.reference}
                    onChange={(event) =>
                      updateSource(item.id, "reference", event.target.value)
                    }
                    placeholder="https://source.example/company/..."
                    required
                  />
                </label>
                <Button
                  aria-label={t("form.sources.remove", { n: index + 1 })}
                  className="self-end"
                  disabled={sources.length === 1}
                  onClick={() => removeSource(item.id)}
                  size="icon-lg"
                  type="button"
                  variant="ghost"
                >
                  <Trash2 />
                </Button>
              </div>
            ))}
          </div>
          <Button className="mt-3" onClick={addSource} type="button" variant="outline">
            <Plus /> {t("form.sources.add")}
          </Button>
        </FormSection>

        <FormSection
          icon={<SlidersHorizontal className="size-4" />}
          title={t("form.signals.title")}
          description={t("form.signals.desc")}
        >
          {signals.length === 0 ? (
            <p className="text-sm text-slate-500">{t("form.signals.empty")}</p>
          ) : (
            <div className="space-y-3">
              {signals.map((item, index) => (
                <div
                  className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-3 sm:grid-cols-[0.75fr_1.25fr_auto]"
                  key={item.id}
                >
                  <label>
                    <span className={labelClass}>
                      {t("form.signals.kind", { n: index + 1 })}
                    </span>
                    <select
                      aria-label={`Signal ${index + 1} kind`}
                      className={inputClass}
                      value={item.kind}
                      onChange={(event) =>
                        updateSignal(item.id, "kind", event.target.value)
                      }
                      required
                    >
                      <option value="" disabled>
                        {t("form.signals.kindPlaceholder")}
                      </option>
                      {SIGNAL_KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {label("signalKind", kind)}
                        </option>
                      ))}
                      {item.kind && !isCanonicalSignalKind(item.kind) ? (
                        <option value={item.kind}>
                          {item.kind in LEGACY_SIGNAL_KINDS
                            ? `${label(
                                "signalKind",
                                LEGACY_SIGNAL_KINDS[item.kind],
                              )}（${t("form.signals.kindLegacy")}: ${item.kind}）`
                            : `${t("form.signals.kindUnknown")}（${item.kind}）`}
                        </option>
                      ) : null}
                    </select>
                  </label>
                  <label>
                    <span className={labelClass}>{t("form.signals.detail")}</span>
                    <input
                      aria-label={`Signal ${index + 1} detail`}
                      className={inputClass}
                      value={item.detail}
                      onChange={(event) =>
                        updateSignal(item.id, "detail", event.target.value)
                      }
                      placeholder="Customs shipments recorded"
                      required
                    />
                  </label>
                  <Button
                    aria-label={t("form.signals.remove", { n: index + 1 })}
                    className="self-end"
                    onClick={() => removeSignal(item.id)}
                    size="icon-lg"
                    type="button"
                    variant="ghost"
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
            </div>
          )}
          <Button className="mt-3" onClick={addSignal} type="button" variant="outline">
            <Plus /> {t("form.signals.add")}
          </Button>
        </FormSection>

        <FormSection
          icon={<UserRound className="size-4" />}
          title={t("form.contact.title")}
          description={t("form.contact.desc")}
        >
          <label className="mb-4 flex items-center gap-3 text-sm font-medium text-slate-800">
            <input
              checked={includeContact}
              className="size-4 accent-teal-700"
              onChange={(event) => setIncludeContact(event.target.checked)}
              type="checkbox"
            />
            {t("form.contact.include")}
          </label>
          {includeContact ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className={labelClass}>{t("form.contact.name")}</span>
                <input
                  aria-label="Contact name"
                  className={inputClass}
                  value={contact.name}
                  onChange={(event) =>
                    setContact((current) => ({ ...current, name: event.target.value }))
                  }
                  placeholder="Maria Chen"
                  required
                />
              </label>
              <label>
                <span className={labelClass}>{t("form.contact.jobTitle")}</span>
                <input
                  aria-label="Contact title"
                  className={inputClass}
                  value={contact.title}
                  onChange={(event) =>
                    setContact((current) => ({ ...current, title: event.target.value }))
                  }
                  placeholder="Director of Supply Chain"
                />
              </label>
              <label>
                <span className={labelClass}>{t("form.contact.email")}</span>
                <input
                  aria-label="Contact email"
                  className={inputClass}
                  value={contact.email}
                  onChange={(event) =>
                    setContact((current) => ({ ...current, email: event.target.value }))
                  }
                  placeholder="maria@company.example"
                  type="email"
                />
              </label>
              <label>
                <span className={labelClass}>{t("form.contact.linkedin")}</span>
                <input
                  aria-label="Contact LinkedIn URL"
                  className={inputClass}
                  value={contact.linkedin_url}
                  onChange={(event) =>
                    setContact((current) => ({
                      ...current,
                      linkedin_url: event.target.value,
                    }))
                  }
                  placeholder="https://linkedin.com/in/..."
                  type="url"
                />
              </label>
              <label>
                <span className={labelClass}>{t("form.contact.phone")}</span>
                <input
                  aria-label="Contact phone"
                  className={inputClass}
                  value={contact.phone}
                  onChange={(event) =>
                    setContact((current) => ({ ...current, phone: event.target.value }))
                  }
                  placeholder="+1 415 555 0100"
                  type="tel"
                />
              </label>
              <label>
                <span className={labelClass}>{t("form.contact.source")}</span>
                <input
                  aria-label="Contact source"
                  className={inputClass}
                  value={contact.source}
                  onChange={(event) =>
                    setContact((current) => ({ ...current, source: event.target.value }))
                  }
                  placeholder="company_website"
                  required
                />
              </label>
            </div>
          ) : null}
        </FormSection>

        <FormSection
          icon={<Send className="size-4" />}
          title={t("form.sender.title")}
          description={t("form.sender.desc")}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label>
              <span className={labelClass}>{t("form.sender.name")}</span>
              <input
                aria-label="Sender name"
                className={inputClass}
                value={sender.name}
                onChange={(event) =>
                  setSender((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="Alex Morgan"
                required
              />
            </label>
            <label>
              <span className={labelClass}>{t("form.sender.company")}</span>
              <input
                aria-label="Sender company"
                className={inputClass}
                value={sender.company}
                onChange={(event) =>
                  setSender((current) => ({ ...current, company: event.target.value }))
                }
                placeholder="Harbor Bridge Logistics"
                required
              />
            </label>
            <label className="sm:col-span-2">
              <span className={labelClass}>{t("form.sender.valueProp")}</span>
              <textarea
                aria-label="Value proposition"
                className={`${inputClass} min-h-24 resize-y py-2.5`}
                value={sender.valueProposition}
                onChange={(event) =>
                  setSender((current) => ({
                    ...current,
                    valueProposition: event.target.value,
                  }))
                }
                placeholder="We simplify Asia-to-US inbound freight."
                required
              />
            </label>
          </div>
          <label className="mt-5 flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-800">
            <input
              checked={generateEmail}
              className="size-4 accent-teal-700"
              onChange={(event) => setGenerateEmail(event.target.checked)}
              type="checkbox"
            />
            {t("form.generateEmail")}
          </label>
        </FormSection>
      </fieldset>

      <div className="bg-slate-50 px-5 py-5 sm:px-7">
        <Button
          className="h-11 w-full bg-teal-700 text-white hover:bg-teal-800"
          disabled={disabled}
          size="lg"
          type="submit"
        >
          {disabled ? <LoaderCircle className="animate-spin" /> : null}
          {disabled ? t("form.submitting") : t("form.submit")}
        </Button>
      </div>
    </form>
  );
}
