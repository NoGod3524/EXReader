# F08 / F09 / F10 台账复核第二轮（2026-11-15）

基线 `origin/main@c2e20df2aee2de3d061e350d2219005d0f1ab2cb`，分支 `codex/ledger-f08-f09-f10-r2`。本 PR 只改 catalog 的 `note` 和本目录证据。三项 state 均保持 **pending**：`.github/workflows/ledger-authority.yml:56–58`（R3）要求 state 变更只能由 `github-actions[bot]` 的 `Ledger-Authority: audit` 提交反写，人工 PR 改 state 会被拒。下文所说「可计 partial 的达成部分」只是供审计反写参考的事实，本 PR 不写入 state。

范围按 `SCOPE-windows-only.md`（2026-11-15）：读屏录像排除；Windows + Linux 可运行宿主完整验收即可判 verified，其余四端只记 build-only 事实。

## F08：Windows runner 的 render p50/p95 已有真实数字，但不是呈现帧

- 真实数字：run [43677041326](https://github.com/NoGod3524/EXReader/actions/runs/43677041326)（source `d2b0be6b`，windows-2022）。原始样本已入库：`evidence/dfinal-b-budget-security-20261114/actions/f08-realbooks.json`。
- 本轮按原始样本独立复算：`F08-recompute.py` → `F08-recompute.txt`（exit0）。每书候选侧 3×64=192 个样本：

```text
pg1.epub  n=192 p50_ms=0.389750 p95_ms=0.458400 peak_ws=20299776
pg10.epub n=192 p50_ms=0.366000 p95_ms=0.370800 peak_ws=30494720
pg11.epub n=192 p50_ms=0.416400 p95_ms=0.478400 peak_ws=13615104
```

- 同一 JSON 自己写明 `display_present_frame=missing`、`first_interactive=missing`、`accepted=False`。这是宿主 render 函数时间，不是产品呈现帧。本轮没有新增测量。
- 呈现帧需要在产品里加 present/VSync 时间戳（例如 DXGI `GetFrameStatistics`，或在 `examples/windows/shell_d2d.cpp` 的 Present 前后打点）。首次可交互需要从进程启动到首个输入被处理的打点。两者都要改产品代码，超出本 PR「只改 note/evidence」的范围。

## F09：Windows runner 第一次测到真实键盘焦点，同时发现键盘陷阱

- 本机尝试（`F09-keyboard*.txt/json`，source `c2e20df2`）：只调了一次 SetForegroundWindow，被系统拒绝（「无法获得前台」），按规则没有重试。closed 面 12 个控件名字/角色通过，键盘节点 0。
- Runner 运行：run [43769173285](https://github.com/NoGod3524/EXReader/actions/runs/43769173285)/1，用证据专用分支 `codex/ledger-f09-keyboard-runner-20261115`（source `84b8e3e7`，不合并）。该分支只加了 workflow `ledger-f09-keyboard-runner.yml` 和 `F09-keyboard-single-activation.py`，产品源码与 main `c2e20df2` 相同。artifact `14184150395`（512728 bytes，`sha256:69f34472b69077fc5b643130e3b42d1138bfff46d2e7c8cfdda605c2b8b5d227`）。除 `host-data/` 外的内容复制在 `F09-runner-43769173285/`。EXReaderAudit.exe SHA256 为 `eab8f549…f342`。
- 输入全部是真实 SendInput，只做了一次前台激活（`set_foreground_calls=1`），共 382 次键盘焦点观测。逐面结果由 `F09-runner-summary.py` 生成到 `F09-runner-summary.txt`：

| 面板 | 控件 | 可聚焦 | 实测键盘到达 | 未到达的可聚焦控件 |
|---|---:|---:|---:|---|
| closed | 12 | 9 | 5 | 编辑（另有窗口/系统菜单） |
| search | 21 | 16 | 9 | 全文搜索栏、上一处、下一处、编辑 |
| settings | 48 | 45 | 39 | 阅读设置、▾、编辑 |
| toc | 30 | 27 | 5 | 目录面板、目录列表及全部章节项 |
| dictionary-settings | 23 | 17 | 4 | 词典目录、生词本、关闭等 |

- **键盘陷阱（产品缺陷）**：词典设置里 `examples/windows/shell_dictionary.inc:434` 的 `ES_MULTILINE|ES_READONLY` EDIT「词典加载状态」会吞掉 Tab。焦点停在它上面后，连续 117 次 Tab/Shift+Tab 都没离开。采集器在 80 次 Tab 内没能到达 813 号控件（`DICT_VOCAB`「生词本」，`shell_dictionary.inc:5,435`），报 `RuntimeError: keyboard did not reach control 813`，所以 vocabulary、webdav-account、shelf 三面未采集。汇总为 `audit_completed=false`，exit1。
- 同样的 `ES_MULTILINE|ES_READONLY` EDIT 还出现在 `shell_dictionary.inc:391`（查词释义）和 `:459`（生词本释义）。这两处本轮没有采集到，是否也是陷阱未知。
- 本 PR 不修产品。修复方向：给该 EDIT 加子类，把 `WM_GETDLGCODE` 返回值中的 `DLGC_WANTTAB` 去掉，或者把 Tab 转交给父窗口。修完后用同一 workflow 重跑。

## F10：Credential Manager 已有代码，也有真实测试，缺口在别处

- 代码：`extras/credentials/src/windows.c:50–71`（CredWriteW/CredReadW/CredDeleteW，CRED_TYPE_GENERIC）。产品宿主 `apps/reader/desktop/windows_accounts.inc:158`（open）、`:256`（记住时 put）、`:275`（忘记时 delete）。
- 测试：`tests/reader_windows_account/check_account_ui.py:516`（保存进 Credential Manager）、`:562`（仅会话凭据不写安全存储也不写明文）、`:625`（退出重开后加载）、`:630`（忘记后删除记录）、`:746`（任何退出都不留明文凭据）。CI：`reader-g1-integration.yml:331`，run [40118190108](https://github.com/NoGod3524/EXReader/actions/runs/40118190108)（source `4e2dad0b`，success；`4e2dad0b` 是 main 的祖先）。
- 所以缺口**不是**「未实现」，也不是「Credential Manager 本身没测试」，而是：
  1. Credential Manager UNAVAILABLE 状态没有被真正触发（`check_account_ui.py:971` 的 uncovered 列表；`tests/reader_credentials/strict_contract.py:22–24` 中低完整性、VaultSvc 停止、S4U 三种方式都没能让它变成不可用）。
  2. 不同源：`windows_accounts.inc` 在 `4e2dad0b..main` 之间改过（6327f713 等 4 个提交，没有动 `exr_credentials_*` 调用行），main 上没有重跑。
  3. 另一套 Windows 壳 `examples/windows/shell_sync.inc:17,853` 仍用 DPAPI 文件 `sync.cred`，没有接 Credential Manager。
  4. 跨用户（第二身份读取/DPAPI 拒绝）没有测。
  5. 普通 `.tmp` 中断恢复缺失：`evidence/dfinal-b-budget-security-20261114/F10-tests.txt` 中为 `PRIVACY abrupt exit=77: … .tmp remains (startup scavenger MISSING)`。OPDS `.part` 恢复没有测。
  6. 真实远端 TLS/跨源隔离只有 loopback 测试 CA（`check_account_ui.py:971`）。
  7. Linux GTK 宿主还缺 Secret Service 不可用回退、临时文件中断恢复和 TLS 链路的同类证据（见 `evidence/dfinal-b-budget-security-20261114/F10.md` 的「六端缺失产物」表）。
