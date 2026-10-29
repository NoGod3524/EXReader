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
