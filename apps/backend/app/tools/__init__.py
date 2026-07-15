"""Tools layer: capabilities exposed to agents (data access, external APIs).

Rules:
- Tools are the only path from agents to data sources.
- Tool inputs and outputs are typed Pydantic schemas.
"""
