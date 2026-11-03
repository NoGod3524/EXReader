# Evidence custody · 2026-11-03

`ledger-evidence-custody.yml` 仅由 owner 手动 workflow_dispatch 触发。默认 commits 为 `0be9b393,c4d67540,e2776a35,a375fd9b`，retention_days 为 90。四个提交均已存在；本流程只搬运补丁，不校验、不重建、不 apply。对应 run 是工作线关联记录，不表示该 run 已通过或针对每个提交执行。

| commit | 分支 | 主题 | 触及文件 | 对应 run | patch 文件名 | sha256（artifact 生成后补） |
|---|---|---|---|---|---|---|
| `0be9b393` | `codex/f05-gtk-recovery-r3-20261103` | Repair F05 GTK credential readiness, bounded cleanup and case alignment [skip ci] | `.github/workflows/gtk-sdk342-package.yml`<br>`tests/product/f05_gtk_native_recovery_20261103/case_alignment.py`<br>`tests/product/f05_gtk_native_recovery_20261103/check_dry_run.py`<br>`tests/product/f05_gtk_native_recovery_20261103/check_r3.py`<br>`tests/product/f05_gtk_native_recovery_20261103/contract.json`<br>`tests/product/f05_gtk_native_recovery_20261103/driver.py`<br>`tests/product/f05_gtk_native_recovery_20261103/gtk.py`<br>`tests/product/f05_gtk_native_recovery_20261103/inspect_network.py`<br>`tests/product/f05_gtk_native_recovery_20261103/native_runtime.py` | 41679586829 | `0be9b393.patch` | |
| `c4d67540` | `codex/f05-gtk-recovery-r3-20261103` | Observe original GTK import dialogs without changing test decisions [skip ci] | `tests/product/f05_gtk_native_recovery_20261103/contract.json`<br>`tests/product/f05_gtk_native_recovery_20261103/driver.py`<br>`tests/product/f05_gtk_native_recovery_20261103/retained_diagnostics.py` | 41679586829 | `c4d67540.patch` | |
| `e2776a35` | `codex/f03-six-host-20261103` | [F03-ANDROID] [F03-WINDOWS] Build synchronization profile and normalize canonical hash prefix | `.github/workflows/f03-six-host-20261103.yml`<br>`docs/reader-total-progress/F03_SIX_HOST_20261103.md`<br>`tests/dot_f03_same_source_20261031/build.py`<br>`tests/f03_six_host_20261103/run.py` | 41679502785 | `e2776a35.patch` | |
| `a375fd9b` | `codex/f03-six-host-20261103` | [F03-SIX-HOST] Integrate bounded Apple organization receive and pin native validation source | `.github/workflows/f03-six-host-20261103.yml`<br>`docs/reader-total-progress/F03_SIX_HOST_20261103.md`<br>`examples/apple/HostCatalog.swift`<br>`examples/apple/HostModel.swift`<br>`tests/dot_f03_same_source_20261031/AppleOrganizationInteropTests.swift`<br>`tests/dot_f03_same_source_20261031/gtk.py`<br>`tests/dot_f03_same_source_20261031/windows.py`<br>`tests/f03_six_host_20261103/run.py` | 41679502785 | `a375fd9b.patch` | |

artifact 名为 `ledger-evidence-custody-<run id>-<attempt>`，包含补丁与 `MANIFEST.txt`；manifest 记录输入短 SHA、解析后的完整 commit SHA、补丁文件名及 SHA-256。首次 artifact 生成后依据 manifest 填入上表空白。

## 取回后复验

在解压目录核对 manifest 的完整提交 SHA 与补丁 SHA-256；再在目标仓库运行：

```bash
sha256sum <sha>.patch             # 与 MANIFEST.txt 比较
git apply --check <sha>.patch      # 只验可应用，不落地
git show <sha> --stat
```

`git apply --check` 取决于当前工作树基线；已包含该提交的工作树可能报告不可重复应用。
