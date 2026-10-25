# S03 macOS 应用包搬移核验

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，独立分支 `codex/reader-fw-s03`。
本包只新增 `tests/reader_final_s03/`、`.github/workflows/reader-final-s03.yml`、`docs/reader-final-s03/` 与根 `HANDOFF-RESULT.md`；
现有 `apps/`、`examples/`、SDK 保护树、原 `tests/`、原 workflow、预算与系统账号配置一律只读。

## 目标与边界

为**实际 macOS 原生 producer** 补上 `.app` 候选的组装、依赖闭包与资源清单，移位后运行**原有** native 烟测，并核对 Info.plist、CPU 架构、SDK 与产品库唯一来源；分发清单工具复用既有 `tests/reader_distribution_inventory/contract.py`（摘要、私有机路径与测试凭据扫描），不重复实现 G09 已交付内容。

本包**不**签名（除 producer 工具原有的 ad-hoc）、不公证、不发布、不打 tag、不开 PR，不使用任何签名秘密。

## 四种 source 分开记录（不得互相替代）

| 角色 | 不可变身份 |
| --- | --- |
| 本包受测源码（verifier） | 分支 `codex/reader-fw-s03` 上本次受测提交 |
| 实际 macOS producer（实现） | `codex/reader-apple-raw3` @ `15dab6b2270dc296ed6239db67ced2e22d255e65`（封存 `44eabdc86b3b84d986f81dbaf8cee92b1829cea8`），run 40196978163 attempt1，job native `121179826434` / strict `121186031984`，工件 `12600789926`（`apple-raw3-native-40196978163-1`，77,056,135 B，`sha256:92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5`，有效至 2027-01-23T13:18:06Z） |
| 批准 SDK 源码 | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41.0，ABI 1）；3.40 冻结 `9854061be331fe603a1822d9b2b36ee357154927` 仅作对照，未在本包构建 |
| 分发清单契约（复用） | `tests/reader_distribution_inventory/contract.py`（G09） |

producer 的 SDK 承载路径（`include`、`src`、`cmake`、`CMakeLists.txt`、`bindings`、`licenses`）与批准 SDK 提交逐对象相同，由 `guard.py`（静态）与 `identity.py`（构建树逐 blob）分别证明；`15dab6b` 不是本分支 HEAD，任何一步都不允许用分支 HEAD 顶替 producer。

## 一次运行的步骤

1. `guard`（ubuntu-22.04）：本包范围（改动路径只允许在包内）、固定提交存在性、SDK 保护树相同、producer 工具具备 `.app` 候选组装所需 `--product-prefix` / `--selector-bytes-candidate`、original 烟测 `checks.count >= 20`、workflow 只触发本分支与本包路径；`check_spec.py` 对 spec 的每条判定喂单个变异并要求按名拒绝。
2. `native`（macos-15，ARM64，矩阵并行上限 2，本包同时最多一个 live run）：
   - 由 `git archive edddc463` 解出 SDK 源码，`cmake` 构建并以 `-DEXR_BUILD_TESTS=OFF -DEXR_BUILD_TOOLS=OFF -DEXR_ENABLE_AAC=OFF` 安装到 stage；归档自身 SHA-256 入证据。
   - 二次 checkout producer（本地 `git clone --shared` + 分离 HEAD 到 `15dab6b`），用 producer 自己的 `tools/build_apple_product.py` 安装默认产品族与显式 raw3 候选族（独立前缀），再用 producer 自己的 `tools/build_apple_host.py` 组装两个 `.app` 候选（ad-hoc 签名，来自 producer 工具）。
   - `bundle.py`：Info.plist 键值、`lipo` 架构、LC_BUILD_VERSION（platform=1/macos、minos=12.0）、`otool -L` 依赖闭包（只允许 bundle 内文件或 `/usr/lib`、`/System/Library`）、唯一动态 SDK、无静态归档、资源清单、字体 pin、许可证原件与安装树一致、资源来源（producer 源文件/字体 pin）、producer `build.json` 与重算散列逐文件相等、产品库唯一来源（重跑 producer 的 `check_apple_product.py` 并独立用 `nm`/链接映射复核 7 个 raw 实现符号），以及私有机路径/测试凭据扫描（复用 G09）。
   - `identity.py`：producer HEAD/tree、SDK 路径对象相同、解出树与 `git ls-tree -r edddc463` 逐 blob 相同、stage 的 `EXR_VERSION`/`EXR_ABI_VERSION`、安装包版本、唯一 `libexreader*.dylib` 散列与 install name、默认产品族 `product.json`、runner 必须是 ARM64。
   - `smoke.py`：用 producer **原有** `tools/check_apple_host.py --device macos`（未改一字）先跑基线；用 `ditto` 把 `.app` 移入含空格与非 ASCII 的路径 `最终 阅读器 候选 ünïcode 空格/EXReader.app` 并逐文件散列比对；在 `sandbox-exec` 拒绝网络的包络内先证控制探针可达、再证同参数探针被拒；随后离线**打开**与离线**重开**（同一 HOME，重开时上一次运行的状态仍在）；记录 codesign/spctl/stapler/quarantine 事实与位置存档。
   - `aggregate.py`：按候选独立判定，写 `result.json`、`validation.json`、`artifact-index.json`；只有两个候选全部通过且 source 身份一致才 `accepted=true`。
