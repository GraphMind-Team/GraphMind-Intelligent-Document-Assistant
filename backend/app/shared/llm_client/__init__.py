"""Shared LLM-client wrapper.

Per architecture decision AD-6, this package is the sole path to
OpenRouter, centralizing retry/timeout handling and enforcing the refusal
short-circuit before any generation call.

Empty in Story 1.1 (running project skeleton) -- no real LLM-client code
exists yet. Future stories add the OpenRouter client here.
"""
