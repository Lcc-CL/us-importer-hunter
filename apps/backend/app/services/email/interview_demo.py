"""Generate a draft from fixed synthetic facts under a shared Redis quota."""

from typing import Literal

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from app.domain.services import EmailDraftGenerator, EmailGenerationContext

CASE = EmailGenerationContext(
    company_name="Cedar Harbor Demo Imports",
    website=None,
    contact_name="Logistics Team",
    contact_title=None,
    opportunity_score=0,
    qualification_decision="manual review",
    opportunity_reasons=("The case is synthetic and shipment volume is unknown.",),
    available_evidence=("The scenario describes inbound home storage products through Long Beach",),
    sender_name="Demo operator",
    sender_company="Example Freight",
    sender_value_proposition="We can discuss inbound routing and delivery planning.",
)

# One attempt per minute across clients and replicas. Reserve before calling the
# provider, including timeouts and failures. The total counter has no expiry.
RESERVE_ATTEMPT = """
if tonumber(redis.call('GET', KEYS[1]) or '0') >= tonumber(ARGV[1]) then
    return 0
end
if not redis.call('SET', KEYS[2], '1', 'EX', 60, 'NX') then
    return 0
end
redis.call('INCR', KEYS[1])
return 1
"""


class DemoQuotaExceeded(Exception):
    """The shared cooldown or total allowance has been reached."""


class InterviewDraft(BaseModel):
    source: Literal["live", "cached"]
    model: str
    subject: str
    body: str


async def generate_interview_draft(
    redis: Redis, generator: EmailDraftGenerator, allowance: int
) -> InterviewDraft:
    namespace = "{interview-demo}"
    cache_key = f"{namespace}:draft:v1:{generator.model_name}:{CASE.fingerprint()}"
    saved = await redis.get(cache_key)
    if saved:
        try:
            return InterviewDraft.model_validate_json(saved).model_copy(update={"source": "cached"})
        except ValidationError:
            pass

    reserved = await redis.eval(
        RESERVE_ATTEMPT, 2, f"{namespace}:attempts", f"{namespace}:cooldown", allowance
    )
    if not reserved:
        raise DemoQuotaExceeded

    draft = await generator.generate(CASE)
    result = InterviewDraft(
        source="live", model=generator.model_name, subject=draft.subject, body=draft.body
    )
    await redis.set(cache_key, result.model_dump_json(), ex=86_400)
    return result
