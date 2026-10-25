# S15 root review: existing imported SDK targets

## 结果

修复受测源码 `1ca21a1a52b565c1e4de5f79a8e10921c0c77b46`，run [40236846254/1](https://github.com/NoGod3524/EXReader/actions/runs/40236846254) 五个作业 completed/success。Linux、Windows、macOS 原 44 项具名检查均保留；真实 frozen 3.40 原 6 项保留；另加的 source/installed 真实预载检查 16/16 通过，strict 在 Actions 中认证 ZIP 和已安装 gate/Config 字节。没有用本地构建、测试、语法检查或工件下载作证。

## 原缺口与真实复现

先于修复的 source `827bda743e5f67af3d84b9f91d7ee2878be961c2`，run [40236360132/1](https://github.com/NoGod3524/EXReader/actions/runs/40236360132) 保持 failure。该轮未改模块，只新增真实 3.40/3.41 SDK 预载回归。三平台原 44 项仍全通过；在 source 与 installed 两种入口，340→341 和 341→340 四次 configure 全部意外 exit0，`EXReader::exr_library` 前后仍指向预载前缀。四个同版本/同前缀正控正常成功。

尤其 installed 的 340→341 路径，`EXReader_VERSION` 已报告 3.41.0，但 target 的 archive 仍是 `s15-frozen-src/.../stage/lib/libexr_library.a`。原 EXACT 版本检查只能约束选中的 Config 元数据，无法代替已经存在的 imported target 来源核验。SDK、导出接口和原功能检查无须改变也能复现这个问题。

## 修复面与兼容性

只在 optional `original-export` 包内增加 `EXReaderSdkTargetGuard.cmake`，Git blob `98d0c8ddaf006591014203141f1faf650cc3ba4c`。它复用 revisions raw Config 的 REAL_PATH、版本头和 imported archive 原点检查模式，按 SDK 的 public component / private vendor 闭包读取核验；没有 `set_target_properties`，不会覆盖或修补外来 target。

源码 `find_package(EXReader ... EXACT)` 后与安装 Config 的 `find_dependency` 后均调用：

```cmake
include("${CMAKE_CURRENT_LIST_DIR}/EXReaderSdkTargetGuard.cmake")
_exr_sdk_target_provenance(EXReader::exr_library "${EXReader_DIR}" "3.41.0")
```

源码入口使用 `${EXR_SDK_VERSION}`；安装 Config 配置为该次安装的固定版本。default 仍为 3.40.0，3.41.0 仍须显式请求。helper 可原样安装到 font-library 等 optional 包旁，换成其实际 SDK 根 target（例如 `EXReader::exr_core`）；无需改 SDK、公共头或引入跨包框架。

`include/` 与 `src/` 相对复用模块 `25cd7b4b` 逐字不变；C ABI、0.1.0 包版本、导出文件行为、取消与无覆盖规则不变。`src/include/cmake/CMakeLists.txt/bindings` 的 SDK 边界相对 approved `edddc463` 不变。附加 gate 检查物理来源、头版本和文件存在性，不声称认证任意被恶意改写的第三方 SDK 安装。

## 16 项真实预载检查

每个组合均使用真实构建安装的 frozen 3.40 与 approved 3.41，未重标包元数据：

- 入口：源码 `add_subdirectory`、已安装 `find_package`。
- 预载：完整 SDK targets、只预载 SDK private vendor targets（`EXReaderDependencies.cmake`）。
- 方向：340→341、341→340 均由 provenance gate 拒绝；340→340、341→341 均通过且 target 位置不变。

合计 8 个外来前缀拒绝、8 个同前缀正控。private-only 检查补足了“public library target 新建正确，但预载 vendor 依赖仍来自旧前缀”的逃逸。strict 重新读取这 16 条 configure 日志，并把真实安装的两份 helper 字节绑定当前 source helper、两份 Config 绑定各自固定版本调用；原六项 frozen 检查集合保持原样。

## 作业与工件

| job | id | 结果 |
| --- | --- | --- |
| original export 3.41 / Linux | 121300132295 | success |
| original export 3.41 / Windows | 121300132211 | success |
| original export 3.41 / macOS | 121300132400 | success |
| frozen 3.40 + preloaded targets | 121300132015 | success |
| strict S15 evidence | 121301127628 | success |

原始工件身份在 `root-review-evidence.json`。前三平台工件和 frozen 工件均由原 strict 下载后按大小/散列认证；terminal evidence 工件身份只从 API 读取，未把其自证当作上游验证。

## 接入与范围

候选 branch `codex/reader-next-s15-root-review`，按顺序取 `827bda74` 回归与 `1ca21a1a` 修复（均基于原 docs `6e64ecd5`）；公共源码不要用整个旧起点替换。产品包精确新增/变更路径是 `apps/reader/original-export/{CMakeLists.txt,EXReaderOriginalExportConfig.cmake.in,EXReaderSdkTargetGuard.cmake}`，所有公共 include/src 保持原样。新增回归为 `tests/reader_next_s15/check_existing_targets.py`，扩展同包 workflow 与原 strict 的 frozen 检查；本封存文档独立。

仍为独立包候选。宿主选择器/导出 UI、share 注册、移动端、六平台统一来源、性能和电源故障均未授予；Windows mid-stream disk-full/fsync 的原 UNAVAILABLE 保留。root 接入后需保留旧判定，并用显式共同来源策略重跑，不能拿本分支的独立成功替代公共 source 验收。
