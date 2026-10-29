# Claude local C2: product performance / interaction budget (F08)

Receipt: official CLI `--bg` local job, model `claude-sonnet-5-5`, effort medium, logged-in claude.ai
subscription (no API key). Branch `claude/local-c2-product-performance-20261029`, base
`bd28d4946f17a184dd3cd47a584cf49fce34e973`. Not the earlier cloud C2; only this branch is written.

Fixed list stays 95/108; this work does not change `catalog.json` and does not score F08.

## Findings
* Existing drivers already measure the real Windows and GTK hosts (2202-original shelf, first screen,
  pagination, search, page turn, resume, import, working set / RSS) but are pinned to SDK 3.41.0.
* No numeric product budget has been ratified (`docs/READER-PRODUCT-PERFORMANCE.md`); Windows
  p95-based figures are proposals only. Therefore the gate applies no thresholds and `f08_accepted=false`.
* Not covered by any existing driver: scroll, locate/jump, font switch, frame time. Listed as not measured.
* Known earlier blocker kept: Windows original 16 MiB TXT import was `import_rejected`; not retried or hidden.

## Delivered
`tests/reader_product_performance_handoff/` and `.github/workflows/reader-product-performance-handoff.yml`
(Windows + Linux sampling at SDK 3.42.0, verified artifact identity, combined handoff report).

## Results (final tested source c3c143c12cb583e33d7b51149d00db5d86806965)
Run 40975652186, attempt 1, branch claude/local-c2-product-performance-20261029, SDK 3.42.0 common source.
All four jobs succeeded: Windows product performance observation (123802906901), GTK product performance
sampling (123802907080), artifact identity verification (123804686096), same-source handoff record (123804757777).
This is a measurement-completeness pass only. F08 is NOT granted: no numeric product budget was ratified,
thresholds are `none ratified`, `f08_accepted=false`, the fixed list stays 95/108.

Artifacts (ID, bytes, ZIP SHA-256):
* reader-product-perf-windows-40975652186-1: 12941823669, 897497, 4f2f680eb0a76ccb7666f13ba88777d3bde114d57710fbf863aca9b84176104d
* reader-product-perf-windows-identity-40975652186-1: 12942841265, 1078, b3300ab9ae8a64ff9710055a88ba83f028c3547813b9f7b70218fdbec08523d9
* reader-product-perf-gtk-40975652186-1: 12943100548, 2525546, 4e70a9d796a67c97925d554ce5373bc49cb258c871aee36884c93fa2c6ee6f70
* reader-product-perf-gtk-interactions-40975652186-1: 12943055753, 511186, 23d49ef53d0de16017eccdaba49ded32d9cecee9f9f916c4ca7544436eb8b114
* reader-product-perf-gtk-verification-40975652186-1: 12943055795, 1122634, a5ed857ef5aac9a2d9acf755cc443bec2b9cad46f931326ce15b25342a094554
* reader-product-perf-handoff-40975652186-1: 12942114409, 3179, 89fb470a36a140ab3e7b6132b9ef25ae2127dad9d9711305f83d20e7a24d53c7

Measured (ms unless noted; n; p50/p95/max). Windows: Windows Server 2022 runner, real product host, native controls.
* cold shelf first screen 12; 1033/1151/1151. warm shelf first screen 12; 108/120/120. shelf next page 12; 121/127/127. search 12; 208/227/227.
* reading page turn 96; 24.1/26.8/28.1. resume 11; 157/184/184. input during EPUB import p50 12; 0.07/0.08/0.08.
* shelf scroll down 30; 3.4/3.6/4.1. up 30; 2.9/3.1/3.2. font bigger 20; 83/106/115. smaller 20; 81/104/106.
* peak working set (bytes): cold shelf 41,496,576 p50 / 41,508,864 max; reading 48,224,256 p50 / 48,480,256 max.
Linux GTK (ubuntu-22.04, Xvfb 1440x900, real X11 input): 32 main launches, 12 interaction launches.
* first shelf rows 24; 146/293/3326. open book painted 16; 130/187/187. page turn forward 112; 18.3/32.7/35.1, backward 32; 16.2/17.5/33.5.
* continuous 20-turn burst 120; 17.6/32.0/33.9. font bigger 18; 123/216/216, smaller 18; 114/210/210.
* shelf scroll down 36; 306/308/308, up 36; 307/309/309 (ends at the host state observation of the new top row; the shelf widget does not advance painted_generation, so no repaint evidence; includes xdotool injection and GTK scroll animation).
* search title 16; 247/603/603. import input response 192; 3.7/4.7/8.0. RSS high water over 32 launches: p50 69,044 KiB, max 212,900 KiB.
* inter-paint interval proxy 156; 18.9/196/267 includes idle gaps; NOT a frame time.

## Failed attempts kept (not hidden)
* 40947731469 (c4e147c): store/native required the OPDSHash prefix. 40948312493 (bf4cfbd): same prefix needed by the installed catalog package config in downstream configures.
* 40948844051 (5f96a47) and 40949082328 (3696982): samplers passed but the handoff job failed on my own `ls | head` SIGPIPE under pipefail; 0aba90c was superseded before it ran.
* 40954833915 (e1290fb): handoff failed on a malformed gate command line. 40960141382 (c0f3ada): Windows font_bigger "no transition" x5 (font size persists and clamps); Linux shelf scroll samples all failed (no repaint evidence for the shelf widget); handoff reported both. Fixed in c3c143c without changing any budget.

## Not measured / remaining
Frame time and dropped frames (hosts expose no frame clock), navigation jump (not compiled into this GTK build; not driven on Windows), reader-body scroll, Windows original 16 MiB TXT import (still import_rejected per earlier evidence; not retried), Apple, Android, physical devices. Full product F01/F07/F08/F12 not claimed.
