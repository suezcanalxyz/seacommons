# SeaCommons Radio — multichannel MF/HF/VHF audit
**Audit date:** 18 November 2026; **audited from:** running Oracle VM `instance-20260828-1159` and public read-only SDR status endpoints.
**Result:** source capability and pipeline audit **only**. No third-party radio audio stream was opened, no live frequencies were retuned, and no production service or root-owned configuration was changed.

## Live snapshot (single point in time)
- Receiver catalog: **421 catalogued**, **315 reachable by HTTP**, **8 eligible**, **405 review_required**. HTTP success must not be interpreted as available SDR stream, RF signal or permission.
- Active receiver sockets: **3**, all tuned to **2,187,500 Hz USB** at time sampled: `mallorca_hf_monitor`, `cassine_hf_monitor`, `heimiswil_hf_monitor`. These can change with failover.
- Decoder: enabled, **2 decoder types**, 3 workers; **35,241,339** lifetime audio frames, **132 decoded/persisted DSC**, **0 first-party NAVTEX**.
- Decoder recent **30s**: 1,750 frames, 0 dropped/invalid/errors; queues [0,0,0]. The lifetime 25,114 continuity resets (mostly sessions) require per-station recent timing before conclusions; a lifetime count alone is not evidence of current breakage.
- Pipeline: **0 verified distress candidates**, **0 strong AIS correlations**. Decoded DSC is **not automatically distress**.
- VM worktree is **dirty**, backend much older than GitHub main; `/etc/seacommons.env` and `/etc/seacommons-radio-receivers.json` are root-managed. Do not reset/pull/override service to deploy this audit.
- External NAVTEX published feed for NAVAREA III via LIVE is a **secondary publication**, distinct from local RF NAVTEX reception.

## Channel support matrix (international assignments; not proof of signal coverage)

| Channel | Nominal RF frequency | Receiver range | Decoder capability today | Live RF acquisition today | Assessment |
|---|---:|---|---|---|---|
| MF DSC | 2187.5 kHz | Most curated KiwiSDR nominally 0–30 MHz | Bundled MF/HF DSC decoder | **yes, 3 sessions** | only monitored band currently |
| HF DSC | 4207.5 kHz | KiwiSDR nominally in range | Bundled MF/HF decoder accepts | **no** | eligible for separate independent tuning after validation |
| HF DSC | 6312.0 kHz | ditto | accepts | **no** | candidate |
| HF DSC | 8414.5 kHz | ditto | accepts | **no** | high-value candidate |
| HF DSC | 12577.0 kHz | ditto | accepts | **no** | candidate / daytime propagation |
| HF DSC | 16804.5 kHz | ditto | accepts | **no** | candidate / propagation-dependent |
| NAVTEX | 518.0 kHz | Kiwi SDR nominally in range; antenna/groundwave unverified | Bundled NAVTEX decoder accepts 518 kHz | **no** | needs dedicated receiver and evidence |
| NAVTEX | 490.0 kHz | ditto | accepts | **no** | national/local messages |
| NAVTEX HF | 4209.5 kHz | Kiwi nominally in range | **not in bundled NAVTEX frequency allowlist** | **no** | decoder routing + tuning validation required |
| VHF DSC Ch70 | 156.525 MHz | KiwiSDR 0–30 MHz **cannot tune**; SDR needs dedicated VHF profile | **not supported**, VHF DSC waveform differs (1200 baud) | **no** | dedicated VHF SDR + decoder + nearby geographic station |
| VHF Ch16 voice | 156.800 MHz | dedicated VHF SDR required | voice classification/transcription **not** GMDSS DSC decoder | **no** | separate lawful listening policy, no distress auto-classification |
| AIS 1/2 | 161.975 / 162.025 MHz | separate terrestrial VHF AIS receiver | separate AIS ingestion stack | not part of radio decoder mesh | never count AIS feed as GMDSS DSC receiver |

**Engineering nuance:** `core.radio.dsc_tuning.receiver_carrier_hz` offsets a USB MF/HF DSC receiver dial 1700 Hz below the nominal frequency to place the AFSK mark/space around 1615/1785 Hz; use this helper for all six channels, not a simple tune-to-label assumption. `core.radio.decoder_runtime._DSC_FREQUENCIES_HZ` contains all six frequencies, whereas `_NAVTEX_FREQUENCIES_HZ` contains only 490 and 518 kHz. Multi-channel failover is implemented through `ChannelTarget`, but the fallback pool defaults to `ChannelTarget('monitor',2187500,'usb')` when no explicit alternative targets exist.

## Passive KiwiSDR /status validation (never tuned a stream)
The public /status endpoints reported these 0–30 MHz frequency bands and free slots *at audit time*. They do **not** establish actual signal quality, multi-channel concurrency or automatic access rights.

