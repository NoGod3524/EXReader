# S17 — 同步状态视图的 raw 家族兼容

状态：源码与验收脚本已就位；真实 CI 证据见本目录 `validation.json`（CI 之后写入）。
本文件只描述设计与代码约束；任何"已通过"的结论必须由 GitHub Actions 的
run/attempt/jobs 与工件身份支撑，不在文档里预支。

## 1. 范围与所有权

| 项 | 内容 |
| --- | --- |
| 固定起点 | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` |
| 批准 SDK 3.41 | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（本包不改） |
| 冻结旧 SDK 3.40 | `9854061be331fe603a1822d9b2b36ee357154927`（本包不改） |
| 独占写入 | `apps/reader/sync-status-view/`、`tests/reader_next_s17/`、`.github/workflows/reader-next-s17.yml`、`docs/reader-next-s17/`、`HANDOFF-RESULT-S17.md` |

七个 raw 模块（revisions 0.4 / sync 0.2 / session 0.2 等）、产品 schema、wire
envelope、旧 anchor、旧裁判与旧测试目录全部按原样复用。`tests/reader_next_s17/run.py`
在 Actions 里用 `git diff --exit-code` 对 `src include cmake CMakeLists.txt`（即批准
SDK 3.41 的树）以及 `apps/reader/store`、`apps/reader/revisions`、
`apps/reader/sync`、`apps/reader/session`、`extras`、`examples`、
`tests/reader_sync_status_view`、`tests/reader_revisions`、`tests/reader_sync`、
`tests/reader_session` 逐条断言未改，并按路径白名单拒绝任何越界改动。

## 2. 改动（3 个文件，都在本模块内）

1. `include/reader_sync_view.h`
   - `READER_SYNC_VIEW_VERSION` 变成显式家族宏：默认 `0.1.0`，定义
     `EXR_READER_SELECTOR_BYTES_CANDIDATE` 时为 `0.2.0`（与 session / sync /
     revisions / commands 等已接纳模块完全同一写法）。
   - 文档段落新增 *Capability*：安装家族决定读 pending 与 heads 的入口点；默认
     家族读 `reader_revisions_open` 的句柄，raw 家族读
     `reader_revisions_open_raw_v3` 的句柄。本模块**不读任何私有字段**：另一
     家族的句柄由 revisions 自己拒绝（`READER_REV_ARGUMENT`），视图随即以
     `READER_SYNC_VIEW_REVISIONS` 失败并把 `*out` 留空。
2. `src/sync_view.cpp`
   - 只有两处读调用改为编译期选择：匿名命名空间里的 `read_outbox` /
     `read_heads` 薄包装，定义 `EXR_READER_SELECTOR_BYTES_CANDIDATE` 时调用
     `reader_revision_outbox_raw_v3` / `reader_revision_heads_raw_v3`，否则调用
     原入口。与 `apps/reader/session/src/session.cpp` 里
     `auto advance=reader_sync_step; if(raw_api)...` 同源；但视图不需要运行时
     构造器，家族在安装期已经定死。
   - 其余语义一字未改：一次 `reader_session_observe`、一页 outbox、至多
     row_limit 次 heads、冲突探测读不到就整体失败、快照拥有全部内存、release 幂等。
3. `CMakeLists.txt` 与 `EXReaderSyncViewConfig.cmake.in`
   - `option(EXR_READER_SELECTOR_BYTES_CANDIDATE)` 默认 OFF；版本 0.1.0/0.2.0；
     `find_package(EXReaderSession ${EXR_SESSION_VERSION} EXACT)`。
   - 目标级家族校验（与 sync / session / commands / annotation-view 同一段模板）：
     源构建校验 `EXReaderSession::reader_session` 的
     `INTERFACE_COMPILE_DEFINITIONS`；安装包在 config 里对
     `EXReaderSession::reader_session` 与 `EXReaderSyncView::reader_sync_view` 一并
     校验，并追加 `_exr_raw_guard_target`（头部版本串 + 头文件/归档来源前缀）。
   - `target_compile_definitions(reader_sync_view PUBLIC EXR_READER_SELECTOR_BYTES_CANDIDATE=1)`
     只在 raw 家族生效，因此 C 与 C++ 消费者都能看到家族宏。

**没有新增公共 API，也没有新增运行时构造器**：视图的输入输出结构、枚举、错误码
与 0.1.0 同构；raw 与 legacy 的差别只是编译期选哪个 revisions 入口。

## 3. 为什么不需要新 API

`reader_session_snapshot` 在 0.2 里没有新增字段。raw 会话
（`reader_session_create_raw_v3`）复用同一个 `reader_session_observe` 与同一套
`attempt / completed_sweeps / steps / pushed / pulled / originals_verified /
pending_metadata_observations / pending_original_observations / transfer_bytes /
shard / completed_shards / after / state / error`。真正需要"家族化"的只有
**revisions 句柄的读取入口**（raw store 拒绝 legacy 入口，反之亦然），而这正是
CMake/config 家族切换加两个编译期内联包装能解决的问题。按任务要求"若只需
CMake/config 切换就不造新 API"，因此不造。

## 4. 安装与消费者矩阵（仅 Actions）

`tests/reader_next_s17/run.py` 在 Windows 与 Linux 上各装**两套完整家族**：

| 家族 | revisions | sync | session | sync-status-view |
| --- | --- | --- | --- | --- |
| 默认（legacy） | 0.3.0 | 0.1.0 | 0.1.0 | 0.1.0 |
| 显式 raw | 0.4.0 | 0.2.0 | 0.2.0 | 0.2.0 |

- **默认家族**：装完后构建**原封不动**的 `tests/reader_sync_status_view/consumer`
  （C 与 C++），再跑**原封不动**的
  `tests/reader_sync_status_view/check_status_view.py`（22 条具名检查，含
  metadata_wait 正向、owner 违规、256 分片、产品库字节不变、证据不含凭据）。
  这是"默认 legacy 不变"与"原完整套保留"的直接证据，且旧裁判未被改动。
- **raw 家族**：装完后构建 `tests/reader_next_s17/consumer`
  （`raw-view-consumer`、`raw-view-c-consumer`、`raw-revision`）。C 消费者保留
  原 28 条参数/生命周期断言并追加家族断言（view/session/sync/revisions 版本与
  `EXR_READER_SELECTOR_BYTES_CANDIDATE`）；C++ 驱动保留原命令边界并新增
  `profile`、`mirror`、`open-legacy`、`capture-legacy`。

**混装拒绝**（5 条，全部断言 CMake 真的失败并给出预期诊断）：

1. 源构建：raw 视图 + 只装 legacy 的 session；
2. 源构建：legacy 视图 + 只装 raw 的 session；
3. 已装包：legacy 视图 0.1.0 被要求匹配 raw 安装树 → `EXReaderSyncView` 版本拒绝；
4. 已装包：raw 视图 0.2.0 + 只装 legacy 依赖 → `EXReaderSession` 版本拒绝；
5. 已导入 target 混用：先导入 legacy 链，再把各 `_DIR` 指向 raw 安装，只剩 target
   属性可判 → `legacy capability family` 拒绝（共享 `_exr_raw_guard_target`）。

## 5. raw 家族的真实 TLS 验收（20 条具名检查）

`tests/reader_next_s17/check_raw_view.py` 使用临时自签 CA（IPv4 回环 + IP SAN，
只信任测试证书，**不关闭 TLS 校验**）、真实 `reader_session`、真实 raw revisions
句柄与真实 HTTPS WebDAV 夹具，覆盖：

- 家族/版本/能力宏显式（`profile`）；空闲只读快照不产生任何请求；
- 空 pending 页与原有参数契约；
- **视图与 session 原值逐字段一致**（16 个镜像字段 + 阶段映射 + sweep/resumable
  派生位），在 idle / syncing(阻塞) / cancelled / sweep-complete / failed / closed
  等静止态各取一次 `mirror`（同一条命令里先 capture 再 observe）；
- 取消保留真实 cursor 与 100 条已收 raw 历史，续跑代际（attempt=3）完成 256 分片；
- 一次完成的 sweep 不等于库已完整（`library_complete==0`）；
- raw outbox 分页按 distinct 记录计数、冲突探测 opt-in、retry token 来自模块码；
- 另一家族句柄被拒绝且不留快照；
- row_limit 上界与默认、owner 违规失败关闭、无句柄多线程 capture；
- 真实发布 + ack（outbox 清空）；
- 401 → `needs-credentials`、不可达 → `offline`、closing/closed 仍可观察；
- 快照活过 session 与 revisions 句柄、release 幂等；
- **重复 capture 后产品库字节完全一致且不新增任何文件**（含无 `*.tmp`）；
- 证据内不含 Authorization、secret、服务端正文或源 URL。

## 6. 明确未验证 / 不作承诺

- 真实 Windows / GTK / Apple / Android 宿主未接线（`actual_hosts=false`）；本包只
  交安装家族、模块与真实 TLS 进程级验收；
- macOS 配置未跑（任务只要求 Windows/Linux 至少双配置）；
- 只跑 Release，未跑 Debug；
- raw 家族下除 revisions/sync/session 之外的其它模块未重新验收；
- 任何新 SDK patch 产物都标"未接纳候选"，即使版本字符串未变（本包无 SDK patch）。

## 7. 复现

`@
python tests/reader_next_s17/run.py      # 两套家族 + 两套消费者 + 混装拒绝 + 两套验收
python tests/reader_next_s17/strict.py   # 同 source/run/attempt 的工件身份与 ZIP 复算
`@

两个脚本都要求 `GITHUB_ACTIONS=true`；本包遵守"仅 Actions"，本地不跑构建与测试。
