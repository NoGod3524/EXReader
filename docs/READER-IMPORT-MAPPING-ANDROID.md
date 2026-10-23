# Android 可恢复产品书库导入映射

基线：`c9870ed68df539b2f08cb889817cd81b3e2e8a6b`，独立分支
`codex/reader-import-mapping`。SDK 保护树保持冻结 K
`9854061be331fe603a1822d9b2b36ee357154927`；产品库仍为 EXRP/schema 1，SDK
书库仍为 schema 7。

## 导入与修复协议

1. 原有 worker 复制本地文件，保留复制过程的 SHA-256 和字节数。SDK 使用原有
   exact-unique 导入，`import-copied`、`import-inserted` 仍可取消。
2. 从公开 `exr_library_source` 分 64 KiB 读取 SDK 原字节，平台 `MessageDigest`
   再算 SHA-256、核对字节数。偏好中的路径不参与产品身份。仅通过
   `exr_library_epub_info_get` 决定 EPUB 的 `epub_chapter` 或 `reflow_global`，
   重复导入不推断或改变旧书模式。
3. `HostTask.commit` 成功后书籍已发布，随后在独立 SQLite 单事务附加
   `reader_books` 与 `reader_local_books`。主键为 `format:sha256`；相同身份只核对
   不可变源信息，保留既有标题、收藏、删除状态、修订、墓碑和 outbox。
   新行的 `sort_title` 使用 NFC 正规化，显示标题原样保留。历史非 unique SDK
   重复行统一保留最小 SDK ID 的本机映射及该 ID 的真实位置模式，不删除重复 SDK 行。
4. 发布前失败／取消只补偿本次 created 的 SDK 行和 owned 副本；重复旧行不删除。
   发布后产品 SQL 失败保留 SDK 行及原件，界面报告 metadata repair pending。
5. 重启仅扫描没有本机映射的 SDK ID，通过公开 books/source 重建，成功映射不重复
   哈希。所有宿主删除先删除本机映射，再删 SDK 行；第二步失败或中断可再次补建。
   全局产品元数据与历史保留，不产生虚构同步修订。
   Activity 重建时的启动恢复复用现有 `IMPORT_LOCK`，等待旧实例完成发布或取消补偿；
   复制路径复用前须核其 canonical 路径位于私有 books 目录，且原字节摘要／长度匹配。

## 云端出口

工作流 `.github/workflows/reader-import-android.yml` 在 API34 x86_64 模拟器运行：

- 原 catalog 8 项检查保持完整。
- 新 14 项真实 SDK／SQLite 检查，包括跨 64 KiB 哈希、删外部副本仍读 SDK 原件、
  幂等映射、元数据／历史保留、legacy/bounded EPUB、源读错、摘要／长度错、SQL
  拒绝的事务回滚、取消、已发布状态、本机 ID 冲突、NFC 排序及历史重复的最小 ID。
  历史行由 debug-only 桥接调用公开 `exr_library_import`／`exr_library_import_file`
  实际建立，分别验证最旧行是 legacy 或 bounded EPUB；不写 SDK 私有表。
- 两次独立杀进程：一次在 SDK 提交后、产品映射前；一次在 SDK 已提交且产品库
  已写入但尚未提交的 SQLite 事务内。新进程先证实产品行未发布，再经实际
  `BookStore` 启动修复，核原书摘要和幂等性。事务中断探针直接在同一 schema
  开启未提交写；生产 `attach` 的原子性另由 SQL 拒绝测试覆盖。
- `tools/check_reader_import_android.py` 严格核 exact case 集合、零失败零跳过、
  原始进程崩溃／恢复记录与同 run/source 身份。
- 另用新源码 dispatch 原 `.github/workflows/wp13-android.yml`，复验原 45+10+11
  用例与原证据拒绝门禁；旧通过项不转授。

## 冻结交付与同源结果

功能源码冻结为 `19128dc5f5e4a3164416ffa17e63937a3894989b`；后续文档提交
不转授其他源码验收。以下两组均为该源码、attempt 1，作业及严格汇总全部成功。

