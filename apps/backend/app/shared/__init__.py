"""Shared layer: cross-cutting primitives used by any layer.

Only dependency-free building blocks live here (constants, enums,
exceptions, type aliases) — never business logic, never I/O. Everything
here may be imported from anywhere without creating coupling.
"""