| Site | Endpoint identity | Reported users | Nominal supported marine HF+MF channels | Deployment recommendation |
|---|---|---:|---|---|
| Cagliari, Italy | `sergiocorda.synology.me:28073` | 2/8, ext_api=4 | 6 DSC + 490/518 NAVTEX | priority for 8414.5 HF DSC or NAVTEX 518 controlled proof |
| Thessaloniki, Greece | `elektrongr.ddns.net:8073` | 1/4, ext_api not published | same nominal range | priority validation for eastern MF/HF, confirm rights |
| Zakynthos, Greece | `sv8rv.dyndns.org:8073` | 6/8, ext_api=8 | same nominal range | retain existing MF slot / conditional HF |
| Mallorca, Spain | `37.10.74.235:8073` | 4/8, ext_api=4 | same nominal range | western sector once audio validated |
| Barcelona EA3HRU, Spain | `sdrbcn.duckdns.org:8073` | 3/4, ext_api not published | same nominal range | one receiver, alternative hostname is duplicate; permission gate |
| Cassine, Italy | `kiwisdr.briata.org:8073` | 3/8, ext_api=4 | same nominal range | inland supplemental HF only |
| Heimiswil, Switzerland | `hb9cwk.internet-box.ch:8073` | 4/8, ext_api=7 | same nominal range | remote HF diagnostic, not Mediterranean coastal coverage |
| Catania OpenWebRX | `arascatania.ns0.it:8073` | HTTP online, 0 published profiles | **not verified** | do not assume 2187.5 support |

Other audited OpenWebRX endpoints in Mallorca (`sdr.alaro.ovh`) and Barcelona (`5.154.110.148:8073`) publish only VHF/UHF/aviation/ADSB/satellite profiles; **no 2187.5 kHz**. Valencia EA5RQ publishes `status=private` and must not be activated.

### Key failures / risks
1. **Concentration:** three slots on one 2187.5 channel, zero simultaneous other RF channels. Broad hardware tuning does not change the currently monitored band.
2. **NAVTEX category gap:** external NAVTEX LIVE feed operates independently; decoder processes no direct NAVTEX RF audio (`navtex_accepted=0`), while 4209.5 kHz is not even in its default accepted-frequency list.
3. **Regional coverage:** inland European HF receivers should not be presented as localized Mediterranean coastal monitoring. Public map currently has regional filter for curated Mediterranean stations; RF footprint cannot be inferred from coordinate alone.
4. **VHF Ch70:** requires purpose-built 156.525 MHz input and a separate VHF decoder; blindly tuning a KiwiSDR or reusing 100 baud MF/HF AFSK bridge is technically wrong.
5. **Provenance and slots:** repeated addresses can be same physical receiver; operator permissions and slot limits must be checked. No unapproved, continuous third-party client sockets.
6. **Runtime constraints:** root-managed service configuration and dirty checkout prohibit blind main-to-Oracle reset/deployment; channel scheduling requires staged rollout and rollback.
7. **Safety:** no automatic distress alert or geolocation claim based solely on secondary text, raw radio data, AIS proximity or unverified decoded frames.

## Recommended staged sequence
- **P0:** add per-channel read-only observability to API/LIVE: channel target, active receivers, last real PCM, decode count & age, signal continuity, permission state and coverage provenance. Show zero/unknown honestly.
- **P1:** test one consented coastal SDR at **8414.5 kHz USB** and another at **518 kHz NAVTEX**, on separate receiver lineages, with short supervised PCM tests; include 2187.5 existing sessions without disrupting them. Confirm robust repeated true decodes before enabling.
- **P2:** add at least 4207.5 and 6312 kHz DSC when resources and independent receivers permit; broaden 12577 and 16804 only if measured propagation/utility justifies persistent slots.
- **P3:** add 490 kHz national NAVTEX and 4209.5 kHz decoder routing after reception/timing proof.
- **P4:** independent terrestrial VHF Ch70 decoder/receiver close to coastline; Ch16 voice only as separate appropriately governed capability, not an auto-generated distress report.
- **P5:** expand coverage south of Mediterranean via locally hosted, explicitly consenting SDR receivers (Tunisia/Libya/Egypt); do not invent stations.
- Dynamically scale within CPU/PCM queues/network/operator slots; avoid arbitrary blanket receiver cap but equally avoid unjustified saturation.

## Validation performed
- Live Oracle status & decoder pipeline sampled; passive HTTP GET /status or /status.json on 8 geographically relevant remote SDRs; no remote SDR sockets opened.
- Python tests run on current VM checkout: `tests/test_dsc_decoder.py`, `tests/test_navtex_parser.py`, `tests/test_radio_decoder_runtime.py`, `tests/test_radio_failover.py`: **36 passed**, one optional PySocks dependency warning.
- Official frequency references: ITU and USCG/FCC https://www.law.cornell.edu/cfr/text/47/80.1077 , https://www.navcen.uscg.gov/international-vhf-marine-radio-channels-freq ; IMO NAVTEX manual https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/Documents%20relevant%20to%20GMDSS/MSC.1-Circ.1403-Rev.2.pdf
- **No production RF change, no added listening stream, no new verified channel coverage.**
