# F08 native window capture and Android startup evidence — 2026-10-31

F08 remains unaccepted. This receipt preserves additional observations and the failed measurements that led to them. It does not change a performance limit, mark a missing measurement as passing, or update the formal progress catalog.

## Native Windows capture

The existing full Windows product remains pinned to source 6bb0a7083c218b8899f9451336654c650b53495c and executable SHA-256 be69ceb2eadd59e13e14e627db85c066200ab2d199be79edab935cee04dadc2d. The additional device executions used LAP25002 and its Intel Arc 140V hardware GPU. They are local executions, not GitHub Actions runs.

Desktop Duplication on the foreground product returned only protected/masked records. Those attempts remain in the device evidence. An owned-window Windows.Graphics.Capture observer subsequently obtained actual shelf and reader pixels without changing the product.

Observer source 679895786e4a2c62b961583441f894d373aba4b1:
- [Build 41235017683](https://github.com/NoGod3524/EXReader/actions/runs/41235017683), job 124636828488, succeeded.
- Artifact 13054977453, 34,789 ZIP bytes, SHA-256 4473c2000b94eb8b5ff1109086543d9af274d7f9f93edc5446472080ce4de5fb.
- observer.exe: 80,896 bytes, SHA-256 d9091ee8b19cce806942d1c7127802b0cfe222eda10e378d95e0cd2bde9869c7.
- Invalid HWND rejection and WIC lossless PNG encode/decode checks passed. Independent Pillow decoding reproduced all test pixels exactly.
- No software-GPU fallback, border suppression, display-affinity modification, or ETW privilege change is implemented.

Producer f494462a984ed7e0ac7f19700f1fedac705ba325 executed on the native device at 20261031T193811Z. Both observer processes exited successfully. The original analyzer rejected an intermediate uniform reader region. Analyzer 8a4f7f90b33142ccc4dfb4722c8c99a8f728eac0 replays the same retained records and reports uniform pixels as an unresolved observation, preserving them separately from verified nonuniform content.

| Observation | Shelf launch | Font launch |
| --- | ---: | ---: |
| Native window frames | 706 | 184 |
| Recorded input dispatches | 32 | 16 |
| Distinct nonuniform shelf frames | 574 | 126 |
| Distinct nonuniform reader frames | 0 | 10 |
| Uniform reader observations | 0 | 2 |
| Native timestamps later than callback QPC | 706 | 176 |
| Encoded image bytes | 38,553,372 | 9,023,920 |

All 1,010 manifest-listed files were rehashed before replay. Native manifest SHA-256: 7b66624fbde489a90af74bd68f14c3e6e225325b5cf5903c92645a9c619ae41e.

The local bundle contains the original run, its original failure, and separate replay outputs:
- C:\Users\Oscar\.codex\f08-analysis\native-window-193811.zip
- 115,264,238 bytes; SHA-256 5b9b61a791a621f425442c62eaf90a8ec7b5da91e6ad98d598f4c63d7534fa3e.
- 1,015 files including the outer artifact index.
- Source data: C:\Users\Oscar\.codex\f08-device-runs\20261031T193811Z.
- Replay: C:\Users\Oscar\.codex\f08-analysis\window-png-replay-193811.

The earlier bitmap execution at 20261031T193259Z reached its 1 GiB raw-image cap during genuine native scroll animation; it is preserved as a failed capture. PNG storage retained the pixel values and avoided that storage limit.

The observed native timestamp ordering conflicts with a straightforward elapsed-time join to callback QPC. No offset correction or replacement timestamp is applied. Application paint generations and a complete application-frame census are still absent. Frame-budget and physical-scanout acceptance remain false.

### Desktop resolution

At the user's request, source 8a4f7f90b33142ccc4dfb4722c8c99a8f728eac0 removes all display-mode mutation calls from the local harness. Future executions record the user's existing display mode and constrain only the product window. The last display-changing execution restored 1920×1200 at 60 Hz. No product or observer process remained after it.

This change defines a separate native window profile; it does not retroactively rewrite the old 1280×800 desktop observations.

## Android startup

### Preserved full shelf measurement

Source 5d4152744ef0fd9a1f2775cdcdae0e542b08476d, [run 41233018618](https://github.com/NoGod3524/EXReader/actions/runs/41233018618):
- Sampling job 124630936542 failed the original numeric limits.
- Audit job 124633168016 succeeded in authenticating and recomputing that failure.
- Raw artifact 13054622664, 43,952,290 bytes; SHA-256 518d4d94e7f153e09b394b0d64f2c2522c5041a9d6997d08d7a5a68f9fb174ab.
- All ten original shelf UI cases and all eighteen original ProductOwnerTest cases passed.
- First interaction: 3,842.087265 ms, limit 2,000 ms.
- Ordinary Window frame P95: 118.996833 ms, limit 16.67 ms.
- P99: 147.227843 ms, limit 33.34 ms.
- Sampled PSS: 102,219 KiB, limit 524,288 KiB.

The source uses the existing revision-heads query instead of decoding a complete selected revision solely to determine whether any history exists. Its standalone full-run timings must not be compared as an A/B result across different hosted machines.

### Same-process query diagnosis

Source 89ad06714250667a82851253d24398eab47acf63, [run 41235602427](https://github.com/NoGod3524/EXReader/actions/runs/41235602427):
- Diagnostic job 124638612390 and audit 124639868860 succeeded; both have a 20-minute cap.
- Raw artifact 13055760536, 42,353,246 bytes; SHA-256 22b175726b64bf3929ce4403b8934697c798f4956ad470c8b108bbc642246d1b.
- Audit artifact 13055585736, 1,506 bytes; SHA-256 cf6d73889071ab4133b57ff6eaeccca38d687601ff27a84d6a383695751ea8df.
- Three independent instrumentation processes used the original 2,202-source library. Filesystem cache coldness is explicitly not claimed.
- Every per-book timing row is retained, and the independent audit recomputes the sums.
- Each ABBA query pass verifies exactly the same observed heads for every book.

| Process | BookStore open ms | Full local shelf lookup total ms | Heads total ms |
| --- | ---: | ---: | ---: |
| 0 | 892.586 | 506.051 | 267.348 |
| 1 | 889.420 | 502.468 | 266.862 |
| 2 | 873.929 | 509.885 | 268.828 |

The alternating full-selection queries took 611.527–630.577 ms per 2,202 books. Existing heads queries took 225.705–230.622 ms. This same-run diagnosis supports removal of redundant selection decoding. It does not establish UI performance acceptance.

### Key-only candidate: complete functional regression, frame budget still failed

Product change 1efae40cf006b59f22673edccf763e446183a695 adds a JNI projection returning only the existing local lookup's book key. Mapping repair keeps its catalog lookup, missing-mapping check, revision check and bootstrap behavior; it avoids constructing five Java display strings and a shelf object for each book.

The first validation, source 3f74fa7205cb48cdbd0c7804ebff7ace5288aef9 and run 41236301654, completed its ten UI cases but then failed because the startup diagnostic and full sampler both created the same installed-package receipt directory. The dependent audit failed at the consequently absent evaluation.json. Both failures remain preserved. Its raw artifact is 13055663243, 44,354,178 bytes, SHA-256 73f6a06449f460114c22c854eca6235481ede195af5f05d62d028bb56e1e582e. A separate replay authenticated all 339 manifest payloads; it did not rewrite the producer result. The UI data in that failed producer still exceeded the frame and first-interaction limits.

Source 1c5eb2f7f12ec59cab182ceaeb574672cee4968b separates startup-installed from the ordinary installed receipt. [Run 41237326028](https://github.com/NoGod3524/EXReader/actions/runs/41237326028) completed the original ten shelf UI, eighteen ProductOwnerTest and twelve ShelfCatalogTest cases. All forty passed. Sampling job 124643723129 then failed the unchanged frame limits; independent audit 124645833257 authenticated and recomputed the complete observation.

| Metric | Observed | Original maximum | Result |
| --- | ---: | ---: | --- |
| First interaction | 1,987.733059 ms | 2,000 ms | Pass in this execution |
| Sampled PSS | 114,817 KiB | 524,288 KiB | Pass |
| Ordinary Window frame P95 | 84.834417 ms | 16.67 ms | Fail |
| Ordinary Window frame P99 | 103.456589 ms | 33.34 ms | Fail |
| Forward scroll P95 / P99 | 84.450628 / 88.98622 ms | 16.67 / 33.34 ms | Fail |
| Reverse scroll P95 / P99 | 83.659927 / 88.572523 ms | 16.67 / 33.34 ms | Fail |

Raw artifact 13056143910 has 64,166,493 ZIP bytes and SHA-256 ada9948c943a316f79577218fc7b889600ae6c6a07372d7258a0f1021ab474f2. Audit artifact 13055569953 has 1,987 bytes and SHA-256 d40c762ebe69748a889badbb4d0484c96847897ea78ada3c1a2d4c540af63459. All 319 archived files were authenticated. Both jobs retained their 20-minute caps.

Same-process lookup/key ABBA checks verified the same 2,202 keys. The three constructor times were 388.898, 379.622 and 382.509 ms. The key-only query passes took 100.969-109.015 ms per 2,202 books, while full lookup passes took 293.326-323.249 ms on the same runner. Different-run startup timings are not an A/B comparison.

### Native system-UI renderer controls

Source 7fae9b37f1c2210a538b3924b31093df7db24dc2 predeclared three software-renderer candidates before [run 41238038744](https://github.com/NoGod3524/EXReader/actions/runs/41238038744). Each used the same API34 x86_64 Pixel 6, four virtual CPUs, 4 GiB RAM, animation scale 1 and native 1080x2400 geometry, without a size override. The program under observation was Android's system Settings, not EXReader. Its APK SHA-256 was ea2c3efc9f4ad1d5e84ecb1f4aa0d05703bab8f6a7c57c35091ddc9f8916a666 in every candidate.

| Requested renderer | Retained ordinary completed frames | Native Settings elapsed P95 / P99 ms | Artifact |
| --- | ---: | ---: | --- |
| swiftshader_indirect | 103 | 267.147451 / 355.762521 | 13056705073 |
| swangle | 65 | 677.580276 / 907.532378 | 13055934595 |
| lavapipe | 103 | 294.057899 / 407.501985 | 13055959631 |

These are bounded gfxinfo ring observations and environment controls, with separate timestamp semantics from the product Window callback metric. All snapshots and two unavailable swangle completion records remain. The controls do not establish an EXReader frame census, a product pass, or a matched-host A/B comparison between renderers. They show that substantial native system-UI latency also occurs in these hosted software-renderer environments.

## Linux and remaining acceptance

The WAL repair remains supported by the earlier alternating cold-population comparison and full GTK cohort:
- Product change a2d3bdd6f7258b6c27188093b253dcad3038c6ca.
- Full product source da12b2b2ea1a727e2d5038d0219a608742227b3b, [run 41228772173](https://github.com/NoGod3524/EXReader/actions/runs/41228772173).
- Original 44 launches/760 samples plus six causal launches/18 actions completed.
- Cold first interaction maximum 1,447.867 ms, warm maximum 215.792 ms, RSS maximum 221,474,816 bytes.
- Frame acceptance remains missing.

Mutter capability source 0c89ee0bee126c2316b2a6445bde7a5a47bb42f3, [run 41233452305](https://github.com/NoGod3524/EXReader/actions/runs/41233452305), obtained 120 complete synthetic frame-clock records but zero actual presentation values. The prerequisite rejected the environment and skipped the expensive full cohort.

GTK 3.24.33's Wayland implementation itself estimates its presentation field from a frame callback plus one refresh interval. Merely obtaining nonzero values from that backend would not resolve this gap. See [upstream implementation](https://github.com/GNOME/gtk/blob/3.24.33/gdk/wayland/gdkwindow-wayland.c#L492).

Remaining work includes valid product-frame attribution on Windows and Linux, Android UI performance and full interaction coverage, Apple first-interaction and missing frame/workload coverage, and rebuilding/verifying the six targets from one final production source. Local screenshots, successful artifact audits, and passing query diagnostics do not close those gates.

## Parallel integration

At the user's request, Windows, Linux and Apple are being handled by three independent GPT-6.1 Sol agents at max reasoning; the root agent owns Android, integration and final acceptance. Each uses an isolated branch/worktree. Desktop resolution changes remain prohibited.

The integration branch is codex/f08-final-integration-20261031. Its initial production assembly is source 01dcd120b186ed3e8f72a373aff52db798d89613. Relative to the shared base 6c3c75bc793acb2bd369db7ea9d701fb87946a81, only six production paths differ: the three Android mapping-projection paths and three Linux durable-WAL paths. Core SDK source/include/CMake trees remain unchanged. Existing Windows/Apple/Linux measurement adapters and failed evidence are retained in the history. New agent instrumentation is not accepted into the final source until its checks and measurement coverage are reviewed.

Formal catalog F08 remains pending. The next common-source execution must prove all required target/workload budgets; independent component runs cannot transfer acceptance to that assembly.
