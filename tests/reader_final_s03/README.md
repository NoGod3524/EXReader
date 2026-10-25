# S03 macOS .app candidate package

Adds the `.app` candidate manifest, relocation and offline native smoke test for
the **actual** macOS producer. Nothing here builds or installs by itself: the
workflow drives the producer's own tools inside GitHub Actions, and these modules
decide whether the resulting bytes prove the claim.

| File | Role |
| --- | --- |
| `spec.py` | Pinned identities (producer / SDK / start), bundle layout, candidate table, and every pure decision. |
| `bundle.py` | Reads one assembled `.app`: Info.plist, `lipo` arch, LC_BUILD_VERSION, `otool -L` closure, single dynamic SDK, resource and licence manifests, resource provenance, producer `build.json` cross-check, product-library single source (re-runs the producer's `check_apple_product.py` and counts the seven raw providers again from `nm` and the link map), plus the G09 private-path/secret scan. |
| `identity.py` | Producer HEAD/tree, SDK-bearing path objects, blob-by-blob equality between the extracted SDK source and `git ls-tree -r edddc463`, installed stage identity, ARM64 runner. |
| `smoke.py` | Runs the producer's **original** `tools/check_apple_host.py --device macos` as a baseline, `ditto`-relocates the bundle into `最终 阅读器 候选 ünïcode 空格/EXReader.app`, proves a `sandbox-exec` network-denied envelope with a control and a denied probe, then runs the same original smoke test offline (open) and again with the previous run's state present (reopen); records codesign/spctl/stapler/quarantine facts. |
| `aggregate.py` | Combines one run's recorded verdicts into `result.json`, `validation.json` and `artifact-index.json`; re-derives everything from the uploaded evidence alone. |
| `guard.py` | Cheap cloud guard: writes only inside this package, pinned commits, SDK tree equality, producer tool capability, workflow trigger scope, validation state. |
| `check_spec.py` | Feeds every decision a good input plus one single mutation and requires a named rejection. |

Accepted per candidate means: closed dependency closure with exactly one dynamic
SDK identity (the producer ships it under every versioned name the linker asks
for, so aliases are accepted only when their `LC_ID_DYLIB` and exported symbols
are the same library and no copy exists outside `Contents/Frameworks`), no static
archive, Info.plist/arch/minos/SDK-source match, resources and
licence originals matching the installed tree, producer `build.json` equal to the
recomputed hashes, byte-identical relocation into a space+Unicode path, a proven
network-denied envelope, and open+reopen reports with `check_count >= 20` from the
producer's own self-test.

Out of scope and reported as pending: signing identity, notarization, Gatekeeper,
publication, physical devices, screen reading, performance budgets and the final
unified source integration. The bundle is ad-hoc signed by the producer's tool.

Re-derive a finished run without rebuilding:

```bash
python3 tests/reader_final_s03/aggregate.py --evidence <evidence-dir> --output <out-dir> \
  --verifier-sha <tested-sha> --producer-sha 15dab6b2270dc296ed6239db67ced2e22d255e65 \
  --sdk-sha edddc463c06ed5731195cdb8f06b2df6dff7699e
```
