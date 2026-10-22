# 原生阅读 preset：Windows/macOS 构建验证（H1）

主线 `codex/r1-reading-core` 的 `b529513b7e8e8992786f8c679c0ec6c92110b035` 上新建分支
`claude/reading-h1-platforms`，保留已联合验收祖先 S=`686ce2fe6c3463ef1b917569677ee9933e22faa9`
（工作流首步再次校验）。只新增 `.github/workflows/reading-platforms.yml`、
`tools/reading_platform_evidence.py` 与本文；未改 Linux 工作流、preset、消费者、性能工具、引擎或公开头。

Linux 结果（源码 `54d8c592…`，run `39853356309`）与原失败 run `39852907619` 保持原样，不代替本包平台验收。

## 结果：4/4 作业成功

受测源码 `9b968a16fc47596725e849e56ee98e4c4c210b74`，
run [39854485070](https://github.com/NoGod3524/EXReader/actions/runs/39854485070)，attempt 1，push 触发。
结果来自 GitHub 作业日志与工件元数据；未下载工件或在本地执行任何测试。

| 平台 | profile | job | 安装消费者 ctest | 九格式 smoke | 依赖/配置判定 | 安装文件合计（字节） |
| --- | --- | --- | ---: | ---: | --- | ---: |
| Windows | reading-core | 120088990745 | 3/3 | 9/9 | accepted | 23955586 |
| Windows | reading-library | 120088990595 | 4/4 | 9/9 | accepted | 27383744 |
| macOS | reading-core | 120088990657 | 3/3 | 9/9 | accepted | 13781718 |
| macOS | reading-library | 120088990411 | 4/4 | 9/9 | accepted | 15547919 |

ctest 项：`installed-core`、`installed-chapter`、`installed-convert`，library 另加 `installed-library`；
所有导出头的 C++ 编译目标随消费者构建完成。消费者 CMake 判定 core/pdf 存在、音频/PDF 编辑/索引未导出，
且书库组件与 profile 一致。九格式 smoke 为 `check_corpus.py` 整本执行冻结清单
`reading-core-synthetic-smoke-v1`，全部 `passed`、`accepted: true`；它是合成 fixture，不计真实语料。

## 工具链

| 平台 | 镜像 | 编译器 | 其他 |
| --- | --- | --- | --- |
| Windows | `windows-2022`，ImageOS win22 / 20261012.333.1，X64 | MSVC `cl` 19.44.35229（VC Tools 14.44.35207），Windows SDK 10.0.26100.0，VS 2022 Enterprise vcvars64 | CMake 3.31.6，Ninja 1.11.1（pip `ninja==1.11.1.1`），Python 3.12.10 |
| macOS | `macos-15`（15.7.9），ImageOS macos15 / 20260907.0337.1，ARM64 | Xcode 16.4（16F6），Apple clang 17.0.0（clang-1700.0.13.5） | CMake 4.4.3，Ninja 1.11.1，Python 3.12.10 |

Windows 先用 vswhere 定位 vcvars64 并导出环境，`CC=cl`/`CXX=cl`，preset 原样使用 Ninja 生成器。

## 工件

| 工件 | ID | 压缩字节 | digest |
| --- | --- | ---: | --- |
| reading-platform-Windows-reading-core-39854485070-1 | 12458373465 | 8442552 | `sha256:be4e6f7c7abc935c9f1a3c8231c1c59dfabb20c914f2d9099ec7b33dcf28234c` |
| reading-platform-Windows-reading-library-39854485070-1 | 12459196985 | 9656903 | `sha256:08d68fdc5908e53e95816a05241c32a0a20edb78ca6d12852913bd06b151bc0e` |
| reading-platform-macOS-reading-core-39854485070-1 | 12459077056 | 5727637 | `sha256:26ed1646d098853cb9736ca77f8bdb8431134ca2f0c048c5f8dc98df6851914a` |
| reading-platform-macOS-reading-library-39854485070-1 | 12458773358 | 6533197 | `sha256:ad9b0b44dd0553712fa3cdff00863ab542d980f8a5caca140a4e08adf3395225` |

每个工件含：安装 SDK（`stage/`）、`toolchain.txt`、配置/构建/安装/消费者日志、`CMakeCache.txt`、
`consumer-tests.xml`、`LastTest.log`、smoke 逐格式结果与 `summary.json`（含程序/字体/清单散列）、
`platform-evidence.json`。后者记录 run/source/attempt、preset 缓存变量比对、编译器身份、
已安装文件逐项路径/大小/SHA-256、各消费者程序散列及 `dumpbin /dependents` 或 `otool -L` 原始输出。

## 限制

- 运行依赖检查：拒绝 webview/webkit/chromium/electron/faad/minimp3（core 另拒 sqlite）。
  macOS 还拒绝 `/usr/lib`、`/System/Library` 以外不存在或 `@rpath` 引用；Windows 不另做解析判定，
  同一程序已在 ctest/smoke 中被加载器实际运行。静态链接时 sqlite 不会以 DLL 出现，书库组件的
  有无由消费者 CMake 导出目标检查负责。
- 安装文件合计含头文件、文档、示例与静态归档，不是阅读可执行体积；消费者程序是测试宿主。
  未执行性能采样或排名，未设任何体积/性能预算。
- Windows 的 Git bash PATH 中 `C:\Program Files\Git\usr\bin\link.exe` 排在 MSVC `link.exe` 之前，
  CMake 选择的链接器路径见工件 `CMakeCache.txt` 的 `CMAKE_LINKER`；构建成功但该项未在日志单独判定。
- 文档提交 HEAD 晚于受测源码；受测身份以 `9b968a1…` 为准，文档提交带 `[skip ci]`。
- 未改分支保护、未推默认分支、未合并 PR；`reading-platforms.yml` 仅在本分支 push 或手动触发。
