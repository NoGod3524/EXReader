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

## Linux component validation completed after parallel investigation

Validated measurement source: d981f2d7c8e0bae6408f27a137bc423638e11026. The actual UI-frame boundary was frozen in 34423007204481654bf3f2c2887c39174504d6be before its final full sampling. It uses the original, unsmoothed GdkFrameTimings.frame_time at the start of the native frame cycle, through update/layout/draw/after-paint and measured XSync completion of preceding X-server requests. The separately retained worker-to-content spans are operation latency; they are not substituted for the ordinary UI-frame metric.

Two independently authenticated executions cover all 54 launches:
- [Full original cohort and six causal launches, run 41240011603](https://github.com/NoGod3524/EXReader/actions/runs/41240011603), sampling 124652417890 and audit 124655106085.
- [Reader body and explicit FOUND jumps, run 41241360545](https://github.com/NoGod3524/EXReader/actions/runs/41241360545), sampling 124655764805 and audit 124656057908.
- Original 44-launch / 760-sample cohort and six-launch / 18-action causal cohort remain intact. Four added launches provide twelve actual reader-body wheel actions and six unique-paragraph FOUND jumps.

All 7,837 native UI-frame records remain, including 84 initial clock frames and the 295.194 ms maximum. Required generations missing: zero. Native errors: zero. Complete inventory: 938 jobs, 380 page generations, 172 shelf generations and 1,639 input records. Each native frame joins the retained original clock/counter evidence.

| Native UI-frame scope | Count | P95 ms | P99 ms |
| --- | ---: | ---: | ---: |
| All 54 launches | 7,837 | 7.051 | 11.698 |
| Reader/body | 816 | 11.759 | 15.130 |
| Shelf | 1,616 | 7.622 | 14.009 |
| Page turn | 286 | 8.369 | 9.012 |
| Font/settings | 44 | 8.026 | 9.701 |
| Locate/jump | 224 | 3.286 | 12.071 |

The original 16.67 ms P95 and 33.34 ms P99 limits are unchanged. Cold first interaction maximum is 1,409.056 ms; warm maximum 214.774 ms; original 44-process RSS peak 221,622,272 bytes, with each added reader process below 74 MiB.

Full raw artifact 13057004287: 50,254,714 bytes, SHA-256 694bc9d1d9eb9a551fd484fc7a5703ae26447b47e302d7fbbc39fdebe39f72af. Its independent audit is artifact 13057870435, SHA-256 ef0413fe3cf76582611db523f3b02fbdc24e7874c5197ac1da0b86a8d3044c5c.

Extra-workload raw artifact 13057342447: 137,687 bytes, SHA-256 1a4111ea7284092354bb38a5fc076a6b657df4a9374354556ab5fee29466f249. Its independent audit is artifact 13056999781, SHA-256 029a28f7935c55644663daae77802702a84c788a3c0c0aeb850e059b83823652.

Both use executable SHA-256 c5be0d15fd4de21ad04daa75474d45440e121be0bb20e3b91b4a668c3e637215 and observer SHA-256 c844d11a40a525138221f7721319fd528d3a318b6712a6f2e72f24bb6c7af810. Every original ZIP entry was rehashed. Earlier cancelled, incomplete and driver-error executions remain preserved.

These results validate this Linux component and its recorded X11/Xvfb profile. They do not prove physical/GPU/compositor scanout, and they do not transfer acceptance to other targets or to a later common-source build. The formal F08 catalog remains pending.

## Android optimized Release component

Source 03ecfa21f6cd8d8e354145d56ffdf24244ecbe61 builds the existing complete host with SDK 3.42, PageTheme, Raw3, Wave3, Reading, Preferences, Search, Navigation and Sync. It enables bounded F08 shelf observations with an explicit build property; ordinary builds leave that observation flag false. The APK is a non-debuggable Release variant, signed only with the ephemeral CI test certificate. The unchanged sampler receives explicit legacy filename aliases for these exact Release APK bytes. The independent audit rechecks APK flags, installed/package hashes and absence of private ProductFixture JNI.

This build exposed and fixed a production compatibility guard that accepted PageTheme only with SDK 3.41 despite the host already admitting SDK 3.42. The guard now accepts the two existing palette-capable SDK versions and retains the reading/preferences prerequisites and exact installed-SDK check.

[Run 41240610450](https://github.com/NoGod3524/EXReader/actions/runs/41240610450), sample 124653538458, completed all ten unchanged shelf UI cases and failed the unchanged frame limits. Audit 124655592271 succeeded in authenticating all 326 archived files and recomputing this failure.

| Release observation | Observed | Original maximum |
| --- | ---: | ---: |
| First interaction | 1,562.43903 ms | 2,000 ms |
| Sampled process PSS | 80,632 KiB | 524,288 KiB |
| Ordinary Window P95 | 117.742834 ms | 16.67 ms |
| Ordinary Window P99 | 138.485091 ms | 33.34 ms |

Raw artifact 13056959967: 42,119,480 bytes; SHA-256 791a2a412820cbc308292f0edec869bc3079504eccd3e5383582d007313982e7. Audit artifact 13057403457: 1,233 bytes; SHA-256 cafca364a5a0964846b17bbe1bbed1a7044b07d7d128215d16c18b3d9b5c9b68.

The original forty-case Debug regression remains independently retained; its private fault suites are not claimed to run against this Release binary. Failed intermediate builds, including the original SDK guard rejection and two test-adapter errors, remain in Actions. Software-renderer and native HWUI OpenGL/Vulkan system-Settings controls also remain separate environment diagnostics and do not grant product acceptance.

Android frame acceptance and its additional reader/font/jump coverage are still outstanding. A bounded same-process native FrameMetrics/FrameTimeline diagnostic is being prepared to distinguish UI scheduling, submission, buffer/fence waits and actual raster work. It does not alter the declared budgets or any desktop resolution.


## 2026-10-31 23:25 UTC integration checkpoint

F08 remains pending. Linux has completed its component checks. The following
qualification and functional results do not replace the final same-source,
six-platform acceptance.

### Native Android hardware qualification

The LAP25002 portable emulator passed the official WHPX check and rendered
with Intel Arc 140V. The fixed API34 default x86_64 Pixel6 target uses 4 CPUs,
4096 MiB RAM, 1080×2400 at 60 Hz, density 420 and animation scales 1. The
requested 512 MiB heap is officially clamped to 576 MiB with growth limit
192 MiB, matching the archived Ubuntu runtime. PSS remains limited to
524288 KiB.

Execution adapter 970904cf6c75f2c4729dce56153ececcc7a5b457 used the older
Release producer 03ecfa21f6cd8d8e354145d56ffdf24244ecbe61 from
[41240610450](https://github.com/NoGod3524/EXReader/actions/runs/41240610450),
artifact 13056959967 (42119480 bytes, SHA256
791a2a412820cbc308292f0edec869bc3079504eccd3e5383582d007313982e7).
The frozen ten-case driver/analyzer remain intact except for two Python
identity/admission lines. No Actions environment was fabricated. This is
hardware qualification, not final same-source evidence.

The single native run native-lap25002-20261031T222413Z passed 9/10 cases;
system-picker return failed. All 6348 callbacks remain archived. The 6343
ordinary callbacks have P95 35.132422 ms, P99 67.226670 ms, maximum 601.940994 ms.
Including all five first-draw callbacks gives P95 35.195304 ms, P99 68.467564 ms,
maximum 608.131626 ms. The original pre-draw readiness measurement was
2873.696 ms. Peak sampled PSS was 99120 KiB over 196 valid samples. Numeric
limits were not met.

Independent replay fdea327b7443273140e8881b5b054376df21aa42 authenticated all
252 payloads and native manifest SHA256
e2c535950dba8529c505a76a120db7f911dbfaf19a537ad4b16ee37ce13f2a11.
The first seven screenshots are nonuniform; rotation/process restoration,
offline return and picker screenshots are black. Accessibility state and
pre-draw revision do not prove visible content. The audit rejects these
captures. Future failures also retain installed APK identity and terminal
power/display/window/input/SurfaceFlinger state.

A separate Settings portrait/landscape/portrait/relaunch control passed,
with 229 authenticated payloads and no GL/color-buffer errors. Settings
retained its Window while EXReader recreated its Activity/Window, so the
control does not resolve the original failure. The prior zero-stage observer
format failure and 200 payloads are retained. Completed sessions restored
rotation and left no qemu/product processes; desktop stayed 1920×1200@60.

### Windows and Apple

Windows candidate ff78144229589efd5715fab7528f42d013f143b9 paints a genuinely
new, valid, visible page before returning to the message loop, after all
existing owner/pending/save/control work. Build, 6 CTests, 17 settings and
10 protocol controls passed in
[41250582151](https://github.com/NoGod3524/EXReader/actions/runs/41250582151).
Native attempt 20261031T231709Z-native-frame was stopped by the computer-use
tool's physical-Escape signal before the eight-page cohort. Its 149 payloads
and separate interruption note are retained; no performance pass is claimed.
The original full Windows scope still requires 78 starts, including its
preparations and extra TXT bisect, plus all original assertions.

Apple [41245322975](https://github.com/NoGod3524/EXReader/actions/runs/41245322975)
at 77b2789de3416f4143f3eb2a37ee09a704d34750 completed both SDK jobs, three
native functional jobs and independent audit. Mac artifact 13059771797 is
70279179 bytes, SHA256
7c6a9504f67cdbb8bfeec61bc0f92fd4c9a021fa2c908a6de10f6a83ffd088d6;
all 379 payloads were independently authenticated.

Mac original-scroll hitch ratios are five 0 ms/s measurements, with native
frame-count aggregates [8,14,8,15,8]. Custom shelf intervals have five 0 ms/s
values and frame aggregates [6,10,10,6,6]; actual start/end counters are
120/120 and inactive. These aggregates are not an independent exact total
frame census. All 18 launch-request-to-native-ready upper bounds are below
2 s (maximum 1185.680 ms). Reader font/locate and separate long-EPUB page/locate
cases function, but their SDK snapshot sequence is not an OS frame count;
native reader hitch coverage remains missing.

Phone extended launch is 2.133–2.569 s and iPad 3.500–4.053 s, above 2 s.
Mobile hitch/frame fields remain absent, not zero. Independent macos-26
capability run [41252447709](https://github.com/NoGod3524/EXReader/actions/runs/41252447709)
is testing newer-host metric availability with authenticated 77b program
bytes; old profiles/data retain their original meaning.

The physical-Escape stop is respected: local interaction/VM tests have not
restarted. Source work, archived-data replay and remote verification continue.
