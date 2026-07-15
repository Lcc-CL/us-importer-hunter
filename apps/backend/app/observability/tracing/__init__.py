"""Tracing: spans across workflow → agent → llm/tool calls, carrying
prompt version and model info, so a failed run can be replayed and
diagnosed end-to-end."""
