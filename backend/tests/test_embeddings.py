"""`shared/embeddings` tests (Story 2.3): `embed_texts` returns one vector
per input text, in order. `_get_model` is monkeypatched to a fake object
(never the real `fastembed` model) so this test stays fast and offline --
mirroring `shapes.py`'s dataclass shape without downloading real weights.
"""

import sys
import threading
import time
import types

import numpy as np

from app.shared.embeddings import EMBEDDING_DIM, embed_texts
from app.shared.embeddings import model as embeddings_model


class _FakeModel:
    def embed(self, texts):
        return [np.full(EMBEDDING_DIM, fill_value=float(i)) for i, _ in enumerate(texts)]


def test_embed_texts_returns_one_vector_per_text_in_order(monkeypatch):
    monkeypatch.setattr(embeddings_model, "_get_model", lambda: _FakeModel())

    vectors = embed_texts(["first passage", "second passage", "third passage"])

    assert len(vectors) == 3
    for i, vector in enumerate(vectors):
        assert len(vector) == EMBEDDING_DIM
        assert vector[0] == float(i)
        assert isinstance(vector, list)


def test_embed_texts_empty_list_returns_empty_list(monkeypatch):
    monkeypatch.setattr(embeddings_model, "_get_model", lambda: _FakeModel())

    assert embed_texts([]) == []


def test_get_model_is_constructed_exactly_once_under_concurrent_calls(monkeypatch):
    """Background ingestion tasks run in Starlette's threadpool, so two
    uploads processed concurrently can both call `_get_model` before
    either finishes constructing the model. `@lru_cache` alone doesn't
    prevent this -- it only guards its cache dict, not the wrapped call --
    so without the explicit lock, both would build a full model instance
    in parallel. This pins that exactly one construction happens even when
    several threads race for it.
    """
    monkeypatch.setattr(embeddings_model, "_model_instance", None)

    construction_count = 0
    construction_lock = threading.Lock()

    class _SlowFakeModel:
        def __init__(self, model_name):
            # Widens the race window -- without the lock, several threads
            # would all pass the `is None` check and reach here together.
            time.sleep(0.05)
            nonlocal construction_count
            with construction_lock:
                construction_count += 1

    fake_fastembed_module = types.SimpleNamespace(TextEmbedding=_SlowFakeModel)
    monkeypatch.setitem(sys.modules, "fastembed", fake_fastembed_module)

    threads = [threading.Thread(target=embeddings_model._get_model) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert construction_count == 1
