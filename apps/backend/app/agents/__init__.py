"""Agents layer: LLM reasoning units.

Rules:
- Agents never access the database directly; they obtain data via tools.
- Every agent output is a typed Pydantic schema (see app.schemas).
"""
