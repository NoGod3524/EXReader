# Frozen CPU enforcing evidence audit

The tested candidate is `220585e8248918096b9fc2c389ea5ad2389d388b`.
PR 7's tested merge is `eb773e284c58aa8a474f09d780df8db610572e48`;
GitHub's run, job and artifact API metadata names the PR head `220585e8…`.
The original performance summary names the tested merge. The existing
`workflow_identity` check binds the merge's second parent to that API head.

The independent audit downloads only existing artifacts in GitHub Actions.
It binds each original upload's ID, byte count and ZIP digest to the API,
checks the whole ZIP, preserves the original summary and baseline summary,
then replays the existing strict raw auditor in the authenticated original
source/run/attempt context. It does not execute the consumer or measure new
processes. Its own `diagnostic_only=true`, `measurement_performed=false`
and `accepted=false` never grant performance acceptance.

## Observed original runs

All rows below have 40 native processes and 12 reference processes in their
retained original evidence. The exact registry and all budget bytes match
the frozen candidate. A successful audit of a rejected original preserves
that rejection.

| Original run | Actual CPU / environment ID | Original result | Strict raw replay |
| --- | --- | --- | --- |
| [40013452463](https://github.com/NoGod3524/EXReader/actions/runs/40013452463) | AMD EPYC 7763 / `amd-epyc-7763` | accepted, valid, no problems | passed |
| [40013457389](https://github.com/NoGod3524/EXReader/actions/runs/40013457389) | AMD EPYC 7763 / `amd-epyc-7763` | accepted, valid, no problems | passed |
| [40013462159](https://github.com/NoGod3524/EXReader/actions/runs/40013462159) | AMD EPYC 7763 / `amd-epyc-7763` | rejected, invalid measurement | same original budget refusal |
| [40013585658](https://github.com/NoGod3524/EXReader/actions/runs/40013585658), performance job `120619855566` | Intel Xeon Platinum 8573C / `intel-xeon-8573c` | accepted, valid, no problems | passed |
| [40015227294](https://github.com/NoGod3524/EXReader/actions/runs/40015227294) | Intel Xeon Platinum 8573C / `intel-xeon-8573c` | accepted, valid, no problems | passed |
| [40015233091](https://github.com/NoGod3524/EXReader/actions/runs/40015233091) | Intel Xeon Platinum 8573C / `intel-xeon-8573c` | accepted, valid, no problems | passed |

The complete enclosing required workflow was still running at this record's
first audit. Its subsequent strict completion is recorded below.
It contains no 9V45 enforcing result: the first three independent runs all
used 7763, and both additional fixed-source runs used 8573C. Dispatch count
does not establish CPU coverage. All six original runs have now been audited;
the latest diagnostic run is `40016119074`, with 6/6 successful audit jobs.

| Original run | Original artifact ID | ZIP bytes | ZIP SHA-256 |
| --- | --- | ---: | --- |
| 40013452463 | 12528535200 | 36419658 | `bd477015fcd135b37fc62956c3ac731ab646a812147a88ac81b2cd2130b39c7f` |
| 40013457389 | 12527677305 | 36419662 | `f9a56103eafb7508636500da63e67c53e22c29b319840603fd79b49378bd0380` |
| 40013462159 | 12526584845 | 36404534 | `a17ec7dcebe28fbacc65105c8ba758df315abbf09617327c6bbf6f9946ef1630` |
| 40013585658 | 12528400498 | 36419781 | `260a98e3d73705c4f0122e6b63548a3c892b6edae92777b13f1ddec00dfbfe8f` |
| 40015227294 | 12527614128 | 36419730 | `b7b5c97d10549a6efa5aa7f8f460c567dae862f70f6ba2519905a3a4b49ffd57` |
| 40015233091 | 12528412700 | 36419769 | `4a4e4ee88446f44cf8f544ae8185e4bfdc643ed184941981b97f3769b417f10e` |

Shared registry SHA-256:
`d389ec5c71f702a52dfed8acf7b23be4c760acfb8a6a16d7192b701f56c0a6d3`.

Unchanged 7763 budget SHA-256:
`75142b54f03b62d8f12752ff96fbc2f8e7f0d910511ec218165c39844ef5b0f3`.

Independent 8573C budget SHA-256:
`212dba6c709888189a508b94c458ed6912265575d27f6ae0b9c9c4cd6904ae6e`.

## PR 7 required completion

Run `40013585658`, attempt 1, subsequently completed successfully with all
17 jobs successful. The strict final job and check are `120625878069`.
The completed log reports `accepted=true`, `problems=[]`, tested source
`eb773e284c58aa8a474f09d780df8db610572e48`, and tested parents
`f32bb8aa18ed3de286900f19ce4230fd93435dd0` and
`220585e8248918096b9fc2c389ea5ad2389d388b`.

All 28 same-run artifacts were checked independently against their original
job upload logs: each ID, name, byte count and ZIP digest matches the API;
all are nonempty, unexpired and bound to the PR head. The strict summary
binds its 18 required upstream artifacts and selects the independent 8573C
budget above. Its publisher is GitHub Actions app `15368`, confirmed again
by the completed check API object on the PR head.

The final artifact is `reading-required-40013585658-1`, ID `12528860307`,
3,385 bytes, SHA-256
`9fd7d86472ef3f5d7efc3f9f2083aee3e5220ef21dad28e3b476b8e18b8e39de`.
The result remains `published=false`, `complete_product=false`, and
`wp16_cpu_credit_seconds=0`. It does not establish 9V45 runtime coverage.

## Retained 7763 refusal

Run `40013462159`, original job `120619434922`, rejects
`nasa-solar-system/font_open_ms`. The five original samples, in process
order, are `26.043645`, `27.163771`, `37.383341`, `27.070235`, and
`26.221027` ms. Reapplying the existing percentile function gives:

- p95: **37.383341 ms**;
- unchanged budget: **33.07087625 ms**;
- excess: **4.31246475 ms**, or **13.040068%**.

These are replays of the retained original stdout files, not new samples.
The budget and the original failure remain unchanged. The original artifact
is ID `12526584845`, 36,404,534 bytes, SHA-256
`a17ec7dcebe28fbacc65105c8ba758df315abbf09617327c6bbf6f9946ef1630`.

## Diagnostic provenance

- [40014534317](https://github.com/NoGod3524/EXReader/actions/runs/40014534317), source `ee6a47d1d7ab9cedfc289f2e527e4b4e85047484`: retained diagnostic failure. The cloud GitHub CLI refused terminal escape sequences in the original job log; no raw replay completed.
- [40014706615](https://github.com/NoGod3524/EXReader/actions/runs/40014706615), source `d998e56d8109170aace3ab203e4d32913ce62349`: 4/4 diagnostic jobs succeeded after allowing the CLI to retain those inert log bytes. The four original upload/API/ZIP identities were verified.
- [40015276821](https://github.com/NoGod3524/EXReader/actions/runs/40015276821), source `ed99c7fb76821497b1038c1c302ffde16a19f686`: 4/4 diagnostic jobs succeeded and added the rejected metric's original values. Refusal detail is in audit job `120625643759`, artifact `12527827370` (117,970 bytes, SHA-256 `97142e6dc08b789cc6ebcf4452351c658da414234618a91f474a44f44f1de376`).
- [40016119074](https://github.com/NoGod3524/EXReader/actions/runs/40016119074), source `6182f69267f2132e55f6b95363c0922895f703e2`: 6/6 diagnostic jobs succeeded. The additional original runs were audited by jobs `120628489048` and `120628489406`; both are 8573C with successful original strict acceptance and raw replay. Their diagnostic artifacts are `12527768659` (146,773 bytes, SHA-256 `f20eff622cf54aa714bfb628a4ba480b4a862f1757743738e3a1b3426f8a2ebc`) and `12527409707` (146,806 bytes, SHA-256 `6c04fe0cd24d82d8010b04744c3ec389951ef2b1617d4f8ef7b780ba99e7db14`).

No PR 7 source, protected SDK tree, old budget, numeric threshold, or
original run was changed by this audit branch.
