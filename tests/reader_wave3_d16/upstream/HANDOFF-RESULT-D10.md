# D10 final handoff — failed full audit, authenticated evidence

- Branch: `codex/reader-dot-d10`; implementation base `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- Final tested harness: `d2e1b55c9cd4ded4201cbb4d1351bc490ef644df`; tested tree `040bfcd49201ba25420ee720e6a2dc8146e7c154`.
- Target macOS: `15dab6b2270dc296ed6239db67ced2e22d255e65`; iPhone/iPad: `5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a`.
- SDK: `edddc463c06ed5731195cdb8f06b2df6dff7699e` /3.41.0; page-theme OFF; actual compiler/project review macros absent.
- Final [run40229896420/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/40229896420): **failure**. Prior-evidence job121279165979 success; macOS121279248047 success; iPhone121279248017 failure; iPad121279248013 success; strict verifier121290384110 failure solely at incomplete real audit after authenticating evidence.
- Documentation seal: this docs-only `[skip ci]` commit; its exact full SHA is returned in parent handoff/status. Parent is final tested harness; no fourth CI and no harness/product edits after final tested source.

## Scope and outcome
Mac6/6 selected cases/64PNG; iPhone8/10/139PNG; iPad10/10/136PNG. Named cases/configuration split, original raw values and all conservative findings in `docs/reader-dot-wave2/d10/validation.json`; full trees/PNGs/xcresults in original artifacts. Mac/light-dark and iPad/medium-AXXXL×light-dark journeys complete. iPhone normal light/dark complete; original large regression+all shelf cases pass, but both NEW large-reader journeys fail owned driver line64. Full audit/AX/Dynamic Type/product acceptance=false.

Native Menu wrapper AND trigger report raw isHittable=false while measured native center tap opens popup→records in iPhone normal2/iPad4 configurations; not AX semantics acceptance. Stale return helper fixed. Recorder now stores genuine offscreen tree/window and null hit-test before failure; primary XCTest error survives teardown.

Remaining iPhone driver gap:12 full-swipes can overshoot/oscillate; final unconditional `.isHittable` asks activation point for font-decrease outside viewport. Retained frames x=-119 or-164,y532,w100.5,h77.5 versus viewport x0,y532,w375,h77.5. Next unexecuted root fix: final geometry precondition and bounded measured smaller native scroll deltas; independently complete missing large dialogs/More/records/settings/return. No product failure inferred; do not replace failed scope with pending or green. Exact evidence `final-iphone-driver-gap.json`.

## Authenticated final original ZIPs
All rehashed in Actions verifier121290384110;46 negatives rejected; exact source/run/attempt/jobs/expiry/unique IDs, file manifest, actual exe/plist and no-review config verified.

| Target / artifact ID | Bytes | SHA-256 | Expiry UTC |
|---|---:|---|---|
| macOS12612821233 |22235435|078e5407bf2912798e8551582ab26e1d413e32eae8c5734af72237f7bb919e52|2026-11-24T20:29:47Z|
| iPhone12613856654 |271519328|742e8af853e21afe6d207f6c3886a82d3ac5062e40a2e59e1b0612f4835f6aa3|2026-11-24T20:47:29Z|
| iPad12613438587 |84160891|d404a51ddba859e2c04be0b468a4c045fee91bb6b289ce1b5da2348c034c5e2f|2026-11-24T21:02:21Z|

Actual executable SHA-256:
- macOS `ec66a4dc477c53e15600b0453157bea06eeafdc7612f6f852d9919682102d960`
- iPhone `1178340d9e43d5f15379c587aa9ac517ceb7fe28e4dc2f09d974cdf8186044c5`
- iPad `a76a2873ea8d5d02d05c7340d2297a9eb0325755e421c06c882d5402ca397e5f`

Final summary12614246023:12780bytes/API digest f28dafae736953dbc5fa68bf8bdefb5839c2648a1c71a561793335db4393ee67, expiry2026-11-24T21:03:14Z; metadata-only, not downstream rehashed. Prior summary12612134636 similarly metadata-only. Full IDs/metadata `artifact-metadata.json`.

## Retained failures / root integration
- D04 final `207d86185a9ddb61bcb276ecb926c63b1a1d3989`: remains failed; never retrospectively green.
- D10 round1 `bdafad551f9f574d329e592d57cc4b095fccb51e` /40224903723/1: owned unsupported snapshot.debugDescription compile error, zero UI cases. Original ZIPs/programs authenticated;28 negatives; `round1.json`.
- D10 round2 `48784fc302340904a4cadc1fdffb424a656c1e9f` /40226413800/1: Mac+iPad passed, iPhone readiness180s timed out before app/UI. Final prior-review authenticated all3 ZIPs, Mac+iPad programs; missing iPhone program=false,42 negatives; `round2.json`.
- Three complete iterations exhausted. No PR/merge/main/tag/release/credentials/Codex/children/local builds/tests/artifact parsing. Only owned new paths touched.

Root entrypoints: `.github/workflows/reader-dot-d10.yml`, `tests/reader_dot_wave2/d10/`, this handoff and `docs/reader-dot-wave2/d10/`. Evidence-only integration, not blanket Apple acceptance. VoiceOver/physical devices/signing/full AX/contrast/keyboard focus/Mac large-font/full settings and visual clipping remain unverified. Installed-library hashes are producer reports; ZIP mode/link provenance and complete signed bundles are not established.
