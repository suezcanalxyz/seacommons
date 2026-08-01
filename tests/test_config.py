# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.config import SuezCanalConfig


def test_opendrift_prewarm_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("OPENDRIFT_PREWARM_ENABLED", raising=False)

    settings = SuezCanalConfig(_env_file=None)

    assert settings.OPENDRIFT_PREWARM_ENABLED is True


def test_opendrift_prewarm_can_be_disabled(monkeypatch):
    monkeypatch.setenv("OPENDRIFT_PREWARM_ENABLED", "false")

    settings = SuezCanalConfig(_env_file=None)

    assert settings.OPENDRIFT_PREWARM_ENABLED is False
