# S18 交接结果：五模块共同安装验收

结论：**共同安装验收通过**（Windows/Linux/macOS 同 source、同一 SDK 3.41.0 provider、default 0.1.0 与显式 raw 0.2.0 两族真实安装，并重放 C06/S14/S15/S16/S17 原有业务判定）。本包只交付「共同安装 + 原业务重放」这一限定授予；未提升 BASE、未接入产品 DSO/host、未做 PR/tag/Release/默认分支。

## 受测身份

| 项 | 值 |
| --- | --- |
| 受测完整 source | `4af92ba023aa64b3ca6db993f2c7b9cec208e326`（分支 `codex/reader-wave3-s18`） |
| 固定 seed | `d263ce5228838ac90c0a0dc13a5193d4a7739681` |
| 运行 | Actions run `40247961052` / attempt `1`，6/6 job completed/success |
| 最终文档 HEAD | 本文件所在提交（docs-only，提交信息带 `[skip ci]`，不触发新功能运行） |
| 原代码 | SDK 候选 `edddc463`(3.41.0)、冻结 `9854061b`(3.40.0)、旧起点 `e67d87cb`、旧 importer `9c7e276f` |
| 认证的 Mac 记录工件 | run `40196978163` artifact `12600789926`，zip `92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5` |

## 工件身份（同 run 同 attempt，均为本次真实上传）

- `reader-wave3-s18-source-40247961052-1` id 12619296639，2008 B，`sha256:0021463f…0329d8`，2027-01-24T00:09:21Z 到期
- `reader-wave3-s18-source-summary-40247961052-1` id 12619910787，2130 B，`sha256:125af63f…cb3198`
- `reader-wave3-s18-runtime-Linux-40247961052-1` id 12619262704，48 679 812 B，`sha256:ec3e5f7a…b7d566de`
- `reader-wave3-s18-runtime-Windows-40247961052-1` id 12619317686，37 628 080 B，`sha256:db0eb254…89936b1`
- `reader-wave3-s18-runtime-macOS-40247961052-1` id 12620225857，41 811 896 B，`sha256:6ce94720…e59ec1a`
- `reader-wave3-s18-runtime-summary-40247961052-1` id 12619537636，1206 B，`sha256:b3f7a6ac…8e344d2a`

（完整 digest 与逐平台数字见 `docs/reader-wave3-s18/VALIDATION.md`。所有证据均来自本 run/job/attempt，未拼接其它 run 的源码结果。）

## 实际通过范围

1. **联合安装（每平台）**：SDK 3.41.0 与冻结 3.40.0 各自从固定 commit 的隔离副本构建安装；product catalog / WebDAV / sideload 装入 shared 前缀；default 与 raw 两族各 11 个包装入独立前缀，安装后逐一核对 `*ConfigVersion.cmake` 版本（revisions 0.3.0/0.4.0、reading-state 0.1.0/0.2.0、commands、sync、session、annotation-export/import、font-library 0.1.0、original-export 0.1.0、jump-history 0.1.0/0.2.0、sync-status-view 0.1.0/0.2.0）。
2. **同图共同安装证明**：每族一个 CMake 图同时导入六包 + 唯一 SDK provider；每族 62 条实际 imported 路径（location/implib/include）全部落在 family/shared/SDK 三个声明前缀内，链接的 `EXReader::exr_library` 位于 SDK 前缀，无生成表达式被当作路径放行（上一轮旧 runner 正是在这里因 `$<TARGET_PROPERTY:…>` 而失败，本次驱动先跳过 genexp 再校验绝对路径）。
3. **C06**：baseline（旧起点导出 + 固定 importer）/default/raw 三套 legacy 导出 JSONL 与 Markdown 字节完全一致（每平台 sha256 `ac5028e4…`，且三平台相同）；raw3 相位（PDF 真实 NUL/空值/锚点 1-3、拒绝矩阵、预算/取消/续传、无写库）；真实 Mac 记录经 GitHub API 认证后导出/预览/提交（3 head、1 NULL head、anchor 1/2/3，`found_checked=0` → 明确记为 ALREADY_VERIFIED，未冒称 FOUND）。共 199 项。
4. **S14**：原 run.py 全套（60 Linux/macOS、61 Windows）+ `preloaded.py` 4 项已有 target 正反 + `verify.py --self-test` 42 条负例契约（4 个合成平台全部接受、42 变异全部拒绝）。
5. **S15**：`check_export` 44 项（含平台故障注入项）、`check_frozen_sdk` 6 项（3.40 默认钉住、显式 3.41 被拒、C ABI/原件字节/不覆盖）、`check_install_graph` 4 类负例、`check_existing_targets` 16 项既有 target 控制（8 拒绝 + 8 接受）。
6. **S16**：原 149 项在 baseline/default/raw 三个安装上各跑一次，raw 162 项、default 21 项；九角色程序与三份 jump-history 归档身份；baseline↔default 投影逐字段等价；四类混配在 configure 期被拒（含仅改 version 文件的伪造前缀）。
7. **S17**：原 22 项 legacy、20 项 raw（profile `view/session/sync/revisions = 0.2.0/0.2.0/0.2.0/0.4.0`，16 个镜像字段）、5 类混配拒绝（含"先导入 legacy target 再用 raw 元数据"路径）。
8. **严格层**：`strict.py` 重新下载三份 ZIP，核对 size/digest/有效期/head_sha/attempt，逐成员、逐程序哈希、逐报告与业务数字；对每平台执行 15 个真实字节变异（覆盖 9 个程序、3 份报告 + attempt + 程序身份 + 缺成员），45/45 全部拒绝；三平台 S17 命名检查完全一致、legacy 字节跨平台一致。
9. **原 guard 未执行**：C06/S14/S16/S17 的旧 branch/ownership guard 一个都没有运行（它们断言各自分支的独占 diff）。新 guard 声明 seed 与精确自有路径，逐路径比对 seed 全树，8 个真实变异（sdk/package/raw/host/root CMake/旧裁判/未知路径/symlink 模式）全部拒绝，另有 1 个"自有路径新增"正例被接受；SDK 树、11 个包树、9 个旧裁判树对象与 seed 逐一同源。

