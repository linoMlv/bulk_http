"""Tests for EngineConfig global defaults and validation."""

import pickle

import pytest

from bulk_http.config import EngineConfig


def test_engine_config_defaults() -> None:
    cfg = EngineConfig()
    assert cfg.workers == "auto"
    assert cfg.concurrency_per_worker == 450
    assert cfg.chunk_size == 1000
    assert cfg.impersonate == "chrome"
    assert cfg.stream_cut is None
    assert cfg.cut_on == "wire"
    assert cfg.fast_status is False
    assert cfg.accept_encoding == "impersonate"
    assert cfg.http_version == "auto"
    assert cfg.verify_ssl is True
    assert cfg.follow_redirects is False
    assert cfg.respect_robots is False
    assert cfg.retries == 2
    assert cfg.retry_non_idempotent is False
    assert cfg.in_flight_batches >= 1


def test_engine_config_is_picklable() -> None:
    cfg = EngineConfig(workers=4, stream_cut=15_000)
    assert pickle.loads(pickle.dumps(cfg)) == cfg


@pytest.mark.parametrize(
    "kwargs",
    [
        {"workers": 0},
        {"workers": "many"},
        {"concurrency_per_worker": 0},
        {"chunk_size": 0},
        {"stream_cut": 0},
        {"cut_on": "bogus"},
        {"http_version": "h5"},
        {"accept_encoding": "gzip"},
        {"max_redirects": -1},
        {"timeout": 0},
        {"total_timeout": -1.0},
        {"retries": -1},
        {"in_flight_batches": 0},
        {"per_domain_rate_limit": 0},
        {"max_tasks_per_child": 0},
    ],
)
def test_engine_config_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EngineConfig(**kwargs)  # type: ignore[arg-type]


def test_engine_config_compliance_defaults() -> None:
    cfg = EngineConfig()
    assert cfg.allowlist == ()
    assert cfg.denylist == ()
    assert cfg.identity_header is None
    assert cfg.authorization is None


def test_engine_config_accepts_compliance_options() -> None:
    cfg = EngineConfig(
        allowlist=("ok.com",),
        denylist=("bad.com",),
        identity_header=("X-Contact", "team@example.com"),
        authorization="scope #1",
    )
    assert cfg.denylist == ("bad.com",)
    assert cfg.identity_header == ("X-Contact", "team@example.com")
