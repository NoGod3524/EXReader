# S01：Windows 最终可迁移包核验

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，独立分支 `codex/reader-fw-s01`。
本包只做一件事：把**固定实际 Windows 简洁版 producer** 已经交付的程序做成可迁移候选包，
逐文件记账，然后把它搬到 Unicode + 带空格、且从未存在构建目录的路径下真实运行。

## 1. 三个 source 分开记录，绝不合并

| 角色 | 值 | 说明 |
| --- | --- | --- |
| producer source（程序来源） | `eab342ef456be4a8a1811e5249e3c217d906ce8a`，tree `cac30c03752cf9d664f275cb095d8311659785af` | 最终 wave 共同约束里受测的 Windows 简洁 UI；本包用**独立 checkout**（`producer-src`）构建，不把当前分支 HEAD 换成它 |
| 批准 SDK source | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41） | producer checkout 的 `src` tree `01753c0a…`、`include` tree `2a81956f…` 与该提交逐字节相同；`CMakeLists.txt/CMakePresets.json/cmake/src/include` 零差异；冻结 3.40 SDK `9854061b…` 是其祖先 |
| implementation source（本包代码来源） | 本分支 head | 只新增 `tests/reader_final_s01/`、`.github/workflows/reader-final-s01.yml`、`docs/reader-final-s01/`、`HANDOFF-RESULT.md` |

生产机路径、producer 路径与 SDK stage 路径都**不进入**任何上线字节：打包后对全部文件做
UTF-8/UTF-16 双编码扫描（前缀集与 G09 同一份），命中即拒。

## 2. 复用而不是重写（J25 + G09）

| 复用项 | 来源 | 用法 |
| --- | --- | --- |
| J25 打包器 | producer 自己的 `tools/build_windows_host.py`（未改一字） | 直接调用它把 compact 程序打成 payload，并运行它内置的原生 26 项自检；产物 `build.json` 就是本包的注册来源 |
| 宿主字体 | `tools/host_font.py` 的 `ASSETS` 固定表 | 包内 `Reader.otf`/`OFL.txt` 必须等于该表的散列 |
| G09 许可/私有路径 | `tests/reader_distribution_inventory/contract.py`（`scan_private_paths`/`scan_test_secrets`/许可记录语义） | 本包不另写一套扫描；许可记录由既有 `tools/check_reading_licenses.py` 生成后逐文件比对 |
| G09 许可记录生成器 | `tools/check_reading_licenses.py` | `reading-library` 安装 stage 的登记材料（组件、安装路径、pin）是本包 `licenses/**` 的唯一事实源 |
| 原有可用烟测 | producer 的 `tests/reader_windows_compact/check_ui.py` + `contract.py`（未改） | 在**迁移后**的程序上执行：四格式导入、阅读、前后翻页、键盘返回/继续、四种原生对话框（含设置）、窗口缩放与重开恢复 |
| 现有守卫机制 | `tests/reader_windows_compact/guard.py` 的写法 | 新增 `tests/reader_final_s01/guard.py` 只守护本包，不改旧守卫 |

`tests/reader_final_s01/guard.py` 断言上面这些被复用文件的 blob 在 producer 与实现分支
**完全相同**，并且在 verify 作业里再按 SHA-256 复核一次：实际执行的检查代码就是 owner 交付的那份。

## 3. 实际验收（全部只在 GitHub Actions 执行）

1. 从 producer checkout 重建 SDK 3.41、产品 catalog provider、16 个既有公开模块，并以
   `EXR_READER_WINDOWS_COMPACT=ON` 单独构建 `EXReaderProduct`（与 producer 自己 workflow 的构建行同源）。
2. 用未改动的打包器生成 payload，跑内置 26 项原生自检；`build.json` 记录 source/sdk/文件散列。
3. `make_candidate.py`：记录 SDK 身份（`base.h`/`ConfigVersion.cmake`/`Config.cmake` SHA-256）、
   程序 PE 头（machine/subsystem/Authenticode 证书目录=0），`dumpbin /DEPENDENTS` 逐项落到
   System32 且不在包内，逐文件 license 归属与来源，最后写**可复现 zip**（排序、固定时间戳、固定权限）。
