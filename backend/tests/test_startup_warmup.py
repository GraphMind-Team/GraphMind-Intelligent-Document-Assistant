"""Startup embedding-warmup tests (Story 3.1).

The warmup exists so `chat/service.py`'s `ask_question` isn't the first
caller to pay fastembed's model construction/download cost inline (see
`main._warm_embedding_model`'s docstring). Two properties matter and are
tested separately here, because only one of them is about what the warmup
does -- the other is about what it must never do:

  1. It actually loads the model, and survives a failure rather than
     taking the app down with it.
  2. It does NOT block `lifespan` from yielding. On a cold instance with
     an ephemeral filesystem, an inline warmup is a multi-minute download
     holding the app before uvicorn accepts traffic, which can fail a
     platform health check outright -- a latency fix turning into a deploy
     failure.

Property 2 is the reason `tests/conftest.py`'s `client` fixture builds a
bare `TestClient(app)` rather than entering it as a context manager: that
fixture never runs `lifespan` at all, so nothing in the rest of the suite
would notice if the warmup regressed to a blocking call. This file enters
the lifespan explicitly, which is also why it stubs `embed_texts` -- an
unstubbed run here would download the real model during the test suite.
"""

import asyncio
import threading

from app import main as main_module


def test_warm_embedding_model_loads_the_model(monkeypatch):
    captured = {}

    def _fake_embed(texts):
        captured["texts"] = texts
        return [[0.0] * 384 for _ in texts]

    monkeypatch.setattr(main_module, "embed_texts", _fake_embed)

    main_module._warm_embedding_model()

    assert captured["texts"] == ["warmup"]


def test_warm_embedding_model_swallows_failure_rather_than_raising(monkeypatch, caplog):
    """Same best-effort contract as the Weaviate/Neo4j warmups: a failure
    only means the first real embed call pays the cost this would have
    absorbed. It also runs on a daemon thread, where there is no caller
    left to propagate to -- an escaping exception would be logged by
    threading itself as an unhandled error, not handled anywhere."""

    def _boom(texts):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(main_module, "embed_texts", _boom)

    with caplog.at_level("ERROR"):
        main_module._warm_embedding_model()  # must not raise

    assert "Embedding model warmup failed" in caplog.text


def test_lifespan_does_not_block_startup_on_the_embedding_warmup(monkeypatch):
    """The regression this guards: moving the warmup back inline.

    Deliberately does NOT assert from inside the stubbed `embed_texts` --
    `_warm_embedding_model` swallows every exception by design, so an
    `assert` raised in there is silently eaten and the test passes while
    the app blocks (verified: an inline warmup makes that version of this
    test green). The signal has to be observed from outside instead:
    `lifespan` is entered on its own thread, and startup is required to
    reach the yield while the warmup is still parked mid-"download".
    """
    started = threading.Event()
    release = threading.Event()
    yielded = threading.Event()

    def _slow_embed(texts):
        started.set()
        # Stands in for a cold-instance model download. Inline, `lifespan`
        # cannot yield until this returns.
        release.wait(timeout=30)
        return [[0.0] * 384]

    monkeypatch.setattr(main_module, "embed_texts", _slow_embed)
    monkeypatch.setattr(main_module, "ensure_ready", lambda: None)
    monkeypatch.setattr(main_module, "ensure_neo4j_ready", lambda: None)
    monkeypatch.setattr(main_module, "close_weaviate_client", lambda: None)
    monkeypatch.setattr(main_module, "close_neo4j_driver", lambda: None)

    async def _enter_lifespan():
        async with main_module.lifespan(main_module.app):
            yielded.set()

    runner = threading.Thread(target=lambda: asyncio.run(_enter_lifespan()), daemon=True)
    runner.start()
    try:
        assert started.wait(timeout=5), "warmup never ran"
        # The whole point: startup completed while the warmup is still
        # blocked below. Inline, this stays unset until `release` is set,
        # and the assertion fails here rather than hanging the suite.
        assert yielded.wait(timeout=5), "lifespan never yielded -- warmup is blocking startup"
    finally:
        release.set()
        runner.join(timeout=10)


def test_lifespan_runs_the_warmup_on_a_daemon_thread(monkeypatch):
    """A non-daemon thread would keep the process alive after shutdown,
    turning a mid-download restart into a hang instead of a restart."""
    captured = {}

    class _FakeThread:
        def __init__(self, target, name=None, daemon=None):
            captured["target"] = target
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(main_module.threading, "Thread", _FakeThread)
    # Stubbed even though `_FakeThread` never runs the target: if this
    # regressed to an inline call, an unstubbed `embed_texts` would
    # download the real model mid-test-suite before failing.
    monkeypatch.setattr(main_module, "embed_texts", lambda texts: [[0.0] * 384])
    monkeypatch.setattr(main_module, "ensure_ready", lambda: None)
    monkeypatch.setattr(main_module, "ensure_neo4j_ready", lambda: None)
    monkeypatch.setattr(main_module, "close_weaviate_client", lambda: None)
    monkeypatch.setattr(main_module, "close_neo4j_driver", lambda: None)

    async def _run():
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(_run())

    assert captured["started"] is True
    assert captured["daemon"] is True
    assert captured["target"] is main_module._warm_embedding_model
