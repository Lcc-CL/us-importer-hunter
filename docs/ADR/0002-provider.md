# ADR-0002: LLM provider abstraction

Date: 2026-07-15 · Status: Accepted

## Context

The product starts on OpenAI but must be able to switch or mix vendors
(Anthropic, DeepSeek, Gemini) without rewriting business code.

## Decision

All LLM calls flow: agent → `llm` service (gateway) →
`app/providers/<vendor>` adapter behind a common interface. Agents and
services never import vendor SDKs. Only the OpenAI adapter is built for
MVP; other vendor SDKs are not installed until their adapter lands.
The provider interface is extracted from real usage when `services/llm`
is first implemented — not designed up front.

## Consequences

- Vendor switch = new adapter + config change; zero churn above providers.
- Model selection, retries, token accounting concentrate in one gateway.
