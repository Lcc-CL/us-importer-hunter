"""LLM service: single gateway to the OpenAI SDK.

Agents and other services call LLMs only through this service —
model selection, retries, and structured-output parsing live here.
"""
