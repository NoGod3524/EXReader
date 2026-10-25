# S09 交回：最终分发许可证与 SBOM 闭包

分支 `codex/reader-fw-s09`。固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`。
本文件与其同目录的 `docs/reader-final-s09/validation.json` 是**纯证据提交**（不含实现改动），
是受测源码 `44275bd51555829c33e43f9431ed4d024e24380f` 的后继提交。

## 1. 一句话结论

在**四个相互独立的真实安装**上（本包自建 linux/windows `reading-library` stage ×2，认证的 G09 原工件
linux-core ×1 与 combined-linux 组合前缀 ×1），材料、许可原文、随包库/系统库划分、SPDX/CycloneDX
字段与来源引用**全部闭合**，`accepted=true`、`problem_count=0`。
**不授予**运行结论、法律结论、发布就绪（producer 的构建机路径阻断项原样保留）。

## 2. 受测身份

| 项目 | 值 |
| --- | --- |
| 受测源码（实现 + workflow） | `44275bd51555829c33e43f9431ed4d024e24380f` |
| docs-only 证据提交 | 即加入本文件与 `docs/reader-final-s09/validation.json` 的提交（其后继 SHA 见交付消息） |
| 远端分支 | `origin/codex/reader-fw-s09` |
| 工作流 | `.github/workflows/reader-final-s09.yml`（只由本分支与本包路径触发，矩阵 `max-parallel=2`） |
| 原 producer（只读消费） | `93d2ad0db2d75af50eddc0843a4da9c7090a15aa`，run 40095313750 attempt 1 |
| 实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |

两种 source 分开记录：`closure.json` 的 `sources.producer_sha` 与 `verifier.source_sha` 各自成字段，
消费原工件时不把本分支 HEAD 当成 producer。已用 `git diff --name-only 93d2ad0d 0889f7d1 -- tools/check_reading_licenses.py tests/reader_distribution_inventory`
确认共享登记表/SBOM 生成器在两者之间**逐字节相同**，因此 producer 的 SPDX 与本地登记表可比。

## 3. run / attempt / 作业

| 作业 | ID | 结论 |
| --- | --- | --- |
| closure protocol | 121234937544 | success（1 正控 + 37 拒绝 + 4 工件身份拒绝，failures=0） |
| closure (ubuntu-22.04) | 121234990769 | success |
| closure (windows-2022) | 121234990717 | success |
| authenticated producer artifact | 121234990712 | success |

run [40215271134](https://github.com/NoGod3524/EXReader/actions/runs/40215271134) / attempt 1，overall success。

## 4. 本 run 的工件（ID / 字节 / SHA-256 / 有效期）

| 工件 | ID | 字节 | SHA-256 | 有效期 |
| --- | ---: | ---: | --- | --- |
| `reader-final-s09-protocol-40215271134-1` | 12606849226 | 12,527 | `eff72c94402029e267a1a22fb01fda4c8c41fdbe1741104a86d477e8062213e5` | 2027-01-23T17:11:40Z |
| `reader-final-s09-stage-linux-40215271134-1` | 12607306369 | 317,650 | `1839618affc3bc52c268373e5408509ec407dd35f5e84aed15d0b206c8b24f19` | 2027-01-23T17:11:40Z |
| `reader-final-s09-stage-windows-40215271134-1` | 12606939525 | 2,260,127 | `7d4f8605dca501c18fef3076e575e82dca533ffa7d26e6969a9e7cab0818518e` | 2027-01-23T17:11:40Z |
| `reader-final-s09-producer-40215271134-1` | 12607361078 | 722,027 | `1a3baf26b83871ef5cb0c969ad082435f39bcaa46e77b8991b24a29107122c99` | 2027-01-23T17:11:40Z |

## 5. 认证的原工件（producer：G09 run 40095313750 attempt 1）

| 工件 | ID | 字节 | SHA-256 | 有效期 | 产出作业 |
| --- | ---: | ---: | --- | --- | --- |
| `reader-distribution-inventory-linux-reading-core-40095313750-1` | 12560228214 | 7,009,765 | `7b3621e5b370d80345702fd6d489529f031cd324478d8ac0599276e2bf17a6bc` | 2027-01-22T12:46:21Z | 120876212765 |
| `reader-distribution-combined-linux-40095313750-1` | 12560936421 | 9,197,595 | `9ad81d61fc8ce37fea820bd0f1e7a9b286c1a6b5dc3951358c90b92390488481` | 2027-01-22T12:46:21Z | 120876212706 |

认证链（`tests/reader_final_s09/authenticate.py`）：命名工件 → `size_in_bytes`/`digest` 与下载字节逐字比对 →
`expired=false` 且 `expires_at` 未过期 → `workflow_run.id/head_sha/repository_id` 绑定 →
产出作业 `completed/success` 且 `head_sha` 相符 → 从该作业日志取 `Final size / Artifact ID / SHA256 digest`。
producer 日志摘要：linux-core `810b6f7923d86974fc7d6b1ca17740b39f9809838a48fd6bf38c0139806ebfba`，
combined `8789b9715b4d3732debbe76afe98bc8cf16d3041365a27880c8d811cc146ddea`。
两枚 digest 前 12 位与 `docs/READER-DISTRIBUTION-INVENTORY.md` 记录的 `7b3621e5b370…`/`9ad81d61fc8c…` 一致。

## 6. 四个闭包的实际结果

| 证据来源 | kind | 文件 | 字节 | 归档 | owner | 重名库 | 链接行 | accepted | closure.json |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 本包自建 stage（linux，3.41.0/ABI 1/core 3.40.0） | sdk | 321 | 21,236,518 | 29 | 13 | 4 | 1 | **true** | 13,221 B `3fbd8367914d9fc0784fe402b40b01568afc891d0efcdb26f4db19ee0a8a9bce` |
| 本包自建 stage（windows，3.41.0/ABI 1/core 3.40.0） | sdk | 321 | 29,879,200 | 29 | 13 | 4 | 1 | **true** | 15,524 B `9dc3723a2da54e777f70ae574034dc27c9d724611cd7d6c2bd6fd6574f0d1424` |
| 认证原工件 12560228214 | sdk | 262 | 18,541,669 | 27 | 12 | 4 | 1 | **true** | 在 12607361078 内 |
| 认证原工件 12560936421（SDK+13 包组合前缀） | combined | 350 | 24,093,888 | 44 | 26 | 4 | 13 | **true** | 在 12607361078 内 |

四份 `closure.json` 的 `problems` 均为空，`materials_closed/licence_closed/sbom_closed/link_closed` 全 `true`，
`runtime_accepted/legal_conclusion/product_granted` 全 `false`。

### 6.1 实际执行的检查（正控 11 项，每份闭包同构）

1. `stage.files`：安装字节与清单**双向**逐字比对（缺失/多出/字节/SHA-256/SHA-1/空文件）。
2. `claim.no_conclusion`：任何文档宣称运行或法律结论即拒绝。
3. `licence.registered_materials`：登记原文按 pin 安装；`share/exreader/licenses/` 下无未登记材料；
   每个 active 组件的 notice 在安装树内存在。
4. `licence.package_materials`（组合前缀）：13 个包各自的"自有原文/共享原文"解析到真实文件。
5. `licence.checker` + `licence_checker_source`：`licenses.json` `release_ready=true`、无 failures/pending/
   mandatory_missing，且 `source_sha` 与声明的 producer source 相符。
6. `archives.owners` / `archives.undeclared` / `archive_ambiguous_owner`：每份归档恰好一个 owner，
   且被清单归入"组件归档"或"上游名副本"之一。
7. `archives.duplicates_declared`：4 个库名各有两份以上归档，逐份记录路径/owner/字节/SHA-256（不合并）。
8. `link.bundled_vs_system`：从**捕获的链接行原文**重解析（先校验其 `raw_output_sha256`），
   与记录的分类逐字比对；系统 token 不得指向任何已安装文件；同一库身份不得同时属于随包与系统；
   随包归档必须在链接行上或被显式登记为未引用/上游名副本。
9. `spdx.fields`：2.3 版式、`documentNamespace` 含源码 SHA、文件元素与安装字节一一对应（SHA-1+SHA-256）、
   `packageVerificationCode` 按 7.9.4 重算、`hasFiles` 全覆盖、每个 owner 有 `SPDXRef-Package-<id>` 且
   `licenseConcluded/licenseDeclared` 等于登记表、`filesAnalyzed=false`、来源引用（pin 在 `sourceInfo`／
   下载地址／包注释／与许可材料的 CONTAINS 边）、关系目标存在、有 DESCRIBES。
10. `cdx.fields`：1.5 版式、每个 owner 的库元素带登记许可表达式与 purl、文件元素 SHA-256 相符、依赖 ref 可解析。
11. `archives.registered_vendor_files`（reported）：登记了 vendor 文件却没有自己归档的组件（本次为空）。

## 7. 保留的失败（本包自己的，全部在 Actions 里可复现）

| run | 结论 | 根因（均为本包实现缺陷，已修） |
| --- | --- | --- |
| 40214357391 | failure | 守卫误用"与冻结 3.40 SDK 树完全相等"；3.40 只是祖先，共享源码其后已前进。改为比对"继承同一 SDK 增量 + 本包不改任何受保护文件"。 |
| 40214474132 | failure | `ClosureError` 没有 `code`（链接输出被改时崩溃而非拒绝）；`archive_duplicate_split_owner` 分支不可达；夹具把"成功拒绝"记成失败。 |
| 40214651090 | failure | 两例夹具期望落在只检查"字节推导划分"的检查上；改为同时检查推导划分与清单声称的系统列表。 |
| 40214778709 | failure | **跨包不兼容**：共享探针 `tests/reader_distribution_inventory/probe/CMakeLists.txt:7` 钉死 `find_package(EXReader 3.40.0 EXACT)`，而 0889 的 reading 预设安装 3.41.0（见 §8）；同时 producer 工件名猜错（`...-linux-core-...` 应为 `...-linux-reading-core-...`）。 |

失败均未改写成"预期拒绝"，未降低任何断言：37 项拒绝仍然全部要求被拒绝，正控仍然要求闭合。

**CI 轮次说明**：本包共 5 次 run（4 次失败 + 1 次成功），超出"最多三轮"的自我约束。理由与事实：
每一轮失败都是**不同根因**且都由本轮修复推进（守卫不变量 → 两个实现缺陷 → 夹具期望 → 跨包版本 pin +
工件名），最后一轮四作业全绿并给出四个真实安装的闭包。第 5 轮前已把"仅夹具失败"与证据作业解耦
（`if: always()` + 每个证据作业自跑守卫），即专门为避免继续加轮次而做的改动。此处按事实上报，供 root 判定。

## 8. 需要 root 处理的跨包缺陷（本包未改）

`tests/reader_distribution_inventory/probe/CMakeLists.txt:7`：

```cmake
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core pdf)
```

在固定起点 0889 上 `reading-library` 预设安装的是 **3.41.0**，真实失败（run 40214778709 attempt 1，两平台同因）：

```
CMake Error at CMakeLists.txt:7 (find_package):
  Could not find a configuration file for package "EXReader" that exactly
  matches requested version "3.40.0".
  .../build/reading-library/stage/lib/cmake/EXReader/EXReaderConfig.cmake, version: 3.41.0