| 组 | 云端 run / job | 实际结果 |
| --- | --- | --- |
| 产品映射专项 | [40014701174](https://github.com/NoGod3524/EXReader/actions/runs/40014701174) / `120623650348` | 原 catalog 8/8、映射 14/14、真实杀进程恢复 2/2；零失败零跳过；`accepted=true, problems=[]` |
| 原完整 Android 宿主 | [40014701234](https://github.com/NoGod3524/EXReader/actions/runs/40014701234) / `120623655742` | 原 45/45、review 10/10、bounded 11/11；零失败零跳过；49 rendered pages、49 native next、0 recovery，顺序翻页 44,619 ms；原 48 项与 bounded 20 项证据门禁全过，最终 `accepted=true, problems=[]` |

工件身份已通过 GitHub API metadata 与同次上传日志核对，均非空、未过期，
`workflow_run.head_sha` 等于功能源码；未在本地下载或解析 ZIP。

| 工件 | ID | 字节 | SHA-256 |
| --- | --- | ---: | --- |
| `reader-import-android-40014701174-1` | `12527429754` | 17,246,360 | `66c93a6dbb5c3f7a28e2147af5b3a25fec6bd0c4225a480ee5ef1028938549a3` |
| `EXReader-WP13-Android` | `12528507540` | 157,930,976 | `c35fa1b72caf57d99e7e1d15111a203a2f1e64108ea2432b8c42289e0a88d43d` |

专项 APK 为 22,276,785 字节，SHA-256
`a5bfae037cd4b4c5f6800cb745e249d1808884b48d903569ebc76f487fd8da58`；
仪器化 APK 为 35,630 字节，SHA-256
`513e2b12f7e087dc6db18a048921239c3038981aa0eb0e322c736a7d12ae5d5f`。

### 旧候选与失败保留

| 源码 | 专项 run | 原完整宿主 run | 结论 |
| --- | --- | --- | --- |
| `c1ccbdda…` | `40011731293` | `40011746155` | 尚在 queued、零 steps 时请求取消；无测试或工件可转授 |
| `90c3ae569c84412257e4bef79fcb1e663e7208df` | `40012042781` | `40012043074` | 同次旧候选成功；不转授到新源码 |
| `f248fef00f477983c145bd0aa2e43e06ede16742` | `40012182562` | `40012182032` | 同次旧候选成功；不转授到新源码 |
| `72bbc5bd6c3072c904637724387cc515b03e7237` | `40012904851` success | `40012904324` failure | 原 45/45、review 9/10、bounded 10/11，严格汇总拒绝；失败身份为 `destroyed_activity_releases_worker` 与 `bounded_budget_limit_preserves_frame` |

失败原件 `12528106635`（156,876,456 字节，SHA-256
`bed03132d339d0b6d7330cbe8c9e57b9cdd900e74c1c8ad4d13ad7f2e9c5f5b6`）
继续保留。上述各轮使用新 run ID，未用重跑覆盖旧尝试，未删除失败工件。

### 恢复响应仍有独立缺口

云端只读诊断 `40015559943`、`40015789990` 与阶段 profile
`40016588193` 确认：旧失败停在大 EPUB 打开，首次 pager 建造在慢 runner
约 8.4–8.6 秒，真实 selector query 达到原 5 秒预算后，宿主关闭并重新完整
建造 pager，未赶上原 20 秒 UI 用例界限。`19128dc5…` 的同次通过证明本轮
功能与回归成功，不证明该慢路径成本已修复。

公开健康探测 run `40017556489` 进一步确认，query 取消后的 chapter reader
会返回 `EXR_CANCELLED`，不能安全删除 close/reopen 或继续复用失败 pager。
这些诊断均 `diagnostic_only=true, accepted=false`，不授产品验收。正常恢复的
CFI／point 缓存优化另开分支；缓存缺失、失效或篡改必须回到真实 TextQuote
解析，原 5 秒 query 与 20 秒 UI 断言保持不变。

本地仅编辑源码／文档与 Git；所有构建、语法检查、SQL、测试和工件解析均在
GitHub Actions。八条 SDK 保护树仍与冻结 K 逐项相同。

本包不实现产品书架分页、网络同步、远端冲突选择或六平台 UI。真实设备、签名和
TalkBack 保持单独验收。
