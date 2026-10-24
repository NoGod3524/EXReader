# J24：Unix 可重定位分发候选

本包从固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950` 独立实现，只改本包白名单：
`tools/reader_distribution_unix/**`、`tests/reader_distribution_unix/**`、
`.github/workflows/reader-distribution-unix.yml`、本文件与
`docs/validation/reader-distribution-unix.json`。SDK 冻结树（`src/`、`include/`、`cmake/`、
顶层 `CMakeLists.txt`、`tests/fixtures/`、`bindings/`、`native.yml`、`reliability.yml`）
与产品 schema（`apps/reader/store`）逐字不变；R6 已验收的六份原包及其散列不被改写或冒用。

## 解决的三件事

1. **Linux/macOS 构建路径**：候选不使用 CMake preset，而由工作流显式传入与 `reading-core`
   preset 相同的 20 个开关与 `CMAKE_INSTALL_PREFIX`，安装到短路径 `build/install-a`，再整体搬到
   另一条更长绝对路径下重建、重跑；搬动后的前缀不再依赖构建目录或安装目录。
2. **上游 pkg-config 绝对 prefix**：安装布局本身没有 pkg-config 单元。候选新增唯一的
   `lib/pkgconfig/exreader.pc`，其 `prefix=${pcfiledir}/../..`，其余变量（`libdir`、`includedir`、
   `vendordir`）都由 `prefix` 派生；`Libs`、`Libs.private`、`Cflags` 中不允许出现绝对安装路径或
   `-Wl,` 包装参数。审计同时用 `pkg-config --cflags --libs --static exreader` 反查：所有
   `-I`/`-L` 必须落在搬动后的前缀内，且组件归档、私有归档、`-pthread -lm` 齐全。
   上游依赖构建（libwebp、aom、sharpyuv）还会把私有静态库的 `*.pc` 一并装进 `lib/pkgconfig`，
   其 `prefix=` 是构建机的绝对路径。候选把这些私有单元移除并记录路径/字节/SHA-256/原 prefix 作为
   缺陷证据，只保留公共的 `exreader.pc`；私有归档已由 `Libs.private` 覆盖，消费者不需要这些单元。
3. **重复归档材料**：安装会同时写入 `LICENSE`、`THIRD_PARTY_NOTICES.md`（根与 `share/exreader/`）
   等字节相同的材料。候选按内容散列规划去重，只对 `docs/`、`share/`、`examples/`、`bindings/`
   与根许可/自述文件生效；组件归档、私有归档与公开头一律不参与。去重使用 `os.link` 保留每个路径，
   删除前后分别构建并运行消费者与九格式 smoke，再比对 PNG 摘要、逐项计数器与九条 smoke 结果；
   封包时重复成员以 tar 硬链接条目只存一份。

## 公开契约

~~~pkgconfig
prefix=${pcfiledir}/../..        # 任何前缀长度下都成立
libdir=${prefix}/lib            # 组件归档 libexr_<layer>.a
vendordir=${libdir}/exreader     # 私有静态依赖 libexr_vendor_<name>.a
includedir=${prefix}/include
Name: EXReader / Version: 3.40.0 / Cflags: -I${includedir}
Libs: -L${libdir} -lexr_<layer>...            # 依赖者在前，顺序取自安装后的 CMake 导出
Libs.private: -L${vendordir} -lexr_vendor_<name>... -pthread -lm [-ldl]
~~~

- **输入/输出**：`pkg-config --cflags/--libs/--static exreader` 的输入只有
  `PKG_CONFIG_PATH=<prefix>/lib/pkgconfig`，输出只有 `-I`/`-L`/`-l` 与系统线程/数学标志；
  不写出前缀以外的路径，不引入 rpath 或包装器参数。
- **内存归属**：pkg-config 查询是一次性进程，字符串随进程退出释放；SDK 侧内存归属仍是
  `include/exr/*.h` 已冻结的借用/拥有规则，本包不改动。消费者显式调用
  `exr_document_free`/`exr_layout_free`/`exr_font_free`/`exr_bitmap_free`。
- **线程/重入**：候选构建、去重、封包均为单线程一次性步骤；SDK 线程规则未变，消费者只在主线程调用。
- **错误**：`stage.py`/`transform.py`/`audit.py`/`seal.py` 以非零退出（stage.json 仍保留 `problems`），
  审计把每条判据写进具名 `checks`；`release_ready` 只在没有失败判据时为真。
- **取消**：无长驻服务；工作流超时（150/45 分钟）即整体取消，已上传工件保留。
- **提交边界**：候选只写入 `build/`，从不写源码树；封包只读候选树，输出目录已存在即拒绝。
- **硬上限**：文本扫描单文件 ≤4 MiB；`walk` 拒绝符号链接与越界/绝对成员名；归档只允许一个根目录；
  硬链接组必须指向已存在的同根成员；重复规划只接受字节完全相同（SHA-256 相等）的材料。

## 云端验收矩阵（命名结果）

- 守卫：`check_scope.sh`（HEAD==GITHUB_SHA、起点为祖先、冻结 SDK 树相等、产品 schema 相等、
  改动全在白名单）。
- 协议：`selfcheck.py` 在合成夹具上跑 11 条判据（链接顺序、私有归档顺序、pkg-config 往返、
  私有 pkg-config 绝对 prefix 识别、
  绝对 prefix/绝对库路径拒绝、组件覆盖、去重规划、树扫描、路径安全、封包/解包硬链接与篡改拒绝）。
- 两平台（ubuntu-22.04、macos-15）：真实构建安装 → 许可材料 → 候选 → 搬迁 → C/C++ 消费者与
  九格式 smoke → `audit before` → 去重 → 重建重跑 → `audit after` → 前后一致 → 封包 → 解包校验
  → 从解包树再建再跑 → `audit extracted` → 解包与去重后一致。
- 汇总：`aggregate.py` 用 `gh api` 读回 run/attempt/jobs/artifacts，重算 ZIP 摘要，解包归档，
  重算逐文件身份，并从上传字节再跑一次静态审计；任一缺项、跨源码、跨 attempt 或摘要不符即拒绝。

## 范围与未覆盖

授予范围仅限 Linux/x64 与 macOS/ARM64 的 `reading-core` 候选：可重定位安装、pkg-config 契约、
重复材料去重与解包往返、安装后 C/C++ 消费者与九格式 smoke 的真实行为。
不授予：Windows 分发、`reading-library`/可选组件 profile、性能/无障碍/真机/音频范围、
产品宿主接线（由 root 统一完成）、任何 tag/Release/正式签名。

## 复现

~~~bash
git push origin codex/reader-distribution-unix
gh run list --workflow=reader-distribution-unix.yml --branch codex/reader-distribution-unix --limit 1
~~~

受测源码、run/attempt、工件 ID/字节/digest/有效期与逐项结果记录在
[validation/reader-distribution-unix.json](validation/reader-distribution-unix.json)；验收前
`accepted=false`，真实运行后按实际范围回填。
