# S03 macOS应用包搬移核验 — 交回

**状态：accepted=false（两个候选各自的 .app 清单与移位离线烟测均通过；同轮总闸被我自己的证据字段接线卡住，修正已提交但按三轮 CI 上限未再运行）。** 不授产品通过，不授签名/公证/Gatekeeper/真机，最终整合仍由 root 控制。

## 1. source 表（四种身份分开，未互相替代）

| 角色 | 身份 |
| --- | --- |
| 实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| 本包受测源码（verifier） | `93427741a4f2c4fce803a00d3ff84c8654c7b388` |
| docs 封存提交 | 见远端 `codex/reader-fw-s03` 顶端提交（只改 `docs/reader-final-s03/` 与本文件，`[skip ci]`，不含断言或实现改动） |
| 实际 macOS producer | `codex/reader-apple-raw3` @ `15dab6b2270dc296ed6239db67ced2e22d255e65`（封存 `44eabdc86b3b84d986f81dbaf8cee92b1829cea8`）；CI 内**二次 checkout** 到 `$RUNNER_TEMP/s03/producer`，HEAD 断言等于该提交 |
| 批准 SDK 源码 | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41.0 / ABI 1u）；CI 内 `git archive` 解出后逐 blob 与 `git ls-tree -r` 比对 |
| 复用分发契约 | `tests/reader_distribution_inventory/contract.py`（摘要、私有路径与测试凭据扫描） |
| 远端分支 | `origin/codex/reader-fw-s03`（未推默认分支，未开 PR/tag/Release） |

producer 的 SDK 承载路径（`include` `src` `cmake` `CMakeLists.txt` `bindings` `licenses`）与批准 SDK 提交逐对象相同：`guard.py`（静态）`git diff --name-only edddc463 15dab6b -- …` 为空，`identity.py`（构建树）逐 blob 相等。

## 2. run / attempt / job / 工件

| 项 | 值 |
| --- | --- |
| 受测 run | **40215433040** attempt **1**，source `93427741a4f2c4fce803a00d3ff84c8654c7b388`，conclusion **failure** |
| job guard | `121235435182` success（17:13:40→17:13:52Z） |
| job native | `121235486548` failure（17:15:20→17:21:48Z） |
| 证据工件 | `12607287249` `reader-final-s03-evidence-40215433040-1`，80,970,449 B，`sha256:dbc66b40649032d4497512745d02e90bd9acdba478b79bd7033521be130a82d2`，有效至 **2027-01-23T17:13:38Z** |
| guard 工件 | `12606649775` `reader-final-s03-guard-40215433040-1`，747 B，`sha256:d36233222b9886c647bd2c01d7a03cea4c97e79e3978f3a9cdb4752b5128b2c0`，有效至 2027-01-23T17:13:38Z |

**同轮实际通过（两个候选各自 `accepted: true`、`problems: []`）**

| 检查 | default | raw |
| --- | --- | --- |
| .app 文件数 / 字节 | 36 / 45,068,685 | 36 / 45,092,492 |
| 可执行文件 `lipo` 架构 | arm64 | arm64 |
| LC_BUILD_VERSION platform / 可执行 minos | 1（macOS） / 12.0 | 同左 |
| `otool -L` 依赖记录（闭包内或系统库） | 38 | 38 |
| 动态 SDK 身份 | 一个身份、三个版本别名（1.dylib / 3.41.0.dylib / dylib），无 Frameworks 之外副本、无静态 `.a` | 同左 |
| 产品库唯一来源 | 复用 producer 的 `check_apple_product.py`（含 7 个反例）通过；7 个 raw 实现符号按 `nm` 与链接映射独立计数=1（raw 候选） | 同左 |
| Info.plist | 3.41.0 / minos 12.0 / `EXRSourceSHA`=producer / `EXRRawSelectorEnabled`=false | 同左（=true） |
| 资源与许可证 | 必需资源齐备、字体 pin 命中、许可证原件与安装树逐文件一致 | 同左 |
| producer `build.json` | 与重算散列逐文件相等（多/少/改一个都拒绝） | 同左 |
| 移位 | `ditto` → `…/relocated/最终 阅读器 候选 ünïcode 空格/EXReader.app`，逐文件散列不变 | 同左 |
| 离线包络 | `sandbox-exec`：控制探针可达、同参数探针被拒（`denied=true`） | 同左 |
| 原 native 烟测（producer 未改的 `check_apple_host.py --device macos`） | 基线 + 离线打开 + 离线重开三阶段，每阶段 21 项 `passed=true`，三次检查清单一致，重开前状态文件存在 | 同左 |
| 签名事实 | `codesign --verify --deep --strict` 通过、`Signature=adhoc`、无 `Authority=`；`spctl` exit 3（拒绝，符合未公证预期）；无 quarantine | 同左 |
| 构建机绝对路径 | 3 个分发文件命中 `/Users/runner/`（记录、不修，按 G09 口径转文件 owner） | 3 个 |
| identity 步骤 | `accepted: true, problems: []`（SDK 源码树逐 blob 等于 `edddc463`、stage 3.41.0/ABI 1u、唯一 `libexreader*.dylib`、runner arm64） | — |

**同轮未通过（总闸）**：`aggregate.py` 的 `problems: ["sdk_version:None","sdk_abi:None"]` —— `identity.py` 把安装版本/ABI 只写进 `stage` 块，而判定读 `sdk` 块。两个候选的清单与烟测本身全是 `accepted: true`。

## 3. 失败轮次（保留原状，未覆盖、未删）

