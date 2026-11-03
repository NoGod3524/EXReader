# Evidence custody · 2026-11-03

当前收口：保留 #31 已入库的四份 patch 与 manifest，不重建、不应用。ledger-evidence-custody.yml 文件已携入，**待 R 后 owner 确认启用**；以下 dispatch 步骤是启用后的设计，不是本次触发授权。

`ledger-evidence-custody.yml` 仅由 owner 手动 workflow_dispatch 触发。默认 commits 为 `0be9b393,c4d67540,e2776a35,a375fd9b`，retention_days 为 90。四个提交均已存在；本流程只搬运补丁，不校验、不重建、不 apply。对应 run 是工作线关联记录，不表示该 run 已通过或针对每个提交执行。

| commit | 分支 | 主题 | 触及文件 | 对应 run | patch 文件名 | sha256（仓库 patch） |
|---|---|---|---|---|---|---|
| `0be9b393` | `codex/f05-gtk-recovery-r3-20261103` | Repair F05 GTK credential readiness, bounded cleanup and case alignment [skip ci] | `.github/workflows/gtk-sdk342-package.yml`<br>`tests/product/f05_gtk_native_recovery_20261103/case_alignment.py`<br>`tests/product/f05_gtk_native_recovery_20261103/check_dry_run.py`<br>`tests/product/f05_gtk_native_recovery_20261103/check_r3.py`<br>`tests/product/f05_gtk_native_recovery_20261103/contract.json`<br>`tests/product/f05_gtk_native_recovery_20261103/driver.py`<br>`tests/product/f05_gtk_native_recovery_20261103/gtk.py`<br>`tests/product/f05_gtk_native_recovery_20261103/inspect_network.py`<br>`tests/product/f05_gtk_native_recovery_20261103/native_runtime.py` | 41679586829 | `0001-Repair-F05-GTK-credential-readiness-bounded-cleanup-.patch` | `d5939df1dc646f7dc59952c5897a5c62eed1229563c7569ca0c84ec2c1ad04a4` |
| `c4d67540` | `codex/f05-gtk-recovery-r3-20261103` | Observe original GTK import dialogs without changing test decisions [skip ci] | `tests/product/f05_gtk_native_recovery_20261103/contract.json`<br>`tests/product/f05_gtk_native_recovery_20261103/driver.py`<br>`tests/product/f05_gtk_native_recovery_20261103/retained_diagnostics.py` | 41679586829 | `0001-Observe-original-GTK-import-dialogs-without-changing.patch` | `961bb872ec0d6e6d060c82d9c6c2b42d0c25dc8b98cb0c31d2350b4ce8fcfc3b` |
| `e2776a35` | `codex/f03-six-host-20261103` | [F03-ANDROID] [F03-WINDOWS] Build synchronization profile and normalize canonical hash prefix | `.github/workflows/f03-six-host-20261103.yml`<br>`docs/reader-total-progress/F03_SIX_HOST_20261103.md`<br>`tests/dot_f03_same_source_20261031/build.py`<br>`tests/f03_six_host_20261103/run.py` | 41679502785 | `0001-F03-ANDROID-F03-WINDOWS-Build-synchronization-profil.patch` | `be549d684044668e76ea75d67a3a02faea580179a09c4d4182f2db8609db290b` |
| `a375fd9b` | `codex/f03-six-host-20261103` | [F03-SIX-HOST] Integrate bounded Apple organization receive and pin native validation source | `.github/workflows/f03-six-host-20261103.yml`<br>`docs/reader-total-progress/F03_SIX_HOST_20261103.md`<br>`examples/apple/HostCatalog.swift`<br>`examples/apple/HostModel.swift`<br>`tests/dot_f03_same_source_20261031/AppleOrganizationInteropTests.swift`<br>`tests/dot_f03_same_source_20261031/gtk.py`<br>`tests/dot_f03_same_source_20261031/windows.py`<br>`tests/f03_six_host_20261103/run.py` | 41679502785 | `0001-F03-SIX-HOST-Integrate-bounded-Apple-organization-re.patch` | `dd420b350ffae1bd756536bdf9f47eeff0fe83388b480a098e9bc961e8094b40` |

artifact 名为 `ledger-evidence-custody-<run id>-<attempt>`，包含补丁与 `MANIFEST.txt`；manifest 记录输入短 SHA、解析后的完整 commit SHA、补丁文件名及 SHA-256。artifact 是可选副本；上表 SHA-256 对应仓库中原样保存的 patch，文件名与 Actions 导出名称不同。

patch 本体位于 evidence/custody-20261103/，来源 commit 与 sha256 一一对应。custody 不再依赖 Actions；完整校验表与命令见该目录的 `MANIFEST.md`。

## 取回后复验

取回仓库后按 `evidence/custody-20261103/MANIFEST.md` 核对完整 commit SHA 与四份 patch 的 SHA-256。进入该目录后可逐份运行：

```bash
sha256sum <patch文件名>            # 与 MANIFEST.md 比较
git apply --check <patch文件名>     # 只验可应用，不落地
git show <sha> --stat
```

`git apply --check` 取决于当前工作树基线；已包含该提交的工作树可能报告不可重复应用。

## #33 索引与接收边界补充

以下“本C包”指 #33 当时仅增加索引、不复制原件的原始范围；#31 已有的 patch 和完整表格继续保留。

本文件仅为索引；本C包不应用补丁、不复制原件、不触发workflow。ledger-evidence-custody.yml **待 R 后启用**。

原件：[PR#28 custody固定目录](https://github.com/NoGod3524/EXReader/tree/7108a1662484b95f8e205795e2cc601acbe6aec9/evidence/custody-20261103)；完整路径/工件/过期日见[唯一INDEX](https://github.com/NoGod3524/EXReader/blob/de0832112e92c47bc1a47969236dd2376a0ed55f/evidence/INDEX.md)。

上游 #33 的摘要表标注“转录原manifest，本包未重验”；四个来源 commit、原分支、patch 与 SHA256 均与上方完整表相同，合并后只保留一套完整数据行，不删除 run、触及文件和复验方法。

关联run不是每份补丁的通过证明。接收方须核完整commit、摘要、目标基线与独占权限；不重复应用已包含提交，不挪用旧CI额度。仓库保管不等产品完成。
