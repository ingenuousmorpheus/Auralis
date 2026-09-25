"""Shared test setup."""
import pytest


@pytest.fixture(autouse=True)
def _no_host_memory_gate(monkeypatch, tmp_path):
    """The model manager refuses heavy jobs when the host is short of memory. Tests use
    fake engines, so the real host's free memory must not decide their outcome; tests of
    the gate itself remove this and inject a memory reading. Engine choices are kept in
    a temporary file so tests never touch the user's settings."""
    monkeypatch.setenv("AURALIS_MEMORY_CHECK", "off")
    from auralis.models import REGISTRY

    monkeypatch.setattr(REGISTRY, "config_path", tmp_path / "models.json")