| run | source | 结论 | 精确原因 | 修复 |
| --- | --- | --- | --- | --- |
| 40214519357 | `5fbd58e7` | failure（0 job，启动失败） | 我在 job 级 `env` 用了 `runner.temp`，该上下文在 job env 不可用 → workflow 无法启动 | 第一步内写 `GITHUB_ENV` |
| 40214601048 | `bff5eaaf` | **cancelled**（我在 SDK 构建中主动取消） | 自查出自己两处过窄断言，避免白白烧掉构建：Frameworks 动态库 minos 被我固定 12.0；用 producer 签名前记录的摘要去比签名后字节 | minos 改为记录（只对可执行固定 12.0）；签名前摘要改为记录 |
| 40214808236 | `a3a20cf8` | failure | `sdk_library_count:3` + `framework_not_referenced`×2：producer 按链接器需要把同一个动态库以三个版本名各放一份，我的规则却要求"恰好一个文件" | 改为身份规则：同一 `LC_ID_DYLIB` + 同一导出符号摘要，别名只允许在 `Contents/Frameworks`，外部副本仍拒绝 |

三轮 CI 预算已用完（一次启动失败、一次取消、两次实质失败中的最后一轮已把除总闸外的全部断言跑绿），故**不再刷第 4 轮**。

## 4. 未验证 / 修复后需要的一次运行

修复已提交到 `tests/reader_final_s03/identity.py`（**未由 Actions 验证**）：

```diff
-    sdk = {'source_sha': …, 'extracted_tree_problems': tree_findings}
-    stage = stage_identity(args.stage.absolute())
-    problems.extend(stage['problems'])
+    stage = stage_identity(args.stage.absolute())
+    problems.extend(stage['problems'])
+    sdk = {'source_sha': …, 'extracted_tree_problems': tree_findings,
+           'version': stage['version'], 'abi': stage['abi'],
+           'package_version': stage['package_version'],
+           'installed_libraries': [entry['name'] for entry in stage['libraries']]}
```

重跑一次（`workflow_dispatch` 或推 `tests/reader_final_s03/**`）即应把 `accepted` 翻为 true；其余断言、阈值（21 项自检、闭包、位移散列、离线包络）与上述通过事实都不需要改动。

**明确未验证范围**：签名身份、公证、Gatekeeper 通过、商店/发布、真机（Mac/iPhone/iPad）与 USB/读屏、长时阅读与性能预算、raw3 运行时请求路径（属 producer run 40196978163 证据，本包自检不触达）、最终统一源码整合、`release_ready`（3 个分发文件仍带构建机绝对路径，按 G09 归文件 owner）。producer 的原始 ZIP `12600789926` **未**在本包下载或复核，本包只用了它的源码提交。

## 5. 复现

```bash
# 本轮同一路径（macos-15 / ARM64，只在 Actions）
git archive edddc463… | tar -x -C "$S03_WORK/sdk-source"
cmake -S "$S03_WORK/sdk-source" -B "$S03_WORK/sdk-build" -DCMAKE_BUILD_TYPE=Release \
  -DEXR_BUILD_TESTS=OFF -DEXR_BUILD_TOOLS=OFF -DEXR_ENABLE_AAC=OFF
cmake --build "$S03_WORK/sdk-build" --parallel 4 && cmake --install "$S03_WORK/sdk-build" --prefix "$S03_WORK/stage"
git clone --shared --no-checkout "$GITHUB_WORKSPACE" "$S03_WORK/producer"
git -C "$S03_WORK/producer" checkout --detach 15dab6b2270dc296ed6239db67ced2e22d255e65
python3 tools/build_apple_product.py --sdk "$S03_WORK/stage" --sdk-version 3.41.0 --target macos --build "$S03_WORK/products-default"
python3 tools/build_apple_product.py --sdk "$S03_WORK/stage" --sdk-version 3.41.0 --target macos \
  --product-prefix "$S03_WORK/products-raw" --selector-bytes-candidate --build "$S03_WORK/raw-build"
python3 tools/build_apple_host.py --sdk "$S03_WORK/stage" --platform macos --sdk-version 3.41.0 --output "$S03_WORK/app-default"
python3 tools/build_apple_host.py --sdk "$S03_WORK/stage" --platform macos --sdk-version 3.41.0 \
  --product-prefix "$S03_WORK/products-raw" --selector-bytes-candidate --output "$S03_WORK/app-raw"
# 然后 bundle.py / identity.py / smoke.py / aggregate.py，见 .github/workflows/reader-final-s03.yml
```

只重算已上传证据（不重建）：

```bash
python3 tests/reader_final_s03/aggregate.py --evidence <证据目录> --output <输出目录> \
  --verifier-sha 93427741a4f2c4fce803a00d3ff84c8654c7b388 \
  --producer-sha 15dab6b2270dc296ed6239db67ced2e22d255e65 --sdk-sha edddc463c06ed5731195cdb8f06b2df6dff7699e
```

## 6. 本包改动清单（未触碰任何 owner/保护树）

`tests/reader_final_s03/`（`spec.py` `bundle.py` `identity.py` `smoke.py` `aggregate.py` `guard.py` `check_spec.py` `README.md`）、`.github/workflows/reader-final-s03.yml`（只触发 `codex/reader-fw-s03` 与本包路径，`concurrency` 单 live run）、`docs/reader-final-s03/`（契约 + 证据 + `validation.json`）、本文件。fixture 全部由 CI 从 producer 源生成，无本地构建/下载。
