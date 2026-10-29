# Apple SDK 3.42 continuation source staging

Base: 80da967f5411e0c76d25e8bb21ec23c5f2b22385. This is source preparation only. No SDK 3.42 build, test, acceptance, catalog change or release is established by this branch.

Prepared changes:
- Native account detail/retry source and tests from 6c7d043d416c1ab1075016695ae510c7b23dd2e5. Both production files and both test-file parents exactly match this base's original blobs.
- Real iOS original-save picker test from 127cdb7c62772fd293c10cc032547c28904bd1c2. Direct source review shows the only base-to-feature-parent difference is the older modal-only folder-name entry; the accepted test retains the modal path and adds inline rename plus explicit commit.
- Actual tag/series member add/remove/restore/restart assertions from b259db57103cd7661ed3f1c3fc6bd0c49c08981c, applied as an exact-context patch to the base's original six-case organization test. Existing unrelated base fixes are retained.
- Candidate annotation control and active theme-sheet fixes from 622b9558f79eda07211e15c51bffcd728da6c553, currently being tested in 40923468266. Both production parents and the feature test parent match this base. These candidate fixes are not yet accepted.
- Font implementation/lease observations already present in the base are retained. The two font test files already have the exact accepted d23fc1de44d94a80ea8cfc5aa8d74fb24d63400a blobs. The missing review view identifiers and distinct-font fixture button are added to the composed annotation view without replacing the base's SDK 3.42 worker/model.
- Native OS command timestamps are carried for the real appearance test; test cases, commands and budgets are unchanged.

No existing SDK 3.42 worker, bridge, migration, checker, provider or release configuration is overwritten. No SDK 3.41 artifact is reused as SDK 3.42 evidence. Before acceptance this composed source needs its own unchanged feature/retained gates and original package/program authentication. Current fixed-catalog acceptance remains 94/108 at audit 40920714977, with independently scoped SDK 3.41 host results; the eleven final joint-delivery items remain pending.
