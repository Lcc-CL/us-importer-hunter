"""Providers layer: LLM vendor adapters behind a common interface.

The llm service depends only on the provider interface defined here;
switching or adding vendors never touches services, agents or workflows.
"""
