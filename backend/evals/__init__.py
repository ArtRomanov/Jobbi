"""Behavioural evals that call the real AI provider. Run by hand, never in CI.

They live outside `tests/` so the normal pytest run never spends Groq tokens.
"""
