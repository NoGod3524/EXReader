# D03 final handoff — blocked acceptance, authenticated evidence

- Branch: `codex/reader-final-d03`
- Tested harness: `81a67f582ddfe8906b64e6eef4e7969127415ba8`
- Target: `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e`; SDK: `edddc463c06ed5731195cdb8f06b2df6dff7699e`
- Run/attempt: `40218375669/1`; producer `121244359634` success; verifier `121247583314` failure at audit-completeness refusal after authentication and 104 negative mutations passed.
- Primary artifact: `12609036554`, 35,146,853 bytes; SHA-256 `a60100c94b4033f236536efb2274cfd4fd38727e51e9fc63e31bd970187d4496`; expiry `2026-11-08T18:03:36Z`; raw ZIP rehashed inside Actions.
- `evidence_authenticated=true`, `audit_completed=false`, `keyboard_accepted=false`, `contrast_accepted=false`, `screen_reader_accepted=false`, `accepted=false`.
- Raw ON 27/27 and OFF 24/25 counts are **not trusted scope grants**. Modal focus check was too weak: actual focus remained outside Reading records in all eight configurations. OFF Escape after bookmark save timed out in all four. Directory focused scroll pane is unnamed. 2× coordinate/crop attribution is indeterminate.
- Three failed rounds retained; no further retry. No production edits. This seal changes documentation only; exact docs-only HEAD is supplied with the final remote delivery.
- Full findings/reproduction/identity/limitations: [REPORT.md](docs/reader-final-d03/REPORT.md).
- Machine adjudication: [validation.json](docs/reader-final-d03/validation.json), mirrored under `docs/validation/reader-final-d03.json`.
