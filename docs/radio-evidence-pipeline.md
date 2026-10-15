# Maritime radio evidence pipeline

SeaCommons treats MF/HF radio as a first-class source of maritime safety evidence alongside AIS, satellite observations and other verified sources. Receiving audio is **not** the same thing as detecting a DSC distress call. The pipeline distinguishes these steps rather than counting all radio activity as incidents.

## How the seven stages work

1. **Radio reception:** The number of currently connected, independent SDR receivers. The managed channel targets three copies of the relevant DSC channel where external SDR capacity allows. A disconnected receiver is not counted as active simply because it was assigned to a channel.
2. **DSC signal processing:** Ephemeral radio audio is converted into PCM and analysed for 100-baud MF/HF DSC. This counter measures processed PCM frames, **not** calls or incidents. The receiver state is `listening` when audio processing is healthy and no verified message has arrived; `degraded` means a real transport, worker or backpressure condition needs attention.
3. **Verified DSC messages:** A message must pass framing, parity and error-control checks, decoder validation and ingestion acceptance. The number excludes NAVTEX bulletins and rejected decoder messages.
4. **Persisted DSC evidence:** A verified message becomes an immutable source observation with its reception time, frequency, decoder identity and provenance. Raw audio is not retained. NAVTEX is stored independently as contextual information.
5. **Distress candidates requiring review:** Only a validated message explicitly categorised as distress enters the Maritime Safety review path. Even then it remains a candidate requiring human review, **not** a confirmed emergency and not an automatically generated rescue incident.
6. **Strong AIS correlations:** Where an actual decoded MMSI and suitable contemporaneous AIS positions agree spatially and temporally, SeaCommons can register a strong link. Identity-only matches are not presented as strong positional corroboration.
7. **Linked investigations:** A strong radio-to-AIS association may enrich an existing canonical maritime episode. Radio does not create a parallel investigation automatically.

The monitoring API provides these stages at `/api/v1/live/receivers/mesh` and in the radio source within `/api/v1/live/pipeline`. The protected operator dashboard includes the same stage overview and the operator stabilization endpoint exposes the scaling gate. Stage counters are explicitly **since the current API process started**, not all-time historical totals. Historical validated radio observations are stored in the source observation database and available through the existing authorized investigation/PLAY pathways.

## Operational interpretation

`Radio: live` indicates healthy receiver coverage. `DSC: listening` means the signal-processing chain is operating, but no verified DSC has yet been accepted; it does not indicate failure. `DSC: live` requires actual accepted structured evidence. `degraded` is reserved for actual missing coverage, absent recent audio, worker/bridge errors or recent sustained backpressure. No synthetic test signal is ever published as a real distress event.

Public receiver streaming is dependent on third-party SDR availability. External network disconnects can interrupt symbol continuity, and the application must reset its decoder state on a confirmed session or packet-sequence break rather than stitch together unrelated audio. The bounded buffers, rapid failover and published continuity diagnostics help identify these gaps without persisting private PCM.
