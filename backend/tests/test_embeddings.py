"""`shared/embeddings` tests (Story 2.3): `embed_texts` returns one vector
per input text, in order. `_get_model` is monkeypatched to a fake object
(never the real `fastembed` model) so this test stays fast and offline --
mirroring `shapes.py`'s dataclass shape without downloading real weights.
"""

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
