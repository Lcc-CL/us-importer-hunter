"""first-outreach-v1: the first cold email to a qualified US importer.

Hard rules live in the system prompt; the user prompt carries ONLY the
facts from EmailGenerationContext. Superseded versions get archived to
app/prompts/versions/sales/ (ADR-0008).
"""

from app.domain.services import EmailGenerationContext

PROMPT_VERSION = "first-outreach-v1"

SYSTEM_PROMPT = """\
You write first-touch B2B outreach emails for an international freight
forwarder contacting US importers.

Hard rules:
- English only. US business tone: direct, courteous, no hype.
- Body length 80-150 words. One short subject line (under 60 characters).
- Exactly one clear call to action (a brief reply or a 15-minute call).
- Use ONLY the facts provided in the context. Do not invent import
  volumes, suppliers, cargo values, savings percentages, or the
  prospect's current freight forwarder.
- If the available facts are thin, stay conservative and generic about
  their business; never guess specifics.
- No pricing, no quotes, no discounts.
- No exaggerated claims ("best", "guaranteed", "revolutionary").

Respond with JSON only:
{"subject": "<subject line>", "body": "<email body>"}
"""


def build_user_prompt(context: EmailGenerationContext) -> str:
    evidence_lines = "\n".join(f"- {claim}" for claim in context.available_evidence) or "- none"
    reason_lines = "\n".join(f"- {reason}" for reason in context.opportunity_reasons) or "- none"
    return f"""\
Write the first outreach email using only these facts.

Prospect:
- Company: {context.company_name}
- Website: {context.website or "unknown"}
- Recipient: {context.contact_name} ({context.contact_title or "role unknown"})

Why we believe they are a fit (internal analysis, do not quote verbatim):
{reason_lines}

Verifiable facts you may reference:
{evidence_lines}

Sender:
- Name: {context.sender_name}
- Company: {context.sender_company}
- Value proposition: {context.sender_value_proposition}
"""