4. `verify_moved.py`：用另一台 runner、**没有 producer checkout、没有构建目录**，把 zip 解到
   `…\Desktop\s01 原始 位置\EXReader-Windows-3.41`，逐文件复算散列，再 `shutil.move` 到
   `…\Desktop\最终 阅读器 候选 中文\第 1 次 迁移 后 目录 带 空格\EXReader-Windows-3.41`，
   在迁移后的目录里运行自检，再运行上面那份未改动的简洁版验收（22 项）。
5. `summarize.py`：用 GitHub API 取本次上传工件（id/字节/digest/有效期/run/head_sha），
   重新下载容器并复算 `sha256` 与内层 `EXReader-Windows-3.41.zip`，把 manifest、归档、程序绑到同一 run。

## 4. 结果与边界

真实结果（source/run/attempt/job/工件/字节/SHA-256/有效期、实际检查项、原失败与 pending）
写在 `docs/reader-final-s01/validation.json` 与 worktree 根 `HANDOFF-RESULT.md`，
本节第 4.1 小节是关键数字的摘要。

判定分两层，按 G09 的既有语义：

- **结构/行为**（`problems`）：缺文件、字节或散列不符、归档被改、许可未登记或改字节、
  依赖不是系统 DLL、测试密钥、迁移失败、运行失败 —— 任一项即拒；
- **分发卫生**（`release_blockers`）：上线字节里出现构建机绝对路径。它照 G09 的做法
  逐文件记录并置 `release_ready=false`，不冒充“运行依赖”，也不因此跳过迁移后的实际运行。

两层都干净才算 `accepted=true`。本包的最终 `accepted=false` 来自第二层（详见 4.1）。

本包**不**授予：完整产品通过、真机/读屏、性能预算、签名或公证、tag/Release/商店发布，
也不授予六平台互通结论。程序当前**未签名**（Authenticode 证书目录为空），这一点在 manifest 与
验证 JSON 中明示。

明确未做（见 `not_verified`）：

- `tools/check_windows_host.py` 的 default-OFF 全量宿主验收：该未改检查器把
  `manifest['source_sha']` 绑定到**本次 workflow 的 checkout**（`GITHUB_SHA`），
  在“二次 checkout 的 producer”上运行只能靠修改绑定或伪造环境变量，因此本包不改它、也不假装跑过；
  简洁版自己的那份未改动验收（22 项）才是本程序的原测试。
- 网络隔离（运行不需要任何网络资源，但没有断开网卡/加防火墙规则）；
- 真机、读屏、USB、性能预算；
- 多平台互通与最终统一源码整合（root 收口）。


## 4.1 实际结果（run 40218363153，attempt 1，受测源码 `b8c973fe`）

三个作业：预检 `121244322738` success、组装 `121244381909` success、迁移验收 `121245129814` failure。
**这里的 failure 是判定，不是执行故障**：迁移验收的每一步（解包、逐文件复核、移动、自检、原验收）都成功，
只有最后一步 `summarize.py` 按 `accepted=false` 拒绝。

