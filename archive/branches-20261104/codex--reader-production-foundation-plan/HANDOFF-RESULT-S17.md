# HANDOFF-RESULT-S17：同步状态视图的 raw 家族兼容

**结论：未接纳（accepted=false）。** 三轮完整 CI 额度已用完；两平台的**验收本身全绿**，
但**包级汇总与混装拒绝矩阵没跑成**，工件身份未经严格复算。所有失败与未验证项原样保留。

## 1. 身份

| 项 | 值 |
| --- | --- |
| 固定起点 | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` |
| 分支 | `codex/reader-next-s17`（仅功能分支，未推默认分支，未开 PR/tag/Release） |
| workflow | `.github/workflows/reader-next-s17.yml`（只触发本分支 + workflow_dispatch） |
| **CI 跑过的源码 SHA** | **`ef5f3898393efea169add05b79c8c210082de121`** |
| 批准 SDK 3.41（未改） | `edddc463c06ed5731195cdb8f06b2df6dff7699e` |
| 冻结旧 SDK 3.40（未改） | `9854061be331fe603a1822d9b2b36ee357154927` |
| 最终 run / attempt | `40227736624` / `1` |
| jobs | ubuntu-22.04 `121272616077`、windows-2022 `121272616328`、aggregate `121273310787` |

目标源码 = 固定起点 + 本包三处模块改动；补丁前后树见 `git diff e67d87c…ef5f3898`
（14 个文件、+1650/-5），全部落在独占路径内，`run.py` 的 `git diff --exit-code`
与路径白名单守卫在 CI 里先于任何构建执行并通过（含 `src include cmake CMakeLists.txt`
等于批准 SDK 3.41 的树、`apps/reader/{store,revisions,sync,session}`、`extras`、
`examples`、`tests/reader_{sync_status_view,revisions,sync,session}` 未改）。

## 2. 交付内容（全部实测过的部分）

- `apps/reader/sync-status-view/`：显式 raw 家族切换（`option(EXR_READER_SELECTOR_BYTES_CANDIDATE)`，
  view 0.2.0 / session 0.2.0），`src/sync_view.cpp` 用两个匿名命名空间薄包装在编译期
  选 `reader_revision_outbox_raw_v3` / `reader_revision_heads_raw_v3`，头文件家族宏 +
  Capability 文档段，CMake 与安装 config 里加共享 `_exr_raw_guard_target` 家族校验。
  **默认 legacy 行为、公共结构/枚举/错误码、语义全部不变；没有新公共 API，没有新运行时构造器。**
- `tests/reader_next_s17/`：`run.py`（两套家族安装 + 两套消费者 + 混装矩阵 + 两套验收）、
  `check_raw_view.py`（真实 TLS 的 20 条具名检查）、`strict.py`（同源工件身份复算）、
  `consumer/`（`raw-view-consumer`、`raw-view-c-consumer`、`raw-revision`）。
- `docs/reader-next-s17/README.md` 与 `validation.json`（含失败与未验证清单）。

## 3. 真实跑绿的部分（run 40227736624 / attempt 1）

| 平台 | 默认家族（**原封不动**的旧消费者 + 旧裁判） | raw 家族（新消费者 + 新验收） |
| --- | --- | --- |
| ubuntu-22.04 | 22/22 具名检查 PASS，`reportedAccepted=true` | 20/20 PASS，`profile` = view 0.2.0 / session 0.2.0 / sync 0.2.0 / revisions 0.4.0 / raw 1 |
| windows-2022 | 22/22 PASS（该 job 共 42 条 PASS = 22+20） | 20/20 PASS，同 profile |

raw 20 条检查覆盖：家族/版本/能力宏显式；空闲只读零请求；空 pending 页与参数契约；
**视图与 session 原值逐字段一致**（16 个镜像字段 + 阶段映射 + sweep/resumable 派生位，
在 idle / syncing(阻塞) / cancelled / sweep-complete / closed 静止态各取一次）；
取消保留真实 cursor 与 100 条已收 raw 历史、代际 attempt=3 续跑完成 256 分片；
一次 sweep ≠ 库完整；raw outbox 分页/冲突 opt-in/retry token；另一家族句柄被拒绝且不留快照；
row_limit 上下界；owner 违规失败关闭；无句柄多线程；真实发布 + ack；401→needs-credentials；
不可达→offline；closing/closed 可观察；快照活过双 owner 且 release 幂等；
**重复 capture 后产品库字节完全一致、不新增任何文件、无 `*.tmp`**；证据无凭据/正文/源 URL。

程序 hash（来自验收报告本身，不是构建清单）：
- Linux `raw-view-consumer` = `4628a1ff70669fad85f5a754f461ec654e2dcdbc2e3b3c0d53112b98ad09a38c`，
  `raw-view-c-consumer` = `daaf3269957169d984c4e9effe16fe01cb35d4d0c22e75f69ef1c06209d3bbdd`
- Windows `raw-view-consumer` = `c9c33fef7dd2afdb685a12512147595c0a4b0a7cc6c90e2c155b95e287c49ea8`，
  `raw-view-c-consumer` = `eac7c7fef70eb67168825a39adebfe7ba0f5ee0377e22db0daafae41acd48f16`

## 4. 工件（**未认证**，只有 GitHub 自报值）

| 平台 | name | id | bytes | digest（GitHub 报告） | expires_at |
| --- | --- | --- | --- | --- | --- |
| Linux | `reader-next-s17-Linux-40227736624-1` | `12611856569` | `17705301` | `sha256:a3198651f665cefab6e0e66608acbdc53df5a5defe5cbae514473badd995aa62` | `2027-01-23T19:48:01Z` |
| Windows | `reader-next-s17-Windows-40227736624-1` | `12612261164` | `23997479` | `sha256:b8e0ed09f1acac5abeecf04d7db6a1e79af6447a09250d20417640e0ac6ebd37` | `2027-01-23T19:48:01Z` |

这两个 ZIP 是**唯一原件且未过期**，但 `strict.py` 在任何 digest 复算之前就退出了，所以
size/digest/source 绑定**没有**被本包认证；没有 `reader-next-s17-summary-…` 工件（汇总目录为空）。

## 5. 三轮失败（原样保留）

1. **run 40227353076**（`a7f54f3c`）：两平台都倒在安装阶梯的 `sync` configure。
   根因：`run.py` 把 build 目录同时当安装前缀，而 `configure_package_config_file` 会把
   `<Name>Config.cmake` 写进 build 树，`find_package` 于是优先命中这个"半安装"文件。
   修于 `771ba50e`。
2. **run 40227554690**（`771ba50e`）：`ctest --test-dir` 仍指向改动前的 build 路径。
   修于 `ef5f3898`。
3. **run 40227736624**（`ef5f3898`，即定版）：验收两套全绿后，
   - `run.py:217` 对**旧裁判报告里不存在的** `adopted` 键做断言 → `KeyError: 'adopted'`，
     包级 `result.json` 未写出，**其后的 5 条混装拒绝矩阵一次都没执行**；
   - 汇总作业 `strict.py:49` 调 `actions/runs/<id>/attempts/<n>/artifacts` → GitHub 返回
     `Not Found`（正确端点是 `.../runs/<id>/artifacts`），`gh api` 退出 1，身份复算未开始。
     （同样的 URL 写法也存在于 `tests/reader_raw_store_companions/strict.py`，不属本包，
     未改动，仅作观察上报。）

两个缺陷**留档未修**：三轮额度已满，若在最后一轮之后改代码，"源码 == CI 跑过的源码"就对不上，
反而比保留失败更糟。修法各一行，留给 root 决定是否开第 4 轮：
- `run.py:217` → `assert report['accepted'] and not report.get('adopted', False)`
- `strict.py:49` → `.../actions/runs/<id>/artifacts?per_page=100`

## 6. 未验证 / 不作承诺

- 5 条混装拒绝（源构建双向、已装包双向版本拒绝、已导入 legacy target 被 raw 包重标）**未执行**；
- 包级 `result.json`（`accepted` / `raw_symbols_absent_from_default` / `mixed_profiles_refused`）**未产出**；
- 工件 ZIP 的 size/digest/过期/内层报告同源身份**未复算**；跨平台具名检查**未由汇总器断言**
  （两份日志各自列出相同的 20 + 22 条，但这只是读日志，不是聚合断言）；
- macOS、Debug 配置未跑；真实 Windows/GTK/Apple/Android 宿主未接线（`actual_hosts=false`），
  物理设备、完整产品均未验证；
- 本包无 SDK patch、无 schema/wire/anchor 改动、未改 root 宿主、旧裁判、其他包或冻结树；
- 未开 PR、未打 tag/Release，未使用额外 agent，未使用 cpuse。

## 7. 复现

`@
python tests/reader_next_s17/run.py      # 两套家族 + 两套消费者 + 混装矩阵 + 两套验收
python tests/reader_next_s17/strict.py   # 同 source/run/attempt 的工件身份与 ZIP 复算
`@

两个脚本都要求 `GITHUB_ACTIONS=true`；本包遵守"仅 Actions"，本地不跑构建/语法/测试/工件解析。
