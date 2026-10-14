from __future__ import annotations

import base64
import math
from array import array
import sys
import json
import hashlib
import queue
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Mapping, Protocol

from core.radio.provider import DecodedRadioMessage

_MAX_EPHEMERAL_FRAME_BYTES = 262_144


@dataclass(frozen=True)
class EphemeralRadioFrame:
    receiver_id: str
    provider: str
    physical_lineage: str
    frequency_hz: int
    mode: str
    observed_at: datetime
    sample_rate_hz: int
    encoding: str
    payload: bytes
    source_terms: str | None = None
    session_id: str | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        if not self.receiver_id.strip() or not self.provider.strip() or not self.physical_lineage.strip():
            raise ValueError("receiver/provider/lineage required")
        if self.frequency_hz <= 0 or self.sample_rate_hz <= 0:
            raise ValueError("frequency and sample rate must be positive")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not isinstance(self.payload, bytes) or len(self.payload) > _MAX_EPHEMERAL_FRAME_BYTES:
            raise ValueError("payload exceeds ephemeral frame bound")
        if self.session_id is not None and len(self.session_id) > 128:
            raise ValueError("audio session identifier too long")
        if self.sequence is not None and not (0 <= self.sequence <= 0xFFFFFFFF):
            raise ValueError("invalid audio packet sequence")

    def public_metadata(self) -> dict[str, object]:
        return {
            "receiver_id": self.receiver_id,
            "provider": self.provider,
            "frequency_hz": self.frequency_hz,
            "mode": self.mode,
            "observed_at": self.observed_at.isoformat(),
            "sample_rate_hz": self.sample_rate_hz,
            "encoding": self.encoding,
            "bytes": len(self.payload),
        }


