# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md Section 5: Connector contract.

Exit gate (v0-bounded, per module docstring): a connector's failure
never propagates as an uncaught exception and never looks like an
empty-but-successful fetch -- run_connector_fetch() always returns a
typed FetchResult either way.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from core.intel.connector_contract import (
    Connector,
    ConnectorClass,
    FailureClass,
    FetchResult,
    run_connector_fetch,
)


class _WorkingConnector(Connector):
    source_id = "test-working"
    connector_class = ConnectorClass.IMPORT
    capabilities = ("poll",)

    def fetch(self, cursor: Optional[str] = None) -> FetchResult:
        return FetchResult(source_id=self.source_id, ok=True, items=[{"id": "1"}])

    def to_observation(self, raw_item: Any) -> dict[str, Any]:
        return {"source_id": raw_item["id"]}

    def idempotency_key(self, raw_item: Any) -> str:
        return f"{self.source_id}:{raw_item['id']}"


class _EmptyButHealthyConnector(Connector):
    source_id = "test-empty"
    connector_class = ConnectorClass.IMPORT

    def fetch(self, cursor: Optional[str] = None) -> FetchResult:
        return FetchResult(source_id=self.source_id, ok=True, items=[])

    def to_observation(self, raw_item: Any) -> dict[str, Any]:
        return {}

    def idempotency_key(self, raw_item: Any) -> str:
        return "n/a"


class _ExplicitlyFailingConnector(Connector):
    source_id = "test-failing"
    connector_class = ConnectorClass.IMPORT

    def fetch(self, cursor: Optional[str] = None) -> FetchResult:
        return FetchResult(
            source_id=self.source_id, ok=False,
            failure_class=FailureClass.RATE_LIMITED, failure_detail="429",
        )

    def to_observation(self, raw_item: Any) -> dict[str, Any]:
        return {}

    def idempotency_key(self, raw_item: Any) -> str:
        return "n/a"


class _CrashingConnector(Connector):
    source_id = "test-crashing"
    connector_class = ConnectorClass.IMPORT

    def fetch(self, cursor: Optional[str] = None) -> FetchResult:
        raise RuntimeError("upstream exploded")

    def to_observation(self, raw_item: Any) -> dict[str, Any]:
        return {}

    def idempotency_key(self, raw_item: Any) -> str:
        return "n/a"


def test_cannot_instantiate_the_bare_abc():
    with pytest.raises(TypeError):
        Connector()  # type: ignore[abstract]


def test_a_successful_fetch_returns_its_items():
    result = run_connector_fetch(_WorkingConnector())
    assert result.ok is True
    assert result.items == [{"id": "1"}]
    assert result.failure_class is None


def test_a_real_empty_result_is_not_treated_as_a_failure():
    """docs/updates.md Section 5: a source genuinely having nothing new
    is a real, distinct outcome from a failed fetch."""
    result = run_connector_fetch(_EmptyButHealthyConnector())
    assert result.ok is True
    assert result.items == []
    assert result.failure_class is None


def test_an_explicit_source_side_failure_is_never_ok():
    result = run_connector_fetch(_ExplicitlyFailingConnector())
    assert result.ok is False
    assert result.failure_class == FailureClass.RATE_LIMITED


def test_a_crashing_connector_never_raises_out_of_run_connector_fetch():
    """docs/updates.md Section 5: "Connector failure must not mutate
    existing incidents or silently mark sources as empty" -- an
    unexpected exception becomes a typed failure, not a crash and not a
    silent empty success."""
    result = run_connector_fetch(_CrashingConnector())
    assert result.ok is False
    assert result.failure_class == FailureClass.UNKNOWN
    assert "upstream exploded" in result.failure_detail
    assert result.items == []  # never silently looks like a successful empty fetch


def test_idempotency_key_is_deterministic_for_the_same_raw_item():
    connector = _WorkingConnector()
    raw_item = {"id": "abc"}
    assert connector.idempotency_key(raw_item) == connector.idempotency_key(raw_item)
