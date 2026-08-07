"use client";

import { useMemo, useState } from "react";

import { useI18n } from "@/lib/i18n";

export interface MappingFieldDefinition {
  key: string;
  labelZh: string;
  labelEn: string;
  required?: boolean;
}

export interface MappingGroupDefinition {
  labelZh: string;
  labelEn: string;
  fields: MappingFieldDefinition[];
}

interface StructuredMappingEditorProps {
  groups: MappingGroupDefinition[];
  mapping: Record<string, string>;
  sourceColumns: string[];
  confidence: Record<string, string>;
  source?: Record<string, string>;
  samples: Record<string, string>;
  duplicateColumns?: string[];
  confirmed: boolean;
  validated: boolean;
  disabled?: boolean;
  onChange: (mapping: Record<string, string>) => void;
}

export function StructuredMappingEditor({
  groups,
  mapping,
  sourceColumns,
  confidence,
  source = {},
  samples,
  duplicateColumns = [],
  confirmed,
  validated,
  disabled = false,
  onChange,
}: StructuredMappingEditorProps) {
  const { lang } = useI18n();
  const [jsonDraft, setJsonDraft] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const jsonText = jsonDraft ?? JSON.stringify(mapping, null, 2);

  const selectedCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const column of Object.values(mapping)) {
      counts.set(column, (counts.get(column) ?? 0) + 1);
    }
    return counts;
  }, [mapping]);

  function updateField(field: string, column: string) {
    const next = { ...mapping };
    if (column) next[field] = column;
    else delete next[field];
    setJsonDraft(null);
    setJsonError(null);
    onChange(next);
  }

  function applyJson() {
    let decoded: unknown;
    try {
      decoded = JSON.parse(jsonText);
    } catch {
      setJsonError(
        lang === "zh" ? "JSON 格式无效，当前 Mapping 未被覆盖。" : "Invalid JSON. The current mapping was preserved.",
      );
      return;
    }
    if (
      typeof decoded !== "object" ||
      decoded === null ||
      Array.isArray(decoded) ||
      !Object.entries(decoded).every(
        ([key, value]) => key.trim() && typeof value === "string" && value.trim(),
      )
    ) {
      setJsonError(
        lang === "zh"
          ? "Mapping 必须是“逻辑字段 → 文件列”的非空字符串对象，当前 Mapping 未被覆盖。"
          : "Mapping must contain non-empty logical-field to source-column strings. The current mapping was preserved.",
      );
      return;
    }
    setJsonError(null);
    setJsonDraft(null);
    onChange(decoded as Record<string, string>);
  }

  return (
    <div className="space-y-4" data-testid="structured-mapping-editor">
      {!validated ? (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          {lang === "zh"
            ? "Mapping 已变更，必须重新运行 Preflight 后才能确认或写入。"
            : "Mapping changed. Run preflight again before confirmation or persistence."}
        </p>
      ) : null}
      {groups.map((group) => (
        <section className="overflow-hidden rounded-xl border border-slate-200" key={group.labelEn}>
          <h4 className="bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700">
            {lang === "zh" ? group.labelZh : group.labelEn}
          </h4>
          <div className="overflow-x-auto">
            <table className="min-w-[880px] divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-white text-slate-500">
                <tr>
                  <th className="px-3 py-2">{lang === "zh" ? "逻辑字段" : "Logical field"}</th>
                  <th className="px-3 py-2">{lang === "zh" ? "文件列" : "Source column"}</th>
                  <th className="px-3 py-2">{lang === "zh" ? "要求" : "Requirement"}</th>
                  <th className="px-3 py-2">{lang === "zh" ? "置信度" : "Confidence"}</th>
                  <th className="px-3 py-2">{lang === "zh" ? "来源" : "Source"}</th>
                  <th className="px-3 py-2">{lang === "zh" ? "脱敏样例" : "Masked sample"}</th>
                  <th className="px-3 py-2">{lang === "zh" ? "状态" : "Status"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {group.fields.map((field) => {
                  const selected = mapping[field.key] ?? "";
                  const conflict = Boolean(
                    selected &&
                      ((selectedCounts.get(selected) ?? 0) > 1 ||
                        duplicateColumns.includes(selected)),
                  );
                  const status = !selected
                    ? "missing"
                    : conflict
                      ? "conflict"
                      : confirmed || confidence[field.key] === "high" || confidence[field.key] === "manual"
                        ? "matched"
                        : "pending";
                  return (
                    <tr key={field.key}>
                      <td className="px-3 py-2.5">
                        <p className="font-semibold text-slate-800">
                          {lang === "zh" ? field.labelZh : field.labelEn}
                        </p>
                        <p className="font-mono text-[10px] text-slate-400">{field.key}</p>
                      </td>
                      <td className="px-3 py-2.5">
                        <select
                          className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs"
                          data-testid={`mapping-select-${field.key}`}
                          disabled={disabled}
                          onChange={(event) => updateField(field.key, event.target.value)}
                          value={selected}
                        >
                          <option value="">{lang === "zh" ? "忽略此字段" : "Ignore field"}</option>
                          {sourceColumns.map((column) => (
                            <option key={column} value={column}>{column}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2.5 text-slate-600">
                        {field.required
                          ? (lang === "zh" ? "必填" : "Required")
                          : (lang === "zh" ? "可选" : "Optional")}
                      </td>
                      <td className="px-3 py-2.5 text-slate-600">
                        <span
                          className={
                            confidence[field.key] === "high"
                              ? "font-semibold text-emerald-700"
                              : "font-medium text-amber-700"
                          }
                        >
                          {(confidence[field.key] ?? "low").toUpperCase()}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
                          {source[field.key] === "manual"
                            ? lang === "zh"
                              ? "手动"
                              : "MANUAL"
                            : source[field.key] === "inferred"
                              ? lang === "zh"
                                ? "推断"
                                : "INFERRED"
                              : lang === "zh"
                                ? "自动"
                                : "AUTO"}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-slate-600">
                        {samples[field.key] ?? "—"}
                      </td>
                      <td className="px-3 py-2.5">
                        <MappingStatus status={status} lang={lang} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <details className="rounded-xl border border-slate-200 bg-slate-50">
        <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-slate-700">
          {lang === "zh" ? "高级 JSON 编辑" : "Advanced JSON editor"}
        </summary>
        <div className="border-t border-slate-200 p-3">
          <textarea
            className="min-h-40 w-full rounded-lg border border-slate-300 bg-white p-3 font-mono text-xs"
            data-testid="mapping-json-editor"
            disabled={disabled}
            onChange={(event) => setJsonDraft(event.target.value)}
            value={jsonText}
          />
          {jsonError ? <p className="mt-2 text-xs text-rose-700">{jsonError}</p> : null}
          <button
            className="mt-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
            data-testid="mapping-json-apply"
            disabled={disabled}
            onClick={applyJson}
            type="button"
          >
            {lang === "zh" ? "应用并重新校验" : "Apply and revalidate"}
          </button>
        </div>
      </details>
    </div>
  );
}

function MappingStatus({
  status,
  lang,
}: {
  status: "matched" | "pending" | "missing" | "conflict";
  lang: "zh" | "en";
}) {
  const labels = {
    matched: lang === "zh" ? "已匹配" : "Matched",
    pending: lang === "zh" ? "待确认" : "Pending",
    missing: lang === "zh" ? "缺失" : "Missing",
    conflict: lang === "zh" ? "冲突" : "Conflict",
  };
  const styles = {
    matched: "bg-emerald-100 text-emerald-800",
    pending: "bg-amber-100 text-amber-800",
    missing: "bg-slate-100 text-slate-700",
    conflict: "bg-rose-100 text-rose-800",
  };
  return <span className={`rounded-full px-2 py-1 font-semibold ${styles[status]}`}>{labels[status]}</span>;
}
