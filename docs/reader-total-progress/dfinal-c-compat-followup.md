# F12：产品旧目录库的当前原生打开回归

## 目标与证据口径

v1 没有独立 `acceptance` 字段。目标原文是
`docs/reader-total-progress/catalog.json:1738` 的「最终版本升级/旧库兼容、许可/依赖与用户安装/导入/同步说明完备」。
产品计划 `docs/READER-PRODUCT-PLAN.md:5` 明确六个目标，`:153` 包含本机映射、分类和离线待同步数据，
`:155` 要求修订/outbox 与中断重试，`:157` 要求同一源码及各平台独立证据，`:185` 要求平台安全凭据。

**verified 门槛：最终共同源码的六端宿主能保留并打开旧原件、记录、产品数据及待同步状态，完成平台升级/恢复核查，并随实际分发包交付完整依赖许可与安装、导入、同步说明。**

## 已有证据与本次补充

| 范围 | 已有证据 / 最近已记录的真实结果 | 本次补充 |
|---|---|---|
| SDK 旧库 | `tests/test_library_epub_storage.c:170`；`evidence/dfinal-c/ctest-full-actions.txt` 与 `actions-model-full-success-43648272236.txt`。源码 c0b07a69 / Actions43648272236 的 schema1–6→7 保留、回滚、复开和实际 TXT 文档打开通过，完整存储套件2765检查；全量580/580。 | 保留已有 SDK 回归，新增独立产品目录库覆盖。 |
| Web 旧格式 | `docs/validation/wp12-migration-run39709534123-a1/summary.json`：Linux/Windows 各65/65场景、135/135检查，浏览器端 e2e 通过；文件明确真实用户库、macOS、Tauri profile 等未测。 | 不转授为最终原生宿主兼容。 |
| Apple 旧记录 | `docs/READER-APPLE-RECORD-COMPATIBILITY.md:9` 的40176647484：18进程阶段、两个SDK各19 owner检查及20+6策略正反例通过；`:38` 将范围限于macOS owner。 | 不转授 iOS 或六端完整升级。 |
| 产品目录 | `apps/reader/store/native/catalog.c:104` 打开时识别 EXRP 身份及 schema1/2/3，按 `002_originals.sql`、`003_original_staging.sql` 升级。原 `tests/reader_catalog/originals_check.c` 只在 v1 空原件的简单映射上进入当前版本。 | `tests/dfinal_c/check_catalog_upgrade.py` 用原始历史 SQL 生成带真实表约束的v1/v2库；当前安装后的 C provider 真实打开，不在 Python 中执行被测升级。 |
| 许可及说明 | `docs/READER-DISTRIBUTION-INVENTORY.md:14` 的40095313750九份历史安装材料通过，`:15` 发布就绪未授予。上轮 `evidence/dfinal-c/license-checker-tests.txt` 中清单22组件、31负例自检通过。用户说明在 `docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md`。 | 用户说明补充产品逐段事务失败的中间版本与凭据备份边界；沿用已有固定依赖清单及检查器。 |

## 新测试的实际范围

`dfinal-c-product-catalog-upgrade` 由 `tests/dfinal_c/CMakeLists.txt` 注册，
`tools/run_dfinal_c_models.py` 的统一安装/编译/CTest 路径自动运行。

- v1与v2分别迁移到3，再经另一个原生进程重开；逐行核对标题/作者/收藏、SDK ID/模式、书架/标签/系列及关联、原修订字节/删除墓碑、outbox queue ID/尝试次数/错误文本不变。
- v2原件 `ready`、`staged`、`deleting` 三状态和 storage_ref 原样保留。
- 对1→2、1→2→3、2→3分别注入 CREATE 同名表冲突，核对失败事务回滚、冲突哨兵及旧行保留；测试移除人工冲突后，新进程重试完成3且 outbox 不丢失。
- 未知未来 schema4 被当前公开 provider 拒绝，关闭所有句柄后对比整个数据库文件字节不变。
- 成功后经公开 API 读回旧标题、作者、收藏及SDK映射，并检查 SQLite integrity / foreign keys。

原生 consumer 为 `tests/dfinal_c/catalog_upgrade.c`，链接安装后的 `EXReaderProductCatalog::reader_catalog`。
保留各数据库、进程stdout/stderr及 `result.json` 到模型 `results/catalog-upgrade-*`；统一运行的真实输出见本轮主报告。
夹具直接在历史 SQL 布局内写入存储层数据，修订 wire 的语义验证由已有 revisions 套件承担；本测试证明迁移保留原字节。
注入 SQL 失败模拟的是确定的事务边界，不是实际进程 kill 或断电。

## 最终仍缺的产物

| 平台 | 缺失产物 |
|---|---|
| Windows / macOS / Linux，分别 | 旧宿主可执行文件及其实际产生的 SDK 库、产品库、原件、设置和 outbox；最终新宿主升级、退出/重启及中断恢复日志，凭据可用性和重认证界面结果。模块 CTest 不能代替此流程。 |
| Android arm64 / iPhone / iPad，分别 | 上述旧→新安装升级及数据核查，加应用身份/签名、安全存储、系统文件授权和真实设备恢复结果；需真机与相应打包 runner。 |
| 最终六端分发包 | 实际包逐文件清单、完整依赖/字体/平台组件的许可和 SBOM、材料随包交付记录，且安装/导入/同步说明能按各平台实际包操作。 |

F12 继续 pending。新增产品目录回归减少自动验证缺口，不授予最终六端宿主升级。
