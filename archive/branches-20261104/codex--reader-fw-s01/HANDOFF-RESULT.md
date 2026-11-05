# S01 Windows 最终可迁移包核验 — 交回状态

分支 `codex/reader-fw-s01`（远端同名），固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`。
本文件所在提交是 docs-only 封存提交；受测源码是它之前的 `b8c973fea2d7370bc5bbb74d4e853805acdba580`。

## 结论

| 项目 | 结果 |
| --- | --- |
| 候选包结构、逐文件散列、许可归属、依赖来源 | **通过** |
| Unicode + 带空格目录迁移后实际运行（自检 26 项 + 原简洁版验收 22 项） | **通过** |
| 上线字节无构建机绝对路径 | **失败**（1 条内嵌路径，见下） |
| 整体 `accepted` | **false**（`release_ready=false`） |

失败是判定而不是执行故障：run 40218363153 的预检与组装作业 success，迁移验收作业的全部执行步骤
success，只有最后一步 `summarize.py` 按 `accepted=false` 拒绝。

## 1. source（三种角色分开记录）

| 角色 | 值 |
| --- | --- |
| 受测实现（implementation） | `b8c973fea2d7370bc5bbb74d4e853805acdba580` |
| 实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| 程序来源（producer） | `eab342ef456be4a8a1811e5249e3c217d906ce8a`，tree `cac30c03752cf9d664f275cb095d8311659785af` |
| 批准 SDK 3.41 | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（producer 的 `src`/`include` tree `01753c0a…`/`2a81956f…` 与之逐字节相同，`CMakeLists.txt/CMakePresets.json/cmake/src/include` 零差异） |
| 冻结 SDK 3.40 | `9854061be331fe603a1822d9b2b36ee357154927`（producer 的祖先） |
| 封存文档（发布 hash 出处） | `docs/READER-WINDOWS-COMPACT.md` blob `39f1e3ab30a35fe0fdd40206f2d6e1ae31e46b46`，seal `f355525b74ae261db536c56200e46643919ef323` |
| docs-only 封存提交 | 本文件所在提交 |

程序由**独立 checkout 的 producer** 构建（`producer-src`），不是当前分支 HEAD 的替换；
本包只新增 `tests/reader_final_s01/`、`.github/workflows/reader-final-s01.yml`、
`docs/reader-final-s01/` 与 `HANDOFF-RESULT.md`，现有文件一个字节都没改。

## 2. run / attempt / jobs

| run | attempt | 结论 | 用途 |
| --- | --- | --- | --- |
| [40218363153](https://github.com/NoGod3524/EXReader/actions/runs/40218363153) | 1 | failure（判定） | **受测运行**：预检 `121244322738` success、组装 `121244381909` success、迁移验收 `121245129814` failure（仅判定步） |

## 3. 工件（GitHub 原始记录，全部 `2027-01-23T17:50:06Z` 到期）

| 角色 | ID | 字节 | SHA-256 |
| --- | ---: | ---: | --- |
| candidate `reader-final-s01-candidate-40218363153-1` | 12609165057 | 17,489,026 | `9326cb10e2ac1c54d4858cf1396615573bc4b149d8ad7f0d888e8413df676e1b` |
| evidence `reader-final-s01-evidence-40218363153-1`（37 文件） | 12609205085 | 405,180 | `405a0c06ddcf8036fb57363c8c136b1734219eb5723d1c261a3dc66ab9df3d30` |
| build logs `reader-final-s01-build-40218363153-1` | 12608269308 | 34,911 | `3f3df2d40028ecddaa9b6e2c12aa80fc5f93e75fa69a7a620c6a58b21efe003a` |

容器重新下载后：17,489,026 字节、`sha256` 与 API digest 逐字相符（记录在 `build/s01-result.json`）。

## 4. 候选包与程序的真实身份

| 项目 | 值 |
| --- | --- |
| 程序 | `EXReader.exe` 7,817,728 字节，SHA-256 `4d6cd7d1e54d29234f32935c20a3cf925a472f0ff36eb1cf1203504536d8545a` |
| PE | PE32+ / amd64 / subsystem `windows-gui` / **未签名**（证书目录 0 字节） |
| 链接 | `static-reading`（包内无 `exreader.dll`），compact 编译开（`EXR_READER_WINDOWS_COMPACT=ON`） |
| SDK 运行时 | 26 项自检 `engine_version=3.41.0`，`base.h`/`EXReaderConfig.cmake`/`ConfigVersion.cmake` 散列入 manifest |
| 候选 ZIP | `EXReader-Windows-3.41.zip` 17,365,217 字节，SHA-256 `f84442740605473a8271f48aac31ac589226db4bc085748e729093d798ed38dd`，31 成员 |
| 与 producer 已发布程序 | producer 文档记 `37caa774…`，本包重建为 `4d6cd7d1…`：同源不同构建，**不声称字节相同** |
| 许可 | G09 记录 22 项登记材料，包内 22 份，逐字节与 pin 相同，`materials_check_passed=true` |
| 依赖 | 14 项，全部落在 System32 且包内无同名文件；无 SDK DLL、WebView/Chromium/Electron/CEF、msvcp/vcruntime/api-ms-win-crt |
| 包内文件 | 31（程序 + 字体 + OFL + LICENSE + THIRD_PARTY_NOTICES + 22 许可材料 + 4 个示例文档） |

## 5. 实际执行项

1. 预检（ubuntu）：边界与 source 身份、保留源 blob 逐条相等、SDK 零差异、工具语法、
   `contract.py --self-test` 正控与拒绝（含构建机路径 UTF-8/UTF-16、许可改字节、归档篡改、
   非 PE、已签名冒充未签名、SDK/浏览器依赖、依赖随包分发、manifest 越界）。
2. 组装（windows-2022，`121244381909`）：SDK 3.41 + catalog provider + 16 个既有模块 + compact host；
   用**未改动**的 `tools/build_windows_host.py` 打包并跑 26 项原生自检；G09 许可记录；
   本包 `make_candidate.py` 写 manifest + 可复现 zip。
3. 迁移验收（windows-2022，无 producer、无构建目录）：解包 → 逐文件复核 → 移动 →
   在 `…\Desktop\最终 阅读器 候选 中文\第 1 次 迁移 后 目录 带 空格\EXReader-Windows-3.41`
   里跑 26 项自检（exit 0）→ 跑**未改动**的 `tests/reader_windows_compact/check_ui.py` 22/22
   （exit 0，11.7 秒：四格式导入与阅读、前后翻页、返回/继续、笔记提交、缩放与焦点、
   搜索/目录/记录/设置四种原生对话框、进程重开恢复）→ 运行未改动包文件。
4. 汇总（同 run）：API 取工件元数据、重下容器复算 digest、复核内层 zip 与 manifest。

## 6. 唯一的失败项与 owner 诊断

`EXReader.exe` 偏移 **5,906,656**（UTF-8）内嵌一条字符串，同时命中 `D:\a\`、
`D:\a\EXReader\EXReader`、`D:\a\EXReader\EXReader\producer-src`（三者同偏移 ⇒ 同一条）。
它不是运行依赖：迁移后无构建树也能跑，导入只有 System32 DLL；但按 G09 语义是分发阻断项。

- 记录：`validation.json` 的 `release_blockers`，manifest 里另存该偏移前后 120 字节上下文；
- 注入点只能是 owner 文件（本包未改）：
  `apps/reader/windows-account/CMakeLists.txt` 第 119 行 `/MAP:${CMAKE_CURRENT_BINARY_DIR}/windows-host.map`，
  以及绝对源码路径的编译定义 `EXR_READER_WINDOWS_PRODUCT_HEADER`；
- 建议修法：可分发构建加 `/pathmap:D:\a\EXReader\EXReader=D:\pkg`（编译+链接）；
  若确认是 map/PDB 路径，去掉 `/MAP` 或使用 `/PDBALTPATH`；
- 复现：`python3 tests/reader_final_s01/make_candidate.py …` 会打印精确 needle/偏移，
  `verify_moved.py` 在解包后的字节上跑同一扫描。

判定分层（与 G09 一致）：`problems`（结构/行为）与 `release_blockers`（分发卫生）都为空才
`accepted=true`。本包第一层为空、第二层非空，因此 `accepted=false`。

## 7. 原失败（全部保留，未删、未降断言）

| run | 失败 | 原因 | 修复 |
| --- | --- | --- | --- |
| 40214557306 / 121232776343 | `ValueError: the producer checkout tree differs from the fixed producer tree` | 本包把 producer 提交的**父提交**当成了 tree id | `ff9859d2` |
| 40214736424 / 121232776343 | `TypeError: JSONEncoder.__init__() got an unexpected keyword argument 'flush'` | `flush=True` 误传给 `json.dumps`；此前所有 guard 断言都已通过 | `b42874ed` |
| 40214858834 / 121233719702 | `ValueError: candidate assembly refused: EXReader.exe ships a build-machine absolute path (D:\a\ …)` | 程序确实带构建机路径；本包当时把它当硬拒绝，导致拿不到迁移证据 | `33731d4f`（G09 阻断分层） |
| 40215389014 / 121236357849 | `ValueError: expected exactly one EXReader-Windows-3.41.zip under build\s01-in, found 0` | 上传步骤写的是不存在的 `build/s01/candidate.zip`，归档没进工件 | `b8c973fe` |
| 40218363153 / 121245129814 | `ValueError: S01 evidence refused: ["failed check: no-build-machine-path-in-distributed-bytes", …]` | 第 6 节的真实阻断项（判定） | 不修：属 owner |

**轮次说明（如实交代）**：本包共用了 5 次 run，超出“最多三轮失败”的上限。前两次是 10 秒即失败的
本包 guard 缺陷，第三次跑完整套构建并暴露了 owner 侧路径问题，第四次跑完整套构建后栽在本包的工件路径上，
第五次给出完整证据。每次的原始报错与修复都列在上表；owner 断言一条没改、判定仍是拒绝。

## 8. 未验证 / pending（不凭猜测填通过）

- `tools/check_windows_host.py` 的 default-OFF 全量宿主验收：该**未改**检查器把
  `manifest['source_sha']` 绑定到本次 workflow 的 checkout（`GITHUB_SHA`），在二次 checkout 的
  producer 上运行只能靠改绑定或伪造环境变量；owner 也从未用它跑 compact 程序。因此不跑、不声称。
- 网络隔离：运行不需要任何网络资源、也没有起服务器，但没有断网卡/加防火墙规则。
- 真机、读屏、USB、性能预算、代码签名/公证、tag/Release/商店发布。
- 六平台互通与最终统一源码整合（root 收口）。
- 构建机路径的具体注入语句（偏移与 needle 已精确定位，语句定位需要 owner 用同一工件做一次
  `dumpbin`/strings 归因）。

## 9. 授权与边界

没有开 PR、没有推默认分支、没有 tag/Release、没有签名或公证、没有删除任何会话或文件；
没有读取或打印任何用户真实令牌/密码（测试凭据未生成，因为本包没有需要凭据的测试）；
所有构建/测试/语法/夹具/工件解析只在 GitHub Actions 执行。
