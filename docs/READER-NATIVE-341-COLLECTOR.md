# Fixed-source native workflow upper collector — preparation

Status: **Actions syntax and 67 synthetic refusal cases passed; native collection pending**.
Starting root source is `5e8b132626cfe7540f675285787d24bf488857a8`.
Only this collector, its synthetic refusal tests, its new workflow and this
document change. Callers, production, original collectors and leaf judges stay
unchanged. The raw-selector v3 prototype is not adopted.

## Required complete leaves

The input supplies one full common source SHA and one explicit `{run_id,attempt}`
per leaf. Platform fragments, implicit latest attempts, reused run IDs, missing
required keys and alternate artifact selections are rejected. The two Windows
slots alone may share the identical whole run and attempt; no third scope or
different attempt may reuse that run.

| Required key | Original complete workflow/scope |
| --- | --- |
| `composition` | SDK3.41, all 27 installed configs, original G1 before/after relocation, three platforms, strict41 |
| `gtk41` | Full original producer, settings41, native navigation29/F2130, record16+12 and all retained GTK scopes |
| `android130` | Original120+theme10 on API34 default x86_64, original APK/native/PNG/kill checks |
| `windows_full_f3` | Full F3 and every retained original Windows suite — contract pending |
| `windows_atomic13` | Root's actual atomic-commit13 — contract pending |
| `apple_records` | Complete records workflow, all macOS/iPhone/iPad producers and strict |
| `apple_navigation` | Complete navigation workflow, all three UI platforms and strict |
| `apple_search` | Complete search workflow, all three UI platforms and strict |
| `apple_shelf` | Complete shelf workflow and its actual validation artifact |
| `apple_mapping` | Complete six-job/six-artifact mapping workflow and original per-artifact collectors |
| `apple_wp13` | Complete eight-job WP13 workflow and original gate-reviewed validation |
| `apple_page_theme` | Complete eight-job SDK3.41 explicit page-theme workflow, including native ON37/OFF10, mixed-version5, three UI platforms and initialization/publication2 |

The two Windows slots remain required `None` contracts. They always stay
`pending` and block the foundation's `accepted` flag, even if another internal
status were accidentally populated. The generic schema refuses unreviewed
Windows summaries. Final Windows workflow/job/artifact/schema fields must be
reviewed and implemented before acceptance; removing those requirements is not
an option.

## Evidence and attempt authentication

The collector checks each run's exact workflow, head source, explicitly selected
**latest** attempt, completion and success. It fetches that entire attempt's
jobs, rejects omitted/duplicate jobs and hidden failed steps, and checks required
common-source guards. Only the explicitly unrequested GTK diagnostic job may
be skipped as a job.

Every required API artifact must have a unique identity, nonzero bounded bytes,
real SHA-256 digest and live expiry, and belong to that run/source. Creation
times must fall inside the actual current-attempt job window. A strict summary
must have been created during its actual strict job, with every upstream
artifact already present before that job started. This also protects WP13's
legacy artifact names, which contain no attempt suffix. No older attempt is
used to fill a missing current platform or artifact.

For workflows with a real strict summary the upper layer downloads and
authenticates that small original ZIP via existing `final.Bundle`, validates
the exact original scope and mandatory counts, and compares every declared
upstream artifact with live API IDs/bytes/digests/expiry. It rechecks complete
upstream job identities and full metadata, rather than downloading all large
SDK/program/UI ZIPs again. GTK's actual 16-reopen/12-SIGKILL owner scope and new
sensitive draw remain mandatory. Android's nine original report groups must
still total 130.

WP13's actual schema has no copied API artifact manifest. The upper layer keeps
that fact: it checks its genuine gate-reviewed strict result, all eight current
jobs and the complete expected API artifact set, and marks the upstream manifest
as absent instead of manufacturing one.

