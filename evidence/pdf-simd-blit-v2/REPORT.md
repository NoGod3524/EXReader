# PDF SIMD rectangle spans

The change is confined to the rectangle span kernel. Normal RGBA spans use SSE2 or NEON, with scalar handling for translucent destinations and unsupported CPUs. Masked spans read the existing clip row.

A is main at `98b029bb4`. B is the same Release configuration with the SIMD kernel. One session alternated A/B for every fixture and width over 3 pairs. Each DLL had one warmup round and 5 timed rounds per capture. Each capture passed the 15% pre-run CPU gate. AVIF was disabled for both DLLs.

| Fixture | Width (px) | A p50 (ms) | B p50 (ms) | B vs. A | B p95 (ms) | A / B p50 spread | B target (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pptx-20 | 600 | 1.584 | 1.502 | -5.2% | 2.102 | 2.1% / 2.2% | 1.6 pass |
| pptx-20 | 1200 | 2.644 | 2.618 | -1.0% | 3.341 | 2.3% / 6.0% | 2.9 pass |
| pptx-20 | 2400 | 8.416 | 8.368 | -0.6% | 9.533 | 1.4% / 4.0% | — |
| deck | 600 | 17.169 | 17.112 | -0.3% | 20.136 | 1.8% / 3.4% | 20 pass |
| deck | 1200 | 37.400 | 37.173 | -0.6% | 47.321 | 0.4% / 2.2% | 52 pass |
| word-5 | 600 | 2.517 | 2.508 | -0.4% | 3.210 | 1.5% / 0.9% | 2.6 pass |
| word-5 | 1200 | 7.115 | 7.165 | +0.7% | 7.967 | 5.7% / 2.9% | 7.3 pass |

Each p50 and p95 is the median across captures. Spread is (max − min) / min over capture p50s. Pre-run CPU ranged from 5.14% to 14.73%. Peak during-capture CPU was 38.16% on word-5 at 1200 px (A, pair 1).

PPTX at 1200 px first-open p50 was 0.339 ms for A and 0.362 ms for B. First-open samples time the first document open in each fresh capture process.

[A/B summary](ab.json) · [Per-page samples](raw-renders.json.gz) · [Build provenance](build.json)

## Pixel and test results

Compared 111,897,000 active RGBA pixels. 0 differed. Maximum channel delta 0. RMSE 0. [Per-page pixel evidence](pixels.json)

CTest passed 586/586, with 0 failures and 0 skips. [CTest evidence](ctest.json)

The forced scalar build passed 168,190 vector checks. The NEON path was untested locally. [Scalar evidence](scalar.json)

## Render cost at 1200 px

Exclusive wall time per output pixel from separate instrumented builds. The residual includes uninstrumented work and timer overhead.

| Path (ns/px) | PPTX A | PPTX B | Deck A | Deck B |
| --- | ---: | ---: | ---: | ---: |
| Opaque rectangle spans | 0.7038 | 0.7205 | 1.0685 | 1.0356 |
| Alpha/edge rectangle spans | 0.0035 | 0.0013 | 0.0745 | 0.0661 |
| Masked rectangle spans | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Other rectangle spans | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Vector fill outside rectangle spans | 1.3238 | 1.2773 | 35.1015 | 35.7225 |
| Group commit | 0.5186 | 0.4652 | 0.6241 | 0.8101 |
| Image paint | 0.0000 | 0.0000 | 8.7655 | 8.9253 |
| Sampled paint | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Canvas creation | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Group begin | 0.0341 | 0.0311 | 0.0234 | 0.0252 |
| Group end outside nested timers | 0.0041 | 0.0040 | 0.0054 | 0.0072 |
| Residual | 1.4095 | 1.3291 | 10.9748 | 11.1130 |
| Total | 3.9974 | 3.8285 | 56.6378 | 57.7051 |

[PPTX profile](profile.json) · [Deck profile](profile-deck.json)

## Hot-cache span benchmark

| Span | A p50 (ns/px) | B p50 (ns/px) | A / B |
| --- | ---: | ---: | ---: |
| Opaque color | 0.0278 | 0.0672 | 0.41× |
| Alpha 128 over opaque | 0.9640 | 0.2176 | 4.43× |
| Alpha 128 with clip 128 | 1.6403 | 0.2577 | 6.36× |

[Alternating kernel samples](kernels.json)

[Reproduction script](reproduce.ps1)
