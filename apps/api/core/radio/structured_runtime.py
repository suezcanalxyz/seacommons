# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any, Mapping


class StructuredRadioRuntime:
    """Disabled-by-default ingestion boundary for already-decoded DSC/NAVTEX input."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = bool(enabled)
        self._accepted = 0
        self._projected = 0
        self._failed = 0

    def status(self) -> dict[str, int | bool]:
        return {
            "enabled": self.enabled,
            "accepted": self._accepted,
            "projected": self._projected,
            "failed": self._failed,
        }

    def ingest_dsc(self, payload: Mapping[str, Any], **context: Any) -> dict[str, Any]:
        from core.observability import record_structured_radio_event

        if not self.enabled:
            record_structured_radio_event(kind="dsc", outcome="disabled")
            return {"accepted": False, "reason": "disabled"}
        try:
            from core.db.session import session_scope
            from core.radio.dsc import normalize_dsc_decoder_message
            from core.radio.safety_projection import ingest_dsc_safety_candidate
            from core.radio.structured_source_observation import persist_dsc_observation

            frequency_hz = int(context.pop("frequency_hz"))
            observation = normalize_dsc_decoder_message(
                payload,
                frequency_hz=frequency_hz,
                **context,
            )
            with session_scope() as db:
                persisted = persist_dsc_observation(db, observation)
            projected = ingest_dsc_safety_candidate(
                observation,
                evidence_observation_id=persisted.observation_id,
            )
        except (TypeError, ValueError, KeyError):
            self._failed += 1
            record_structured_radio_event(kind="dsc", outcome="invalid")
            return {"accepted": False, "reason": "invalid"}
        except Exception:
            self._failed += 1
            record_structured_radio_event(kind="dsc", outcome="persist_failed")
            return {"accepted": False, "reason": "persist_failed"}

        self._accepted += 1
        if projected:
            self._projected += 1
            record_structured_radio_event(kind="dsc", outcome="projected")
        else:
            record_structured_radio_event(kind="dsc", outcome="accepted")
        result: dict[str, Any] = {
            "accepted": True,
            "projected": projected,
            "observation_id": persisted.observation_id,
        }
        if projected:
            from core.radio.safety_projection import project_dsc_safety_candidate

            candidate = project_dsc_safety_candidate(
                observation,
                evidence_observation_id=persisted.observation_id,
            )
            if candidate is not None:
                result["candidate_id"] = candidate.id
        return result

    def ingest_navtex(
        self,
        block: str,
        *,
        decoder_message_id: str | None = None,
        area: str | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        from core.observability import record_structured_radio_event

        if not self.enabled:
            record_structured_radio_event(kind="navtex", outcome="disabled")
            return {"accepted": False, "reason": "disabled"}
        try:
            from core.db.session import session_scope
            from core.radio.navtex import parse_navtex_block
            from core.radio.structured_source_observation import persist_navtex_observation

            frequency_hz = int(context.pop("frequency_hz"))
            observation = parse_navtex_block(
                block,
                frequency_hz=frequency_hz,
                decoder_message_id=decoder_message_id,
                area=area,
                **context,
            )
            with session_scope() as db:
                persisted = persist_navtex_observation(db, observation)
        except (TypeError, ValueError, KeyError):
            self._failed += 1
            record_structured_radio_event(kind="navtex", outcome="invalid")
            return {"accepted": False, "reason": "invalid"}
        except Exception:
            self._failed += 1
            record_structured_radio_event(kind="navtex", outcome="persist_failed")
            return {"accepted": False, "reason": "persist_failed"}

        self._accepted += 1
        record_structured_radio_event(kind="navtex", outcome="context_only")
        return {
            "accepted": True,
            "projected": False,
            "observation_id": persisted.observation_id,
        }


_runtime: StructuredRadioRuntime | None = None


def runtime_from_config() -> StructuredRadioRuntime:
    from core.config import config

    return StructuredRadioRuntime(enabled=config.STRUCTURED_RADIO_ENABLED)


def get_structured_radio_runtime() -> StructuredRadioRuntime:
    global _runtime
    if _runtime is None:
        _runtime = runtime_from_config()
    return _runtime
