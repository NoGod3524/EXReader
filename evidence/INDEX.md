# Evidence INDEX · A 档 · 2026-11-03

按每行分支与固定 commit 解析仓库内路径。这里只登记已有产物，不合并来源分支、不重跑验收、不改 catalog。仓内副本无 Actions 到期限制；到期列描述对应远端 artifact。

| 产物 | 类型 | 分支与 commit | 仓库内路径 | artifact id | 到期日（UTC） | 关联 run |
| --- | --- | --- | --- | --- | --- | --- |
| 台账护栏与权限规则 | 规则源码；未证实运行验收 | `codex/ledger-guard-20261103@7108a166`；护栏源码 `88572532` | `.github/workflows/ledger-authority.yml`；`docs/reader-total-progress/LEDGER-AUTHORITY.md`；`evidence/default-branch-protection-inventory-20261103.md` | 无专属 artifact | 不适用；仓内保存 | 无专属护栏验收 run；PR #28 的旧 native run 不作护栏通过证据 |
| F05 native 六项与关键阶段材料 | 原始证据仓内副本 | `codex/f05-native-final-20261103@e98cdc3f`；受测 `8a268b8582903926dfa7198a07fabacb2cacd6fd` | `evidence/f05-acceptance-20261103/producer/`；`evidence/f05-acceptance-20261103/MANIFEST.md` | 13259880666 | 2027-02-01 18:21:51Z | 41693082728 / attempt 1 |
| F05 独立 audit 与逐项结果 | 审计仓内副本 | `codex/f05-native-final-20261103@e98cdc3f`；受测 `8a268b8582903926dfa7198a07fabacb2cacd6fd` | `evidence/f05-acceptance-20261103/audit/`；`evidence/f05-acceptance-20261103/session-sampling-summary.json` | 13260346480 | 2027-02-01 18:21:51Z | 41693082728 / attempt 1 |
| F03 GTK 六阶段接收、重启、请求与截图 | 原始小件仓内副本 | `codex/f03-six-host-20261103@f53bb9ed`；受测 `c583ebe7dadf971eed680fea60ab850bbb7a41ce` | `evidence/f03-sdk-examples-20261103/receipts/gtk/`；`evidence/f03-sdk-examples-20261103/screenshots/gtk/` | 13261840048 | 2027-02-01 18:29:08Z | 41694251471 / attempt 1 |
| F03 Windows 六阶段接收、重启与请求 | 原始小件仓内副本；36MB ZIP 未入仓 | `codex/f03-six-host-20261103@f53bb9ed`；受测 `c583ebe7dadf971eed680fea60ab850bbb7a41ce` | `evidence/f03-sdk-examples-20261103/receipts/windows/` | 13261900834 | 2027-02-01 18:29:08Z | 41694251471 / attempt 1 |
| F03 audit 原件与 round-1 逐项结果 | 1261B ZIP、2820B 原始 JSON、汇总及保管清单 | `codex/f03-six-host-20261103@f53bb9ed`；受测 `c583ebe7dadf971eed680fea60ab850bbb7a41ce` | `evidence/f03-sdk-examples-20261103/audit-result.zip`；`evidence/f03-sdk-examples-20261103/audit-result.json`；`evidence/f03-sdk-examples-20261103/round-1-items.json`；`evidence/f03-sdk-examples-20261103/archive-manifest.json` | 13261530995 | 2027-02-01 18:29:08Z | 41694251471 / attempt 1 |
| custody：F05 GTK recovery | 原样 Git patch，未 apply | `codex/ledger-guard-20261103@a212dd59975d5aa4256af7cc37d1bddd6b242dd1`；补丁源 `codex/f05-gtk-recovery-r3-20261103@0be9b39384edd386b48b78d128515cf330611654` | `evidence/custody-20261103/0001-Repair-F05-GTK-credential-readiness-bounded-cleanup-.patch` | 无；仓内原件 | 不适用；仓内保存 | 历史工作线关联 41679586829，非补丁验收证明 |
| custody：F05 原 GTK dialog 观察 | 原样 Git patch，未 apply | `codex/ledger-guard-20261103@a212dd59975d5aa4256af7cc37d1bddd6b242dd1`；补丁源 `codex/f05-gtk-recovery-r3-20261103@c4d67540a0e17a86bd42ad9323cd269ce8959326` | `evidence/custody-20261103/0001-Observe-original-GTK-import-dialogs-without-changing.patch` | 无；仓内原件 | 不适用；仓内保存 | 历史工作线关联 41679586829，非补丁验收证明 |
| custody：F03 Android/Windows build | 原样 Git patch，未 apply | `codex/ledger-guard-20261103@a212dd59975d5aa4256af7cc37d1bddd6b242dd1`；补丁源 `codex/f03-six-host-20261103@e2776a35c965f676f49c1cc85c709c24494b7743` | `evidence/custody-20261103/0001-F03-ANDROID-F03-WINDOWS-Build-synchronization-profil.patch` | 无；仓内原件 | 不适用；仓内保存 | 历史工作线关联 41679502785，非该 patch 的独立验收 |
| custody：F03 Apple receive | 原样 Git patch，未 apply | `codex/ledger-guard-20261103@a212dd59975d5aa4256af7cc37d1bddd6b242dd1`；补丁源 `codex/f03-six-host-20261103@a375fd9baa70f040d5c144415c5ec0d2e541e5e6` | `evidence/custody-20261103/0001-F03-SIX-HOST-Integrate-bounded-Apple-organization-re.patch` | 无；仓内原件 | 不适用；仓内保存 | 历史工作线关联 41679502785，保留原范围与结果 |

custody 四份 patch 的 SHA-256 见来源分支 `evidence/custody-20261103/MANIFEST.md`。F03 与 F05 的接受范围分别以各自归档为准；护栏源码与 custody patch 的存在不授予产品验收信用。

T1 四个首错、两侧历史对照及 T4 方案见 [t1-readonly-triage-20261103/README.md](t1-readonly-triage-20261103/README.md)，原观察见 [observations.json](t1-readonly-triage-20261103/observations.json)。T1 保持停手，T4 仅列为前置方案；本索引更新零新 run。
