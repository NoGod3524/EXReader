# Mobile annotation directory and gesture continuation — 2026-10-29

Original failed producer: [40935165396](https://github.com/NoGod3524/EXReader/actions/runs/40935165396), source `55ec49020383ef5073f47502b300ab0b5d0a7cae`, attempt 1.
Exact retained iPhone/iPad ZIPs and original wave3 xcresults were authenticated and parsed in [40946269661](https://github.com/NoGod3524/EXReader/actions/runs/40946269661), inspection source `c8cb7ecf21973e0cec731048901e3ac763e59689`.
Both original mobile hosts passed the other 38 cases; annotation exchange exhausted the unchanged 240-second case allowance.

The original cell import repair now reaches both valid and invalid native files. The new traces show avoidable directory-picker probes and repeated slow feature-panel swipes:
- iPhone first export consumed about 66 seconds after the export button, including waiting for nonexistent folder StaticText after creating and entering the directory.
- Both platforms repeatedly crossed the feature panel between actual import controls and fixture/snapshot controls.
- iPad selected the invalid file by 200 seconds, reread revision identity by 223 seconds, and reached the third valid preview only after the 240-second deadline.
- The exported native picker hierarchy exposes the selected directory as `DOC.browsingRoot Source: com.apple.FileProvider.LocalStorage, Title: EXReaderAnnotations`.

Only helpers change. Folder export uses the real local-storage/folder cells, recognizes the already-selected directory, and verifies its identity before pressing Open. Import allows its existing three-second native-cell wait before deciding to leave the current directory. Panel navigation uses a bounded drag sized from the target's actual frame, and reads enabled/frame from one snapshot while retaining the hittable and viewport checks. The original 24-attempt scroll cap, 90-second helper wait and 240-second case budget remain unchanged.

All five feature test bodies, the original Team24 driver and the 34 original suite files remain unchanged. No SDK or product behavior is changed. The full original SDK/native/authentication workflow runs on the new source. This note grants no acceptance while that run is pending.

## Second retained failure and final helper candidate

The first helper candidate `fc336333cd67bf8871e2602777ec857312de06cb` ran as [40946665738](https://github.com/NoGod3524/EXReader/actions/runs/40946665738), attempt 1. macOS passed 39/39; iPad passed 38/39 and timed out only in the annotation case. Its original iPad ZIP is artifact `12934491128`, 479945377 bytes, SHA-256 `cc696e4d3060c7e2a2c6cf2f55e283bd5e7323ff082cfe949e39d1fb37e6d90a`.

The exact ZIP and retained native log were authenticated in [40957964706](https://github.com/NoGod3524/EXReader/actions/runs/40957964706), inspection source `45a49ce266d4649d2c27a0ab5e1743dcffd674d5`. All annotation assertions finished at t=231.30 seconds; the original teardown then called app.terminate, and XCTest reported both a 245.241-second pass line and the four-minute timeout. The raw xcresult marks the case Failed; it remains a failure.

The trace shows five repeated scroll-element resolutions while synthesizing each drag. The final helper candidate anchors both endpoints to the app using the already-observed viewport coordinates, and uses the native fast gesture velocity. Drag distance, visible-target/enabled/hittable checks, 24 attempts, 90-second wait, original case budget, test bodies and teardown termination remain intact. The API is the documented [XCUICoordinate velocity-controlled drag](https://developer.apple.com/documentation/xcuiautomation/xcuicoordinate/press%28forduration%3Athendragto%3Awithvelocity%3Athenholdforduration%3A%29).
