# H1：Windows/macOS 阅读构建验证

## 目标与输入

给独立 AI 的小包：把现有两个原生阅读 preset 的构建与安装消费验证扩展到 Windows/macOS，
不改引擎或 SDK 接口。按 [交接索引](reading-simple-index.md) 核对主线最新完整 SHA，
从该 SHA 新建独立分支和工作树，保留已联合验收祖先 S=`686ce2fe6c3463ef1b917569677ee9933e22faa9`。
主线首轮 `39852907619` 在测量自验失败；采用后续修复和新源码验收记录，不重置其他工作树。

阅读 `CMakePresets.json`、`tests/reading_core/CMakeLists.txt`、`.github/workflows/reading-core.yml`、
`tools/reading_core/smoke-manifest.json`，以及 `docs/READING-CORE-START.md`。

## 文件边界

只新增 `.github/workflows/reading-platforms.yml`、`tools/reading_platform_evidence.py`（确有需要才写）
及 `docs/READING-PLATFORMS.md`。不修改现有 Linux workflow、preset、消费者、性能工具、引擎或公开头。
遇到共享文件编译缺陷，交给主线最小复现与修法；不要复制另一套消费者绕过缺陷。

## 执行与出口

1. 使用 GitHub 托管 Windows/macOS runner，两个 preset 分别构建和安装。
   Windows 的 Ninja/MSVC 需先进入有效编译器环境，记录实际版本；macOS 记录 Xcode/Clang。
2. 原样构建 `tests/reading_core`，运行其安装后 C 消费者、C++ 头编译和现有 ctest。
   传入正确的 `EXR_EXPECT_LIBRARY`、字体与 fixture 绝对路径。
3. 复用 `tools/check_corpus.py` 和冻结九格式清单，整本执行，保留所有结果；合成 smoke 不算真实语料。
4. Linux 的 `check_reading_profile.py` 使用 `ldd`，不能直接在这些平台运行。
   导出目标约束由现有消费者 CMake 检查，运行依赖按 Windows/macOS 原生工具检查并留原始输出，
   记录已安装文件清单与大小；不把安装资源总量冒充阅读可执行体积。
5. 每个作业的 run/source/attempt、构建配置、字体/输入/程序散列、测试/失败日志与工件完整登记。
   不执行性能排名或捏造硬预算，本包只授予实际平台构建/安装/消费者/smoke 的结果。

交付固定完整 SHA、独立 workflow run、逐平台逐 profile 成败、工件身份/限制、可合入提交。
原失败保留；不得拼接旧源通过项。不改 GitHub 保护设置，不推默认分支、不合并 PR。
本地只读写源码/文档和 Git；所有测试与证据解析在云端。
