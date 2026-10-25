# S01：Windows 最终可迁移包核验

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，独立分支 `codex/reader-fw-s01`。
本包只做一件事：把**固定实际 Windows 简洁版 producer** 已经交付的程序做成可迁移候选包，
逐文件记账，然后把它搬到 Unicode + 带空格、且从未存在构建目录的路径下真实运行。

## 1. 三个 source 分开记录，绝不合并

| 角色 | 值 | 说明 |
| --- | --- | --- |
| producer source（程序来源） | `eab342ef456be4a8a1811e5249e3c217d906ce8a`，tree `6c4fad985bf46603f0afc5baaa4e2b2b9e82c870` | 最终 wave 共同约束里受测的 Windows 简洁 UI；本包用**独立 checkout**（`producer-src`）构建，不把当前分支 HEAD 换成它 |
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
   重新下载容器并复算 `sha256` 与内层 `candidate.zip`，把 manifest、归档、程序绑到同一 run。

## 4. 结果与边界

真实结果（source/run/attempt/job/工件/字节/SHA-256/有效期、实际检查项、原失败与 pending）
写在 `docs/reader-final-s01/validation.json` 与 worktree 根 `HANDOFF-RESULT.md`。

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
