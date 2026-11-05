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
