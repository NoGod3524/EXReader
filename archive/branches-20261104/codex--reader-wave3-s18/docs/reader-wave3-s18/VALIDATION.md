# Wave3 S18 validation record

## Execution

| item | value |
| --- | --- |
| tested source | `4af92ba023aa64b3ca6db993f2c7b9cec208e326` |
| branch | `codex/reader-wave3-s18` |
| fixed seed | `d263ce5228838ac90c0a0dc13a5193d4a7739681` |
| Actions run / attempt | `40247961052` / `1` |
| jobs | preflight `121333464221`, source strict `121333517312`, Linux `121333517342`, macOS `121333517386`, Windows `121333517333`, runtime strict `121336242302` — all completed/success |

Retained earlier failures of this package (both are my own driver defects, no
product or judge change):

| run | failure |
| --- | --- |
| `40245930197` / 1 | S14 contract JSON was prefixed by a UserWarning; S16 evidence path used `Path + str`; the runtime job exit status did not reflect the phase result |
| `40246888203` / 1 | strict read `legacy_all_equal` from the phase record instead of the annotation report |

The two failures this task took over from the reviewed foundation runner are
kept as history: `40240222437` / 1 (Linux job had no libcurl) and
`40240645276` / 1 (the shared consumer refused the SDK generator-expression
include paths). That workflow, tree and manifest were not reused or claimed.

## Artifacts of this run and attempt

| artifact | id | bytes | digest | expires |
| --- | --- | --- | --- | --- |
| reader-wave3-s18-source-40247961052-1 | 12619296639 | 2008 | sha256:0021463f2d4ff6d4a76c62fa9ca7c4ac37b7efbbb48415a69fd01e65ed0329d8 | 2027-01-24T00:09:21Z |
| reader-wave3-s18-source-summary-40247961052-1 | 12619910787 | 2130 | sha256:125af63ffa9d0f9fba4d63287e22b5ba89b58e9f3d8165ab0c27219ab3cb3198 | 2027-01-24T00:09:21Z |
| reader-wave3-s18-runtime-Linux-40247961052-1 | 12619262704 | 48679812 | sha256:ec3e5f7a57ccb19087748ed3485e1815e4b8b3db82d0f135fd9b790cb7d566de | 2027-01-24T00:09:21Z |
| reader-wave3-s18-runtime-Windows-40247961052-1 | 12619317686 | 37628080 | sha256:db0eb254fac1a402c9b5f05676e78a1c0d02bdd3ee78430c12fb8fbf689936b1 | 2027-01-24T00:09:21Z |
| reader-wave3-s18-runtime-macOS-40247961052-1 | 12620225857 | 41811896 | sha256:6ce94720fcc453b1a46df0ca0f0970114d0dd1c62c14b182fcf5cf167e59ec1a | 2027-01-24T00:09:21Z |
| reader-wave3-s18-runtime-summary-40247961052-1 | 12619537636 | 1206 | sha256:b3f7a6ac7439d5b92cd47aa948ffb3852a4b8bfcd08cc81ea0a1cc6a8e344d2a | 2027-01-24T00:09:21Z |

The strict job authenticated every ZIP byte, member, program hash and report of
these artifacts against this run and attempt; it then rejected 15 real byte
mutations on each platform (45/45). Linux and Windows and macOS report the
identical S17 named checks, and the legacy annotation JSONL/Markdown bytes are
identical on all three platforms.

## Per-platform results

| item | Linux | Windows | macOS |
| --- | --- | --- | --- |
| phases passed | 11/11 | 11/11 | 11/11 |
| S14 named cases | 60 | 61 | 60 |
| S14 existing-target controls | 4 | 4 | 4 |
| S14 negative contracts | 42 | 42 | 42 |
| C06 annotation checks | 199 | 199 | 199 |
| C06 certified Mac heads / NULL | 3 / 1 | 3 / 1 | 3 / 1 |
| S16 original baseline/default/raw | 149/149/149 | 149/149/149 | 149/149/149 |
| S16 raw / default | 162 / 21 | 162 / 21 | 162 / 21 |
| S16 programs / archives | 9 / 3 | 9 / 3 | 9 / 3 |
| S15 checks / frozen 3.40 / targets | 44 / 6 / 16 | 44 / 6 / 16 | 44 / 6 / 16 |
| S17 legacy / raw / mixed refusals | 22 / 20 / 5 | 22 / 20 / 5 | 22 / 20 / 5 |
| programs / files in artifact | 24 / 189 | 24 / 189 | 24 / 189 |
| strict mutations rejected | 15/15 | 15/15 | 15/15 |
