# Core SDK format adoption

The core team worktree adopts the two SDK implementation files from
`9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09` exactly. The candidate has one parent,
`edddc463c06ed5731195cdb8f06b2df6dff7699e`. Its source review is separately
recorded by `4a64ad917fa030b5af7e4f190c1b3394556ac5d4` at
`docs/sdk-341-format-adoption/PLAN.md` and `candidate.json`.

| Identity | Value |
| --- | --- |
| Isolated candidate whole SDK tree | `dd5f4fa912bcaab483524a76988515c731f22702` |
| Isolated candidate src tree | `001bd8d0baa49ecde6fae82d799bafd0b007030f` |
| `src/rtf.c` before | `6c000ebebfcbd6a8c9460df4b8b279d3203a25bd` |
| `src/rtf.c` adopted | `5475935199f9a0e0fbbdd17a3a74f2ef3b2952d9` |
| `src/cbz.c` before | `b30803adb79a0a4c2e66320a749dee14f2bb52de` |
| `src/cbz.c` adopted | `8be705007cec11d4f586d0b87b2a001ea87b4de2` |

Git review found both core worktree files at the recorded pre-adoption blobs.
Restoring only those paths produces the candidate blobs with 65 additions and
9 deletions; there is no remaining difference against the candidate for those
paths. The combined team commit has its own whole tree and must not be described
as the isolated candidate whole SDK tree.

RTF now accepts root-close NUL/whitespace padding, bounded Word theme font
numbers and signed reserved list IDs. CBZ permits one leading slash during
validation/classification, keeps the stored ZIP member name as its page identity,
and refuses normalized-name collisions. No parser rewrite is included.

## Host integration

This repository directly contains the SDK; the SDK is not a missing submodule.
The existing `tools/layers.json` assigns `rtf.c` to `formats` and `cbz.c` to `pdf`.
`cmake/modules.cmake` already builds these layers and their installed component
targets, so the two implementation files require no additional API or build
entry. `src/formats.c` calls `exr_rtf`; CBZ continues through its existing
`exr_cbz_open_owned`, `exr_cbz_open_file` and `exr_cbz_open_source` entry points.
The optional PDF component remains required for CBZ in the existing layer model.

Any producer using a separate SDK checkout must pin the candidate commit above;
changing only this worktree's files does not update that checkout. The parent
owns the producer/guard/workflow pins and the combined source/run binding. SDK
3.41.0, ABI 1, headers, exports, bindings and build options remain unchanged by
this adoption. No SDK export or host dependency was removed or replaced.

## Evidence boundaries

The prior isolated candidate tree is recorded as strictly equal to the tree
accepted by run [40244430230/1](https://github.com/NoGod3524/EXReader/actions/runs/40244430230),
source `8015c576822d5284dedfea17428ecf1a240befd0`, strict job `121326920910`.
The record is at commit `0d330c3bdc027a4b9b42b8f402675c13f43a96c1`,
`docs/reader-format-combination/acceptance.json`. That record contains the original
ZIP IDs/digests, Windows/Linux native169, RTF100, CBZ103, argv8 and F5 v2 18/18,
and retains the original F5 v1 failures and first complete-round failure.
It remains evidence for that source and isolated tree; it is not a successful
run for the new combined team source.

This adoption subtask ran no local build, test, syntax check, benchmark, fixture
generation, screenshot, artifact download, unpack or parse. The parent's Actions
run must bind its own source, SDK checkout, installed package and actual host
programs. Native GUI import, first/middle/last-page reading and reopen against
this combined source remain subject to those host runs. Physical-device and
screen-reader acceptance is untested here. Historical failures, frozen SDK
contracts, the 0/1710 historical corpus count and CPU budgets remain intact.
