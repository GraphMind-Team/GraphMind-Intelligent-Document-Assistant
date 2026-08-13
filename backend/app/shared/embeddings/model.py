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
"""

from functools import lru_cache

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@lru_cache
def _get_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """One embedding vector per input text, in the same order."""
    model = _get_model()
    return [vector.tolist() for vector in model.embed(texts)]