def _pcm_quality(frame: EphemeralRadioFrame) -> dict[str, object]:
    """Ephemeral coarse audio diagnostics; samples and identifiers are not retained."""
    data = frame.payload
    duration_ms = round(1000 * (len(data) // 2) / frame.sample_rate_hz, 1)
    result: dict[str, object] = {"duration_ms": duration_ms, "bytes": len(data), "valid_pcm": False}
    if not data or len(data) % 2 or frame.encoding not in {"kiwi_snd_raw", "openwebrx_pcm_s16le", "pcm_s16le"}:
        return result
    # Sample at a bounded stride rather than accumulating raw audio in memory.
    # Signed magnitude is endian-independent for clipping only; RMS needs correct order.
    samples = array("h")
    samples.frombytes(data)
    byteorder = "big" if frame.encoding == "kiwi_snd_raw" else "little"
    if sys.byteorder != byteorder:
        samples.byteswap()
    stride = max(1, len(samples) // 1024)
    sampled = samples[::stride]
    if not sampled:
        return result
    rms = math.sqrt(sum(float(x) * float(x) for x in sampled) / len(sampled)) / 32768
    clipped = sum(abs(x) >= 32500 for x in sampled) / len(sampled)
    result.update(valid_pcm=True, rms=round(rms, 5), clipped_fraction=round(clipped, 4),
                  silent=rms < 0.002, clipping=clipped > 0.02)
    return result


class RadioDecoder(Protocol):
    def decode(self, frame: EphemeralRadioFrame) -> Iterable[Mapping[str, object]]: ...


class RadioDecoderRuntime:
    def __init__(
        self,
        *,
        enabled: bool,
        decoders: Iterable[RadioDecoder] = (),
        decoded_handler: Callable[[DecodedRadioMessage], dict[str, object]],
        queue_size: int = 32,
        decoder_factory: Callable[[], Iterable[RadioDecoder]] | None = None,
        worker_count: int = 1,
    ) -> None:
        self.enabled = bool(enabled)
        self._decoders = tuple(decoders)
        self._decoded_handler = decoded_handler
        self._frames = 0
        self._decoded = 0
        self._accepted = 0
        self._rejected = 0
        self._invalid = 0
        self._dropped = 0
        self._errors = 0
        self._audio_sampled = 0
        self._audio_silent = 0
        self._audio_clipped = 0
        self._audio_invalid = 0
        self._audio_duration_ms = 0.0
        self._audio_rms_sum = 0.0
        # One FIFO per shard, selected by physical lineage. All frames from a
        # receiver remain ordered and are decoded by the same persistent process.
        # Existing direct/isolated callers retain one worker and one queue.
        shards = max(1, min(int(worker_count), 4)) if decoder_factory else 1
        self._queues = tuple(queue.Queue(maxsize=max(1, int(queue_size))) for _ in range(shards))
        self._queue = self._queues[0]  # backward compatible single-shard runtime
        self._decoder_sets = [self._decoders]
        for _ in range(shards - 1):
            self._decoder_sets.append(tuple(decoder_factory()))
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "decoders": len(self._decoders),
            "frames": self._frames,
            "decoded": self._decoded,
            "accepted": self._accepted,
            "rejected": self._rejected,
            "invalid": self._invalid,
            "dropped": self._dropped,
            "errors": self._errors,
            "audio_quality": {
                "sampled_frames": self._audio_sampled,
                "silent_frames": self._audio_silent,
                "clipped_frames": self._audio_clipped,
                "invalid_pcm_frames": self._audio_invalid,
                "sampled_duration_s": round(self._audio_duration_ms / 1000, 1),
                "mean_rms": round(self._audio_rms_sum / max(1, self._audio_sampled - self._audio_invalid), 5),
                "sampling_interval_frames": 64,
                "note": "Sampled signal quality only; not a decoded transmission or an RF SNR measurement",
            },
            "queued": sum(q.qsize() for q in self._queues),
            "worker_alive": bool(self._workers) and all(w.is_alive() for w in self._workers),
            "worker_count": len(self._queues),
            "queues": [q.qsize() for q in self._queues],
            "continuity_resets": sum(int(getattr(d, "continuity_resets", 0)) for group in self._decoder_sets for d in group),
            "state_evictions": sum(int(getattr(d, "state_evictions", 0)) for group in self._decoder_sets for d in group),
            "bridge_errors": sum(int(getattr(d, "bridge_errors", 0)) for group in self._decoder_sets for d in group),
        }

    def start(self) -> None:
        if not self.enabled or self._workers:
            return
        self._stop.clear()
        for i, (q, decoders) in enumerate(zip(self._queues, self._decoder_sets)):
            worker = threading.Thread(target=self._run, args=(q, decoders), daemon=True,
                                      name=f"radio-decoder-{i}")
            self._workers.append(worker)
            worker.start()
        self._worker = self._workers[0]

    def submit_frame(self, frame: EphemeralRadioFrame) -> bool:
        if not self.enabled:
            return False
        self.start()
        try:
            lineage = frame.physical_lineage.encode("utf-8")
            shard = int.from_bytes(hashlib.blake2s(lineage, digest_size=4).digest(), "big") % len(self._queues)
            self._queues[shard].put_nowait(frame)
            return True
        except queue.Full:
            self._dropped += 1
            return False

    def _run(self, q: queue.Queue[EphemeralRadioFrame], decoders: tuple[RadioDecoder, ...]) -> None:
        while not self._stop.is_set():
            try:
                frame = q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.ingest_frame(frame, decoders=decoders)
            except Exception:
                self._errors += 1
            finally:
                q.task_done()

    def stop(self) -> None:
        self._stop.set()
        workers, self._workers = self._workers, []
        self._worker = None
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=2.0)
        for decoders in self._decoder_sets:
            for decoder in decoders:
                close = getattr(decoder, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

    def ingest_frame(self, frame: EphemeralRadioFrame, *, decoders: tuple[RadioDecoder, ...] | None = None) -> dict[str, object]:
        if not self.enabled:
            return {"accepted": False, "reason": "disabled"}
        self._frames += 1
        if self._frames % 64 == 1:
            quality = _pcm_quality(frame)
            self._audio_sampled += 1
            self._audio_duration_ms += float(quality["duration_ms"])
            if not quality["valid_pcm"]:
                self._audio_invalid += 1
            else:
                self._audio_rms_sum += float(quality["rms"])
                self._audio_silent += int(bool(quality["silent"]))
                self._audio_clipped += int(bool(quality["clipping"]))
        decoded = 0
        accepted = 0
        rejected = 0
        invalid = 0
        for decoder in (self._decoders if decoders is None else decoders):
            try:
                outputs = tuple(decoder.decode(frame))
            except Exception:
                invalid += 1
                continue
            for output in outputs[:16]:
                try:
                    kind = str(output.get("kind") or "").strip().lower()
                    payload = output.get("payload")
                    message = DecodedRadioMessage(
                        kind=kind,
                        receiver_id=frame.receiver_id,
                        provider=frame.provider,
                        physical_lineage=frame.physical_lineage,
                        frequency_hz=frame.frequency_hz,
                        mode=frame.mode,
                        observed_at=frame.observed_at,
                        payload=payload,  # type: ignore[arg-type]
                        provider_message_id=str(output.get("message_id") or "").strip() or None,
                        source_terms=frame.source_terms,
                    )
                except (TypeError, ValueError):
                    invalid += 1
                    continue
                try:
                    result = self._decoded_handler(message)
                except Exception:
                    self._errors += 1
                    continue
                decoded += 1
                if isinstance(result, Mapping) and result.get("accepted") is True:
                    accepted += 1
                else:
                    rejected += 1
        self._decoded += decoded
        self._accepted += accepted
        self._rejected += rejected
        self._invalid += invalid
        return {"accepted": True, "decoded": decoded, "invalid": invalid,
                "persisted": accepted, "rejected": rejected}

class JSONLProcessDecoder:
    """Persistent bounded JSONL decoder subprocess. No shell, no file persistence."""

    def __init__(
        self,
        command: tuple[str, ...],
        *,
        timeout_s: float = 0.5,
        max_output_chars: int = 65536,
        accepted_frequencies_hz: frozenset[int] | None = None,
        frequency_tolerance_hz: int = 100,
    ) -> None:
        if not command or not command[0]:
            raise ValueError("decoder command required")
        if timeout_s <= 0:
            raise ValueError("decoder timeout must be positive")
        self._command = tuple(command)
        self._timeout_s = float(timeout_s)
        self._max_output_chars = max(1024, int(max_output_chars))
        self._accepted_frequencies_hz = accepted_frequencies_hz
        self._frequency_tolerance_hz = max(0, int(frequency_tolerance_hz))
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str | Exception] | None = None
        self._reader: threading.Thread | None = None
        self._reader_stop = threading.Event()
        self._lock = threading.Lock()
        self.continuity_resets = 0
        self.state_evictions = 0
        self.bridge_errors = 0

    def _ensure_process(self) -> subprocess.Popen[str]:
        process = self._process
        if process is not None and process.poll() is None:
            return process
        self.close()
        process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            close_fds=True,
        )
        responses: queue.Queue[str | Exception] = queue.Queue(maxsize=1)
        self._reader_stop.clear()

        def enqueue(item: str | Exception) -> bool:
            while not self._reader_stop.is_set():
                try:
                    responses.put(item, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def read_responses() -> None:
            assert process.stdout is not None
            try:
                while True:
                    line = process.stdout.readline(self._max_output_chars + 1)
                    if not line:
                        enqueue(EOFError("decoder process closed stdout"))
                        return
                    if not enqueue(line):
                        return
            except Exception as exc:
                enqueue(exc)

        reader = threading.Thread(
            target=read_responses,
            daemon=True,
            name="radio-decoder-stdout",
        )
        self._process = process
        self._responses = responses
        self._reader = reader
        reader.start()
        return process

    def decode(self, frame: EphemeralRadioFrame) -> Iterable[Mapping[str, object]]:
        if self._accepted_frequencies_hz is not None and not any(
            abs(int(frame.frequency_hz) - frequency) <= self._frequency_tolerance_hz
            for frequency in self._accepted_frequencies_hz
        ):
            # Frequency routing happens before PCM normalization/base64/process
            # I/O. At 2.1875 MHz the NAVTEX decoder must not consume every DSC
            # audio frame merely to return an empty result.
            return ()

        from core.radio.pcm import normalize_pcm16le

        pcm = normalize_pcm16le(
            frame.payload, encoding=frame.encoding, sample_rate_hz=frame.sample_rate_hz
        )
        envelope = {
            "receiver_id": frame.receiver_id,
            "provider": frame.provider,
            "physical_lineage": frame.physical_lineage,
            "frequency_hz": frame.frequency_hz,
            "mode": frame.mode,
            "observed_at": frame.observed_at.isoformat(),
            "sample_rate_hz": pcm.sample_rate_hz,
            "encoding": pcm.encoding,
            "payload_b64": base64.b64encode(pcm.payload).decode("ascii"),
            "session_id": frame.session_id,
            "sequence": frame.sequence,
        }
        with self._lock:
            process = self._ensure_process()
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(envelope, separators=(",", ":")) + "\n")
            process.stdin.flush()
            responses = self._responses
            assert responses is not None
            try:
                response = responses.get(timeout=self._timeout_s)
            except queue.Empty as exc:
                self.close()
                raise TimeoutError("decoder response timeout") from exc
            if isinstance(response, Exception):
                self.close()
                raise response
            line = response
            if len(line) > self._max_output_chars:
                self.close()
                raise ValueError("decoder output exceeds bound")
        payload = json.loads(line)
        if isinstance(payload, Mapping):
            for key, attribute in (("continuity_resets", "continuity_resets"),
                                   ("state_evictions", "state_evictions"),
                                   ("bridge_errors", "bridge_errors")):
                count = payload.get(key)
                if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 64:
                    setattr(self, attribute, getattr(self, attribute) + count)
        messages = payload.get("messages", []) if isinstance(payload, Mapping) else []
        if not isinstance(messages, list):
            raise ValueError("decoder messages must be a list")
        return tuple(item for item in messages[:16] if isinstance(item, Mapping))

    def close(self) -> None:
        process, self._process = self._process, None
        reader, self._reader = self._reader, None
        self._reader_stop.set()
        self._responses = None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.5)
        finally:
            # Closing both pipe ends prevents descriptor accumulation after
            # decoder timeouts, including when the child has already exited.
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if reader is not None and reader is not threading.current_thread():
                reader.join(timeout=1.0)

