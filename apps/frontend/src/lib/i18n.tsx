"use client";

/**
 * Lightweight i18n: one dictionary, React context, no route duplication.
 * Default language is Simplified Chinese; the choice persists in localStorage.
 * Database/API enum values stay English — `label()` translates them at the
 * display layer only.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

export type Lang = "zh" | "en";

const STORAGE_KEY = "uih.lang";

const zh = {
  "app.tagline": "从证据到触达 · MVP",
  "header.apiDocs": "API 文档",
  "header.langSwitch": "English",
  "hero.kicker": "潜在客户分析工作台",
  "hero.title": "将经过验证的进口商证据，转化为人工审核的首封开发信草稿。",

  "provider.checking": "正在检测运行配置…",
  "provider.unavailable": "无法获取后端运行状态",
  "provider.demo": "演示模式",
  "provider.live": "真实 AI",
  "provider.model": "模型",

  "draftMode.notice": "草稿模式：当前版本只生成和审批邮件草稿，不会自动发送。",

  "form.kicker": "潜客录入",
  "form.title": "分析一家美国进口商",
  "form.intro":
    "提交有证据支撑的公司事实。工作流会评估匹配度、选择决策人，并生成仅供人工审核的邮件草稿。",
  "form.company.title": "公司",
  "form.company.desc": "你要评估资格的进口商。网站选填。",
  "form.company.name": "公司名称 *",
  "form.company.website": "网站",
  "form.sources.title": "证据来源",
  "form.sources.desc": "只填写你实际查阅过的参考来源；系统不会替你创建任何来源。",
  "form.sources.tip":
    "建议提供两个独立来源以便通过资格评估。只有一个来源时可能返回“需更多调研”。",
  "form.sources.name": "来源 {n} 名称 *",
  "form.sources.reference": "参考链接或记录 ID *",
  "form.sources.remove": "删除来源 {n}",
  "form.sources.add": "添加来源",
  "form.signals.title": "信号",
  "form.signals.desc": "选填。分析接口已支持的客观事实信号。",
  "form.signals.empty": "尚未添加信号。",
  "form.signals.kind": "信号 {n} 类型 *",
  "form.signals.kindPlaceholder": "请选择信号类型",
  "form.signals.kindUnknown": "未知信号类型",
  "form.signals.kindLegacy": "旧值",
  "form.signals.detail": "观察到的细节 *",
  "form.signals.remove": "删除信号 {n}",
  "form.signals.add": "添加信号",
  "form.contact.title": "联系人",
  "form.contact.desc": "选填。添加可触达的联系人以启用决策人选择。",
  "form.contact.include": "在本次分析中包含联系人",
  "form.contact.name": "联系人姓名 *",
  "form.contact.jobTitle": "职位",
  "form.contact.email": "邮箱",
  "form.contact.linkedin": "LinkedIn 链接",
  "form.contact.phone": "电话",
  "form.contact.source": "联系人来源 *",
  "form.sender.title": "发件人",
  "form.sender.desc": "仅用于个性化草稿内容，不会用于任何实际发送。",
  "form.sender.name": "发件人姓名 *",
  "form.sender.company": "发件人公司 *",
  "form.sender.valueProp": "价值主张 *",
  "form.generateEmail": "满足资格条件时生成邮件草稿",
  "form.submit": "分析潜在客户",
  "form.submitting": "分析中…",

  "result.kicker": "分析结果",
  "result.subtitle": "展示已保存的工作流结果（草稿模式，不涉及邮件发送状态）。",
  "result.refresh": "刷新结果",
  "result.refreshing": "刷新中…",
  "result.error.code": "错误码：",
  "result.error.requestId": "请求 ID：",
  "result.empty.title": "分析结果将显示在这里",
  "result.empty.body":
    "提交潜在客户后，可查看公司事实、机会资格评估、决策人选择和可审核的邮件草稿。",
  "result.overallStatus": "总体状态",
  "result.requestId": "请求 ID",
  "result.workflowNotes": "工作流备注",
  "result.company": "公司",
  "result.contactDm": "联系人 · 决策人",
  "result.noContact": "未选择联系人",
  "result.noTitle": "职位未知",
  "result.contactStatus": "联系人状态",
  "result.channel": "推荐渠道",
  "result.dmConfidence": "选择置信度",
  "result.selectedContact": "已选联系人：",

  "opp.kicker": "机会",
  "opp.title": "资格评估",
  "opp.score": "评分",
  "opp.scoreHint": "匹配度 · 0–100",
  "opp.confidence": "置信度",
  "opp.confidenceHint": "证据强度",
  "opp.completeness": "完整度",
  "opp.completenessHint": "已知决策输入",
  "opp.decision": "资格判定",
  "opp.recommendedAction": "建议动作",
  "opp.researchNotice":
    "需要更多独立证据才能通过资格评估。请只添加你实际验证过的来源。",
  "opp.why": "判定依据",

  "draft.kicker": "邮件草稿",
  "draft.version": "版本 {n}",
  "draft.notGenerated": "未生成",
  "draft.subject": "主题",
  "draft.body": "正文",
  "draft.copySubject": "复制主题",
  "draft.copyBody": "复制正文",
  "draft.copied": "已复制",
  "draft.empty": "本次结果未生成草稿。请查看上方的资格评估与决策人阶段。",
  "draft.approvedBy": "批准人：{name}",
  "draft.approverName": "审批人姓名",
  "draft.approve": "批准草稿",
  "draft.approving": "批准中…",

  "error.network_error": "无法连接后端服务。请确认后端已在配置的地址上运行。",
  "error.unexpected_client_error": "处理请求时发生了意外错误。",

  "common.notAvailable": "暂无",
} as const;

export type MessageKey = keyof typeof zh;

const en: Record<MessageKey, string> = {
  "app.tagline": "Evidence to outreach · MVP",
  "header.apiDocs": "API docs",
  "header.langSwitch": "中文",
  "hero.kicker": "Prospect analysis workspace",
  "hero.title": "Turn verified importer evidence into a human-reviewed first draft.",

  "provider.checking": "Checking runtime configuration…",
  "provider.unavailable": "Runtime status unavailable",
  "provider.demo": "Demo mode",
  "provider.live": "Live AI",
  "provider.model": "Model",

  "draftMode.notice":
    "Draft mode: this version generates and approves email drafts but does not send them automatically.",

  "form.kicker": "Prospect input",
  "form.title": "Analyze a US importer",
  "form.intro":
    "Submit evidence-backed company facts. The workflow evaluates fit, selects a decision maker, and prepares a review-only email draft.",
  "form.company.title": "Company",
  "form.company.desc": "The importer you want to qualify. Website is optional.",
  "form.company.name": "Company name *",
  "form.company.website": "Website",
  "form.sources.title": "Evidence sources",
  "form.sources.desc":
    "Use only references you actually consulted; no source is created for you.",
  "form.sources.tip":
    "Two independent sources are recommended for qualification. One source is allowed and may return RESEARCH_MORE.",
  "form.sources.name": "Source {n} name *",
  "form.sources.reference": "Reference URL or record ID *",
  "form.sources.remove": "Remove source {n}",
  "form.sources.add": "Add source",
  "form.signals.title": "Signals",
  "form.signals.desc": "Optional factual signals already supported by the analysis API.",
  "form.signals.empty": "No optional signals added.",
  "form.signals.kind": "Signal {n} kind *",
  "form.signals.kindPlaceholder": "Select a signal type",
  "form.signals.kindUnknown": "Unknown signal type",
  "form.signals.kindLegacy": "legacy",
  "form.signals.detail": "Observed detail *",
  "form.signals.remove": "Remove signal {n}",
  "form.signals.add": "Add signal",
  "form.contact.title": "Contact",
  "form.contact.desc": "Optional. Add a reachable person to enable decision-maker selection.",
  "form.contact.include": "Include a contact in this analysis",
  "form.contact.name": "Contact name *",
  "form.contact.jobTitle": "Title",
  "form.contact.email": "Email",
  "form.contact.linkedin": "LinkedIn URL",
  "form.contact.phone": "Phone",
  "form.contact.source": "Contact source *",
  "form.sender.title": "Sender",
  "form.sender.desc": "Used only to personalize the draft; never used to send anything.",
  "form.sender.name": "Sender name *",
  "form.sender.company": "Sender company *",
  "form.sender.valueProp": "Value proposition *",
  "form.generateEmail": "Generate an email draft when qualification conditions are met",
  "form.submit": "Analyze prospect",
  "form.submitting": "Running analysis…",

  "result.kicker": "Analysis result",
  "result.subtitle":
    "Persisted workflow outcomes (draft mode — not a live email delivery status).",
  "result.refresh": "Refresh result",
  "result.refreshing": "Refreshing…",
  "result.error.code": "Code: ",
  "result.error.requestId": "Request ID: ",
  "result.empty.title": "Your analysis will appear here",
  "result.empty.body":
    "Submit a prospect to see company facts, opportunity qualification, decision-maker selection, and a reviewable email draft.",
  "result.overallStatus": "Overall status",
  "result.requestId": "Request ID",
  "result.workflowNotes": "Workflow notes",
  "result.company": "Company",
  "result.contactDm": "Contact · Decision maker",
  "result.noContact": "No contact selected",
  "result.noTitle": "Title unavailable",
  "result.contactStatus": "Contact status",
  "result.channel": "Recommended channel",
  "result.dmConfidence": "Selection confidence",
  "result.selectedContact": "Selected contact: ",

  "opp.kicker": "Opportunity",
  "opp.title": "Qualification assessment",
  "opp.score": "Score",
  "opp.scoreHint": "Fit score · 0–100",
  "opp.confidence": "Confidence",
  "opp.confidenceHint": "Strength of evidence",
  "opp.completeness": "Completeness",
  "opp.completenessHint": "Known decision inputs",
  "opp.decision": "Qualification decision",
  "opp.recommendedAction": "Recommended action",
  "opp.researchNotice":
    "More independent evidence is needed before this prospect can be qualified. Add only sources you have actually verified.",
  "opp.why": "Why this decision",

  "draft.kicker": "Email draft",
  "draft.version": "Version {n}",
  "draft.notGenerated": "Not generated",
  "draft.subject": "Subject",
  "draft.body": "Body",
  "draft.copySubject": "Copy subject",
  "draft.copyBody": "Copy body",
  "draft.copied": "Copied",
  "draft.empty":
    "A draft was not generated for this result. Review the qualification and decision-maker stages above.",
  "draft.approvedBy": "Approved by {name}",
  "draft.approverName": "Approver name",
  "draft.approve": "Approve draft",
  "draft.approving": "Approving…",

  "error.network_error":
    "Unable to reach the API. Confirm the backend is running on the configured URL.",
  "error.unexpected_client_error":
    "Something unexpected happened while processing the request.",

  "common.notAvailable": "Not available",
};

const dictionaries: Record<Lang, Record<MessageKey, string>> = { zh, en };

/** Display-layer translations for API/DB enum values (values stay English). */
const enumLabels: Record<Lang, Record<string, Record<string, string>>> = {
  zh: {
    overall: {
      COMPLETED: "已完成",
      PARTIAL: "部分完成",
      REJECTED: "已拒绝",
      FAILED: "失败",
      "SAVED RESULT": "已保存结果",
    },
    stage: {
      CREATED: "已创建",
      MERGED: "已合并",
      QUALIFIED: "已通过资格",
      REVIEW: "需人工复核",
      RESEARCH_MORE: "需更多调研",
      SELECTED: "已选定",
      GENERATED: "已生成",
      SKIPPED: "已跳过",
      REJECTED: "已拒绝",
      FAILED: "失败",
      "NOT ASSESSED": "未评估",
    },
    decision: {
      qualified: "通过",
      review: "人工复核",
      research_more: "需更多调研",
      disqualified: "不合格",
    },
    recommendedAction: {
      prepare_outreach: "准备触达",
      research_more: "继续调研",
      review: "人工复核",
      disqualify: "放弃线索",
    },
    channel: { email: "邮件", phone: "电话", linkedin: "领英" },
    contactStatus: { active: "活跃", inactive: "不活跃", archived: "已归档" },
    draftStatus: {
      generated: "已生成 · 待审核",
      approved: "已批准",
      rejected: "已拒绝",
    },
    signalKind: {
      import_activity: "进口活跃度",
      china_dependency: "中国供应链依赖",
      shipping_fit: "运输匹配度",
      cargo_value_potential: "货值潜力",
      company_scale: "企业规模",
      growth_signal: "增长信号",
      logistics_complexity: "物流复杂度",
      pain_point: "潜在痛点",
    },
  },
  en: {
    overall: {},
    stage: {},
    decision: {},
    recommendedAction: {},
    channel: {},
    contactStatus: {},
    draftStatus: { generated: "Generated · awaiting review", approved: "Approved" },
    signalKind: {
      import_activity: "Import activity",
      china_dependency: "China supply dependency",
      shipping_fit: "Shipping fit",
      cargo_value_potential: "Cargo value potential",
      company_scale: "Company scale",
      growth_signal: "Growth signal",
      logistics_complexity: "Logistics complexity",
      pain_point: "Pain point",
    },
  },
};

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
  label: (group: string, value: string | null | undefined) => string;
  dateLocale: string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

/* The language lives in localStorage; useSyncExternalStore keeps SSR
   hydration consistent (server always renders the zh default). */
const langListeners = new Set<() => void>();

function subscribeToLang(listener: () => void) {
  langListeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    langListeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function readStoredLang(): Lang {
  return window.localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore<Lang>(
    subscribeToLang,
    readStoredLang,
    () => "zh",
  );

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    for (const listener of langListeners) listener();
  }, []);

  const t = useCallback(
    (key: MessageKey, params?: Record<string, string | number>) => {
      let text: string = dictionaries[lang][key];
      if (params) {
        for (const [name, value] of Object.entries(params)) {
          text = text.replaceAll(`{${name}}`, String(value));
        }
      }
      return text;
    },
    [lang],
  );

  const label = useCallback(
    (group: string, value: string | null | undefined) => {
      if (!value) return dictionaries[lang]["common.notAvailable"];
      return enumLabels[lang][group]?.[value] ?? humanize(value);
    },
    [lang],
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang,
      t,
      label,
      dateLocale: lang === "zh" ? "zh-CN" : "en-US",
    }),
    [lang, setLang, t, label],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
