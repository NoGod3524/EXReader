# Wave3 S18 plan: joint install acceptance

## Scope

Take over the unfinished five-package shared-install acceptance of
`tests/reader_production_foundation` (runs 40240222437 and 40240645276 both
failed: the Linux job missed libcurl, then all three platforms were stopped by
the composition consumer rejecting the SDK's generator-expression include
paths). This wave replaces that runner with its own package; the original
workflow, tree and manifest stay untouched and are not claimed.

## Owned paths

- `tests/reader_wave3_s18/` (guard, runtime, strict, consumer, README)
- `.github/workflows/reader-wave3-s18.yml`
- `docs/reader-wave3-s18/`
- `HANDOFF-RESULT-S18.md`

Everything else must be byte-identical to the seed `d263ce52`.

## Fixed inputs

| role | commit |
| --- | --- |
| seed | `d263ce5228838ac90c0a0dc13a5193d4a7739681` |
| approved SDK | `edddc463c06ed5731195cdb8f06b2df6dff7699e` (3.41.0) |
| frozen SDK | `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0) |
| legacy start reused by C06/S14/S16/S17 | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` |
| fixed legacy importer | `9c7e276f13f42cb61a32507c36d1c22c4489bd01` |
| certified Mac records | artifact 12600789926 of run 40196978163 |

## Platform transport

Linux and Windows keep the transports their own acceptance used (libcurl and
WinHTTP). On Apple the joint install selects the documented
`EXR_WEBDAV_APPLE_URLSESSION` Foundation transport, because the fixture CA is
trusted through the system keychain there.

## Non-claims

No host wiring, no product DSO, no adopted BASE, no PR, tag, Release or default
branch change. The raw 0.2.0 family remains an explicit candidate.