| 事实 | 值 |
| --- | --- |
| 程序 | `EXReader.exe` 7,817,728 字节，SHA-256 `4d6cd7d1e54d29234f32935c20a3cf925a472f0ff36eb1cf1203504536d8545a`，PE32+ amd64，`windows-gui`，**未签名**（证书目录 0 字节），静态阅读链接 |
| 候选 ZIP | `EXReader-Windows-3.41.zip` 17,365,217 字节，SHA-256 `f84442740605473a8271f48aac31ac589226db4bc085748e729093d798ed38dd`，31 个成员 |
| 工件 | candidate `12609165057`（17,489,026 字节，`sha256:9326cb10…`）、evidence `12609205085`（405,180 字节，`sha256:405a0c06…`）、build logs `12608269308`（34,911 字节，`sha256:3f3df2d4…`），均 `2027-01-23T17:50:06Z` 到期；容器重新下载后字节数与 digest 与 API 记录逐字相符 |
| SDK | 3.41.0（ABI 1、core 3.40.0），`src`/`include` tree 与批准 SDK `edddc463` 相同；构建缓存 `EXR_SDK_VERSION=3.41.0`、`EXR_READER_WINDOWS_COMPACT=ON`、`CMAKE_BUILD_TYPE=Release` |
| 许可 | G09 记录 22 项登记材料，包内 22 份，逐字节与 pin 相同，`materials_check_passed=true` |
| 依赖 | 14 项，全部是 System32 里实际存在的系统 DLL，包内没有同名文件；无 SDK/浏览器/动态 CRT |
| 迁移 | 解到 `…\Desktop\s01 原始 位置\EXReader-Windows-3.41`，`shutil.move` 到 `…\Desktop\最终 阅读器 候选 中文\第 1 次 迁移 后 目录 带 空格\EXReader-Windows-3.41`；31 个文件散列不变，旧路径消失 |
| 迁移后自检 | 26 项通过，engine 3.41.0，退出码 0（程序与字体都在迁移后的目录里） |
| 原验收（未改） | `tests/reader_windows_compact/check_ui.py` 22/22、退出码 0、11.7 秒；四格式导入与阅读、前后翻页、返回/继续、笔记提交、缩放与焦点、搜索/目录/记录/设置四种原生对话框、进程重开恢复 |
| 程序未签名 | 是（manifest 与结果 JSON 均明示） |

### 唯一的拒绝项：程序字节内嵌构建机路径

`EXReader.exe` 在偏移 **5,906,656**（UTF-8）含一个字符串，同时命中 `D:\a\`、
`D:\a\EXReader\EXReader`、`D:\a\EXReader\EXReader\producer-src` —— 三者在同一偏移，
说明是**一条**内嵌路径。这不是运行依赖（迁移后无构建树也能跑、导入只有 System32 DLL），
而是 G09 意义上的分发阻断项，因此 `accepted=false` / `release_ready=false`，逐条记录在
`validation.json` 的 `release_blockers`，manifest 里还存了该偏移前后 120 字节的上下文。

注入点只能在 owner 文件里（本包不改）：`apps/reader/windows-account/CMakeLists.txt` 的
`target_link_options(... /MAP:${CMAKE_CURRENT_BINARY_DIR}/windows-host.map)`（第 119 行）
与绝对源码路径的编译定义 `EXR_READER_WINDOWS_PRODUCT_HEADER`。建议 owner 在可分发构建里加
`/pathmap:D:\a\EXReader\EXReader=D:\pkg`（编译与链接都加），若确认是 map/PDB 路径则去掉 `/MAP`
或改用 `/PDBALTPATH`。

### 与发布就绪的关系

- 结构、许可、依赖、迁移后可运行：**已证明**；
- 发布就绪：**拒绝**（构建机路径残留）；
- 完整产品、真机/读屏、性能、签名/公证、tag/Release：**不授予**。

## 5. 复现

```bash
# 边界与 source 身份（Actions，ubuntu）
python3 tests/reader_final_s01/guard.py --producer producer-src
python3 tests/reader_final_s01/contract.py --self-test     # 正控 + 拒绝
# Windows 组装（producer checkout 在 producer-src）
python3 tests/reader_final_s01/make_candidate.py --payload <stage>/EXReader --stage <sdk-stage> \
  --licenses build/s01-input/licenses.json --producer-src <producer> --build <compact-build> \
  --program <compact-build>/EXReaderProduct.exe --selftest <package>/report.json \
  --build-root <producer> --output build/s01
# 迁移后验收（另一台 runner，无 producer/无构建目录）
python3 tests/reader_final_s01/verify_moved.py --artifacts build/s01-in --fixtures build/s01-fixtures \
  --output build/s01-moved
python3 tests/reader_final_s01/summarize.py --manifest build/s01-in/manifest.json \
  --moved build/s01-moved/moved.json --artifact-id <id> --output build/s01-result.json
```

`contract.py --self-test` 的每一条拒绝都是可执行的负控：缺文件、改字节、多出成员、重复成员、
未固定时间戳、非 PE、已签名却报未签名、把 SDK/浏览器运行时列为依赖、依赖随包分发、
未知系统 DLL、构建机路径（UTF-8 与 UTF-16）、测试密钥、未登记许可、许可改字节、
manifest 越界路径与外部 producer。