Mapping has **no strict-summary artifact**. It reuses the existing
`apple.check_artifacts` and all six `apple.verify_bundle(mapping)` collectors,
including their original native/UI/file/database checks. These necessary raw
ZIP authentications remain; the collector never labels them a pre-existing
mapping strict summary. The old Apple branch-name restriction is replaced only
by exact fixed source/workflow/current-attempt checks; original artifact and
mapping data judges are reused.

## Required product facts and historical evidence

Apple real record compatibility (18 + 19×2 + Java20), Android→Apple and
Apple→Android are separate required product conditions. Their reviewed
same-common-source adapters are not configured here, so they remain explicitly
pending. They cannot replace any of the seven Apple native-UI workflows.
Independently sealed `9ce…` / `b93…` deliveries may be listed as declared history;
history never counts for the current source and is never accepted by this
collector.

The upper result's scope is the declared native UI foundation only. Upgrade,
bidirectional interoperability, physical devices, performance and complete
product acceptance stay `false`, including when every foundation leaf passes.

## Input shape

Use the same final SHA for workflow dispatch, checkout, `source_sha` input and
the table's `source_sha`. Supply all twelve keys; use `null` for genuinely
pending work, not an older run. No default old evidence is preloaded.

```json
{
  "source_sha": "<FULL_FINAL_COMMON_SHA>",
  "runs": {
    "composition": null, "gtk41": null, "android130": null,
    "windows_full_f3": null, "windows_atomic13": null,
    "apple_records": null, "apple_navigation": null, "apple_search": null,
    "apple_shelf": null, "apple_mapping": null, "apple_wp13": null,
    "apple_page_theme": null
  },
  "product_conditions": {
    "apple_record_compatibility": null,
    "android_to_apple": null, "apple_to_android": null
  },
  "history": []
}
```

Replace each completed null with `{ "run_id": 123, "attempt": 1 }` using its
actual complete run. The already accepted composition source `b5e49d17` /
`40186697513` remains owned by that source; it cannot fill another final SHA.

## Final root configuration and deferred validation

1. Update `aggregate_native.BASE` to the reviewed final production boundary;
   current pin is `5e8b1326`. The source guard requires unchanged production from
   that boundary, exact SDK `eddd…`, unchanged schema1 and actual MAX2 header.
2. Pin both real Windows contracts and their exact strict summary validators.
   If full-F3 and atomic13 genuinely share one complete workflow/run, explicitly
   use the reviewed two-slot identical-run/attempt exception; all other duplicate-run rejection remains.
3. Confirm the final callers preserve the listed workflow/job/artifact names,
   actual source-guard step names and original strict schemas. Any required
   identity adaptation must be explicit; no required scope may be dropped.
4. Configure separate product-fact adapters only after reviewing actual common
   source record/peer evidence. History never replaces these conditions.
5. Collect only after all required complete same-source leaves finish. The
   protocol suite now contains 67 negative controls for missing/failed/foreign/
   duplicate/old-attempt/wrong-scope evidence, including absent theme-native or
   initialization/publication reports. These are synthetic collector checks.

## Executed protocol evidence

Source `e3e5cc6ddf7f0b219eae79a61fa13a3122f2029d`,
[run 40193435537](https://github.com/NoGod3524/EXReader/actions/runs/40193435537)
attempt 1: protocol job success. Actions compiled both Python sources and
reported `63 actual rejections; synthetic fixtures only`. No local checks ran.
The collection job was skipped as intended; no native leaf or product was
accepted by this run.

Follow-up source `b1b1639639cffa6a7decce51a1f54027802429a3`,
[run 40193923047](https://github.com/NoGod3524/EXReader/actions/runs/40193923047)
attempt 1: protocol job success, `67 actual rejections`. The added positive
fixture models all eight Apple theme jobs and eight artifacts; its four negative
controls reject the old seven-job set, missing fast-import artifact, skipped
source guard and previous-attempt fast-import artifact. Native collection stayed
skipped. The 63-case run above remains the earlier source's evidence.

Push runs the cheap protocol job. Manual dispatch defaults to `mode=protocol`;
only explicit `mode=collect` runs the authenticated collection after protocol
passes. No long producer workflow is launched by this collector.
