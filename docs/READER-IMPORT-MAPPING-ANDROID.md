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

本地仅编辑源码／文档与 Git；所有构建、语法检查、SQL、测试和工件解析均在
GitHub Actions。当前文档记录实现及验收出口，最终 run/source/artifact 尚待云端完成。

本包不实现产品书架分页、网络同步、远端冲突选择或六平台 UI。真实设备、签名和
TalkBack 保持单独验收。
