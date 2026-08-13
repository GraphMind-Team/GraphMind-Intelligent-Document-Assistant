"""Local passage embeddings (Story 2.3).

Runs entirely offline via `fastembed` (ONNX Runtime) rather than
`sentence-transformers`/`torch` -- the project has a documented
zero-cost/free-tier-only constraint, and Render's free-tier instance
(512MB RAM) doesn't comfortably fit torch's install size (~800MB-1GB) or
a loaded MiniLM's runtime footprint (~400-600MB RSS) under
sentence-transformers. `fastembed` runs the same
`sentence-transformers/all-MiniLM-L6-v2` model (384-dim) far lighter on
both axes.

The `fastembed` import is deliberately inside `_get_model`'s body, not at
module top level: `service.py` imports `embed_texts` at module scope, and
`service.py` is transitively imported by essentially every backend test
via `app.main`. An eager top-level import would make every test in the
suite pay fastembed's import cost, whether or not embedding is ever
actually exercised.

A hand-rolled double-checked-locking singleton, not `@lru_cache`:
background ingestion tasks run in Starlette's threadpool, so two uploads
processed concurrently can both miss an empty cache before either has
finished constructing the model. `lru_cache` only guards its internal
dict against concurrent mutation -- it holds no lock across the wrapped
call itself, so both threads would proceed to build a full `TextEmbedding`
instance in parallel. On a 512MB instance, two models loaded at once
(rather than one) is plausibly the difference between running and OOMing.
The lock here is only ever taken on the first call from each of
potentially several racing threads; every call after construction hits
the `is None` check and returns immediately, lock-free.
"""

import threading

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model_lock = threading.Lock()
_model_instance = None


def _get_model():
    global _model_instance
    if _model_instance is None:
        with _model_lock:
            if _model_instance is None:  # re-check: lost the race, not the need
                from fastembed import TextEmbedding

                _model_instance = TextEmbedding(model_name=MODEL_NAME)
    return _model_instance


def embed_texts(texts: list[str]) -> list[list[float]]:
    """One embedding vector per input text, in the same order."""
    model = _get_model()
    return [vector.tolist() for vector in model.embed(texts)]