_decoder_runtime: RadioDecoderRuntime | None = None
_decoder_runtime_lock = threading.Lock()

_NAVTEX_FREQUENCIES_HZ = frozenset({490_000, 518_000})
_DSC_FREQUENCIES_HZ = frozenset(
    # The bundled bridge is the MF/HF 100 Bd / 170 Hz decoder. VHF channel
    # 70 is 1200 Bd with a different audio shift and is intentionally not
    # advertised until a dedicated VHF decoder exists.
    {2_187_500, 4_207_500, 6_312_000, 8_414_500, 12_577_000, 16_804_500}
)


def _builtin_decoder_frequencies(command: tuple[str, ...]) -> frozenset[int] | None:
    """Frequency contract for the bundled decoders; unknown plugins stay generic."""
    joined = " ".join(command).lower()
    if "navtex_jsonl.py" in joined:
        return _NAVTEX_FREQUENCIES_HZ
    if "seacommonsdscbridge.dll" in joined:
        return _DSC_FREQUENCIES_HZ
    return None


def runtime_from_config() -> RadioDecoderRuntime:
    from core.config import config
    from core.radio.bridge import handle_decoded_radio_message

    decoders: list[RadioDecoder] = []
    if config.RADIO_DECODER_ENABLED and str(config.RADIO_DECODER_COMMANDS_JSON or "").strip():
        try:
            commands = json.loads(config.RADIO_DECODER_COMMANDS_JSON)
        except json.JSONDecodeError:
            commands = []
        if isinstance(commands, list):
            for raw in commands[:4]:
                if not isinstance(raw, list) or not raw or not all(isinstance(v, str) and v for v in raw):
                    continue
                command = tuple(raw)
                decoders.append(
                    JSONLProcessDecoder(
                        command,
                        timeout_s=config.RADIO_DECODER_TIMEOUT_S,
                        accepted_frequencies_hz=_builtin_decoder_frequencies(command),
                    )
                )
    return RadioDecoderRuntime(
        enabled=bool(config.RADIO_DECODER_ENABLED and decoders),
        decoders=decoders,
        decoded_handler=handle_decoded_radio_message,
        queue_size=config.RADIO_DECODER_QUEUE_SIZE,
        decoder_factory=(lambda: tuple(
            JSONLProcessDecoder(
                tuple(raw), timeout_s=config.RADIO_DECODER_TIMEOUT_S,
                accepted_frequencies_hz=_builtin_decoder_frequencies(tuple(raw)),
            ) for raw in commands[:4] if isinstance(raw, list) and raw
            and all(isinstance(v, str) and v for v in raw)
        )) if decoders else None,
        worker_count=3,
    )


def get_radio_decoder_runtime() -> RadioDecoderRuntime:
    global _decoder_runtime
    if _decoder_runtime is None:
        with _decoder_runtime_lock:
            if _decoder_runtime is None:
                _decoder_runtime = runtime_from_config()
    return _decoder_runtime


def submit_ephemeral_frame(frame: EphemeralRadioFrame) -> bool:
    from core.radio.listen import publish_ephemeral_audio

    listen_deliveries = publish_ephemeral_audio(frame)
    decoder_accepted = get_radio_decoder_runtime().submit_frame(frame)
    return bool(listen_deliveries or decoder_accepted)


def radio_decoder_status() -> dict[str, object]:
    return get_radio_decoder_runtime().status()


def reset_radio_decoder_runtime() -> None:
    global _decoder_runtime
    with _decoder_runtime_lock:
        runtime, _decoder_runtime = _decoder_runtime, None
    if runtime is not None:
        runtime.stop()
