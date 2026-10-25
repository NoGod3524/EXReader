# S05 simulator distribution verification

| File | Role |
| --- | --- |
| `app_bundle.py` | Reads one `.app` into a distribution manifest (Info.plist, files with SHA-256, Mach-O slices and load commands, nested code, code signature and entitlements) and returns the named checks. Pure bundle reading: no network, no simulator, no signing identity. |
| `sim_smoke.py` | Erases an iPhone or iPad simulator, proves the container is gone, installs the bundle, hashes the installed executable against the source, launches it, requires the launched process to stay alive and to be the installed program, screenshots, and erases the device again. |
| `verify.py` | Runs the bundle checks and the optional clean install smoke for one device class and writes `bundle-manifest.json`, `install-manifest.json`, `checks.json`, `simulator/simulator.json` and `result.json`. |
| `fixture.py` | CI-only: compiles the fixture app from `fixture/`, signs it ad-hoc, and proves the verifier by accepting the untouched bundle and rejecting one mutant per named check. The generated bundle is never committed and never stands in for a producer. |
| `zip_stage.py` | Authenticated artifact ZIP staging: ditto extraction on macOS, mode restoring `zipfile` fallback, app discovery, per-app identity facts. |
| `producer_source.py` | Authenticates a designated producer run, attempt, workflow, head commit and artifact bytes (artifact API digest plus a second SHA-256 of the downloaded ZIP), extracts it, records every `.app` candidate and stages the chosen bundle per device class. |
| `summary.py` | Collects the downloaded evidence and keeps tool capability, simulator capability and producer acceptance apart. A fixture or a failed producer can never become `accepted`. |

Fixtures are generated inside the Actions job only. The fixture app is an ad-hoc
signed iPhone/iPad simulator bundle with a nested dylib, a resource, a license
file and the `EXRSourceSHA` binding; the mutants are single deliberate changes to
that generated bundle.

Run locally only to read the code: every build, test, syntax check, fixture
generation, screenshot and artifact download happens in
`.github/workflows/reader-final-s05.yml`.
# Root review, accepted simulator bundle-byte scope

`codex/reader-fw-s05-root-review` starts at submitted S05 `ccef845e` and pins the
successful producer `5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a`, run40217963443 /
attempt1. Implementation `d0a3971d0ee1254b24e4f5f9bc4503ebff3844ab` passed
run40226594342/attempt1 on its first full Actions round: all six jobs, both real
producer bundle-byte/copy/install/launch checks, original15 classification
controls, new evidence-chain negatives and strict same-run authentication.
The original DS worktree is untouched; no local syntax/build/test or artifact
parsing was run. Exact evidence and limited grants are in the package contract.

The new `identity.py` authenticates the producer's exact attempt, five jobs and
per-device original ZIP pins, and S05's own same-run upstream ZIPs. `bundle_copy.py`
binds the entire `program-raw/EXReaderHost.app` ordinary-file inventory to the
original report, stages it with the observed metadata, and compares the complete
installed bytes. `restore.py` authenticates the staging tar before extraction.
The simulator PID must name the canonical installed executable path. The
summary refuses duplicate, missing or foreign-attempt records and binds both
device intakes independently. `test_chain.py` supplies small Actions-only
boundary negatives; original fixture/classification and simulator tests remain.

The original producer report did not attest file modes or symlink targets.
`original_modes_links_accepted=false` remains pending even if current extracted,
staged and installed observations agree. No chmod or resign is applied to a
producer app. A missing executable bit or install failure stays a real failure.
The binary-only/ad-hoc signature facts and no-device-signing scope remain.

The isolated workflow now triggers only its root-review branch/path; source and
producer remain separate. This evidence seal changes Markdown/JSON only. Original
mode/link fidelity, bundle signing, devices, screen readers, performance and the
complete product are outside the accepted bundle-byte/simulator-install scope.