3. 证据目录 `build/s03/evidence/` 作为工件上传；`validation.json` 与 `artifact-index.json` 均在证据内。

## 每个候选的接受条件

- 依赖闭包：所有 `otool -L` 条目要么在 bundle 内按 LC_RPATH 解析到真实文件，要么是系统库；无外部绝对依赖。
- 唯一来源：`Contents/Frameworks` 恰好一个 `libexreader*.dylib`，bundle 内无第二份副本、无静态 `.a`，可执行文件必须引用它；SQLite 提供者唯一来自 `libreader_catalog_sqlite.a(sqlite3.c.o)`，无系统 SQLite、无第二个静态 SDK。
- Info.plist：`CFBundleShortVersionString == 3.41.0`、`LSMinimumSystemVersion == 12.0`、`NSHighResolutionCapable`、`EXRSourceSHA == producer 提交`、`EXRRawSelectorEnabled` 与候选一致。
- 架构：可执行文件与每个 Frameworks 动态库均为单一 `arm64`，minos 12.0。
- 资源：`Sample.pdf`/`Sample.epub`/`reader-catalog-v1.sql`/`Reader.otf`/`Noto-OFL.txt`/`EXReader-LICENSE.txt`/`THIRD_PARTY_NOTICES.md`/`licenses/` 齐备，字体与许可证散列与 pin/安装树一致。
- producer `build.json` 的 `files` 映射与实际重算散列逐文件相等（多一个、少一个、改一个都拒绝）。
- 移位：文件集合与逐文件散列不变，路径含空格且非 ASCII。
- 离线：控制探针可达、同参数探针在包络内被拒；打开与重开报告 `passed=true`、`check_count >= 20`、`engine_version == 3.41.0`、`source_sha == producer`、`platform == macOS`，且三次运行的检查清单一致；重开必须存在上一次运行留下的状态。
- 签名事实：`codesign --verify --deep --strict` 通过、`Signature=adhoc`、无 `Authority=`；不要求 Gatekeeper 通过。

## 不授范围（validation.json 的 pending）

签名身份、公证、Gatekeeper、商店/发布、真机与 USB/读屏、长时阅读与性能预算、最终统一源码整合；`release_ready` 另列（分发字节里若含构建机绝对路径，按 G09 口径转交对应文件 owner，不在本包修）。

## 重新输入 source/run 表

- 重跑：在本分支 `workflow_dispatch`（或向 `tests/reader_final_s03/**` 推送）；同一时刻只有一个 live run（`concurrency: reader-final-s03`）。
- 只有原工件而不重建时，把证据 ZIP 解到任意目录后运行
  `python3 tests/reader_final_s03/aggregate.py --evidence <目录> --output <目录> --verifier-sha <受测 SHA> --producer-sha 15dab6b... --sdk-sha edddc463...`，
  它会用证据里的 `identity.json`、`manifest-*.json`、`smoke-*.json` 重算判定，不读本机产物。
