"""Observability layer: metrics, logging and tracing.

This is where "why did the agent fail / why did the prompt fail" gets
answered: every agent run, tool call and LLM request should be visible
here — inputs, outputs, prompt version, token usage, latency, errors.
"""