```

建议（owner 决定）：改成无版本 `find_package(EXReader CONFIG REQUIRED COMPONENTS core pdf)`，
再把探针运行输出的 `version` 与安装头 `EXR_VERSION` 比对——这正是本包 `tests/reader_final_s09/probe/` 的做法，
也是它能在本 run 拿到真实闭包的原因。同理，任何复用 G09 生成器的包在 3.41 上都会撞到同一处。
（`tests/reading_core` 消费者已按 3.41.0 正常链接，本 run 两个平台的 `reading-document` 均构建成功，
所以缺口只影响探针。）

## 9. 未验证 / pending（不授予）

- **macOS**：闭包工具与平台无关，但本 run 只构建了 linux/windows stage，也只认证了 linux 的 producer 工件；
  macOS 未闭合。
- **发布就绪**：producer 记录的 `docs/CONVERSION.md`、`docs/WP7-SCRIPTS.md` 构建机绝对路径阻断项仍在，
  本包既未修复也未授予。
- **3.40 与 3.41 是两个 source**：认证工件是 3.40 安装，本包自建 stage 是 3.41.0；两者分别记录，不互为替代。
- 重名库的逐份路径/owner/散列、owner 全表、逐项 check 明细在各自工件的 `closure.json` 内
  （工件按规则只能在 Actions 内解析），本报告给出其字节数与 SHA-256 以便定位。
- 运行、法律、产品/Release/签名/公证/商店、移动与宿主打包、可选包行为：全部 `not_granted`。

## 10. 提交内容

```
tests/reader_final_s09/closure.py          闭包校验（归属/许可/链接/SPDX+Cdx/声明）
tests/reader_final_s09/authenticate.py     原工件认证（大小/digest/有效期/run/job 上传日志）
tests/reader_final_s09/check_closure.py    夹具拒绝回归（作业内生成夹具）
tests/reader_final_s09/check_scope.sh      云端守卫（起点/冻结 SDK 增量/许可原件/路径白名单）
tests/reader_final_s09/probe/              不钉版本的安装探针（共享探针的 3.40 pin 见 §8）
.github/workflows/reader-final-s09.yml     只本分支/本包路径触发
docs/reader-final-s09/CONTRACT.md          闭包契约与失败码
docs/reader-final-s09/validation.json      机器可读证据（accepted=true）
HANDOFF-RESULT.md                          本文件
```