## 保留的失败与缺口

- 本轮之前的两条原失败保留：`40240222437/1`（Linux 缺 libcurl）、`40240645276/1`（共用 consumer 拒绝 SDK 生成表达式 include 路径）。我没有复用其 workflow/manifest/工件，也没有重写它们。
- 本包自己的两轮失败保留：`40245930197/1`（S14 契约 JSON 前有 UserWarning 致解析失败、S16 证据路径 `Path + str` 类型错误、runtime 退出码未反映失败）、`40246888203/1`（strict 从阶段记录而非报告读 `legacy_all_equal`）。都是我驱动层缺陷，未改产品/旧裁判；第三次运行为上述绿轮。
- 原 S16 的 15 个变异控制绑定它自己的 job/artifact 名字，无法原样运行；这里以同数量 15 个真实字节变异在我的工件上执行，并在 strict 里记录每个变异名与拒绝条数。S16 `check_artifacts.py --protocol-selftest` 未重复运行（避免再造第二套元数据协议）。
- S15 的 44 项 = cases.json 43 项 + 1 项平台故障注入（POSIX 中途写失败 / Windows 锁定清理失败）；沿用原判定语义，未改写计数。
- 未授予：BASE、产品 DSO、host 接线（UI/字体选择/历史/同步状态条的真实宿主）、PR、tag、Release、默认分支。raw 0.2.0 仍是显式候选。

## 平台说明

macOS 的 WebDAV 采用仓库既有 `EXR_WEBDAV_APPLE_URLSESSION=ON`（Foundation + 系统 LibXml2），因为 S17 fixture 的 CA 是通过系统钥匙串信任的；Linux 保持 libcurl、Windows 保持 WinHTTP，与各自历史验收一致。这一选择在 `docs/reader-wave3-s18/PLAN.md` 与运行日志里可见（macOS configure 日志显示 OBJCXX 与系统 libxml2）。

## 接入命令

```
# 源码与种子（本包自有路径之外必须与 seed 逐字节相同）
python tests/reader_wave3_s18/guard.py preflight

# 三平台联合安装 + 原业务重放（仅 Actions）
python tests/reader_wave3_s18/runtime.py

# 同 run/attempt 源码收据与三份运行时工件认证
python tests/reader_wave3_s18/guard.py strict
python tests/reader_wave3_s18/strict.py
```

产物根：`build/reader-wave3-s18/`（`source.json`、`strict.json`、`runtime/result.json`、`runtime/evidence/`、`runtime/programs/`、`runtime/logs/`、`runtime-strict.json`）。构建目录 `build/s18b/`，SDK 阶段目录 `build/reading-library/stage`、`build/s18b/sdk340-src/build/reading-library/stage`，两族安装前缀 `build/s14-stage`（default）与 `build/reader-wave3-s18/raw-stage`（raw）。
