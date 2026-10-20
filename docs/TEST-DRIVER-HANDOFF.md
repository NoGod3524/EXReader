# 测试驱动修复交接

日期：2026-10-19。范围仅为解析测试驱动、样本保存和重放；整体开发路线仍见[HANDOFF.md](HANDOFF.md)。

> **完成状态（2026-10-19 后续处理）**：本交接中的改动已提交为 `c8aa950`，验证记录为 `ba657f3`。
> 卡点根因是 CBZ 的 central directory 把某个成员压缩尺寸写小（71 vs 本地头 77），miniz 的
> extract iterator 吃到截断 deflate 流后不前进。`src/cbz.c` 已改为按本地文件头取成员布局，
> 用有界 `tinfl_decompress` 循环（每轮必须有进展、输出封顶、完整成员校验 CRC）。908 字节
> 样本进入 `native-fuzz-driver` 回归并以 `EXR_FORMAT` 结束；有效 `comic.cbz` 在 GCC/MSVC
> 均重放成功。20 万次、5 种子、seed1 长跑完成（15,919 parsed，CBZ 40,235 attempts / 857
> parsed）。本地两套编译器 145/145；CI/sanitizer 以推送后的运行为准。

## 交接现场

- 仓库：`C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader`；ASCII入口：`C:/Users/Oscar/exr`。
- 分支：`codex/framework`；已推送代码：`d7aa4d0b5650f047243f97c4c36ee6bbf5d390f6`，SDK3.38.0、核心3.37.0、PDF3.38.0，MIT、ABI1、schema6。
- 已推送版本的[CI39356541064](https://github.com/NoGod3524/EXReader/actions/runs/39356541064)已7/7通过：三桌面143/143、sanitizer140/140、移动库与安装/裁剪/绑定消费通过。该次CI使用旧测试驱动，不能用来验收下述未提交改动。
- 用户要求这项小任务暂时交接；本地长测试已经停止，没有留下运行中的测试进程。
- 当前对话多次出现平台内容无法显示提示，具体触发原因未知；它与项目的编译和测试结果分别记录。

## 尚未提交的代码

| 文件 | 改动 |
| --- | --- |
| `tests/fuzz_parse.c` | 原保存逻辑仅rewind/fwrite，短输入会留下旧尾部。现检查定位、写入、flush并使用Windows/POSIX截断；旁存解析格式；增加直接重放、格式选项、格式计数和数字参数检查；统一失败清理 |
| `tests/test_fuzz_driver.c` | 新文件，28项检查：长→短→零字节记录、只读文件写失败、CBZ实际解析、扩展名/损坏头路由、数字溢出等 |
| `CMakeLists.txt` | 可选EXR_BUILD_FUZZ增加驱动回归目标，smoke语料增加CBZ |
| `.github/workflows/native.yml` | sanitizer环境执行驱动回归，失败时保留样本与`.format` |

工作树另有未跟踪的`docs/validation/2026-10-19-shading-extent-ci.json`，是上一个已推送批次的CI作业记录，尚未归一化补齐计数。不要把它当成本任务的新测试结果。

已备份代码补丁：`C:/Users/Oscar/exr-gcc/test-driver-handoff.patch`。在同一工作区接手时直接使用现有改动，不要重复应用。新测试源码仍在上表路径。

## 两个原始问题

1. 更短的下一条输入没有截断旧文件，因此落盘样本与实际传入解析器的长度不同。
2. 原驱动将所有ZIP头输入都送入EPUB解析器，包括`.cbz`。新驱动先由种子扩展名/原始头确定解析格式，变异后保持该格式；损坏文件头也进入原本要测试的解析器。

样本旁的`.format`保存实际解析格式。`--replay`不变异输入，默认读取该记录；也可用`--format cbz`显式指定。新驱动的统计不可与旧驱动成功解析次数直接当作同口径比较。

## 已通过的本地验证

- GCC16.2和MSVC Release均构建通过；两边`native-fuzz-driver`及`native-fuzz-smoke`各2/2通过，驱动回归28项。
- 另做18项命令行检查，含相同种子两次1000次运行的最终字节/格式一致、32字节上限、格式重放、空文件、坏格式记录和数字参数拒绝。
- 外部检查脚本及原始结果：`C:/Users/Oscar/exr-gcc/fuzz-cli-check.py`、`fuzz-cli-check.json`。这两个文件不在仓库中。
- 首次新回归把空TXT误期望为成功；核对公开入口后改为其既有`EXR_ARGUMENT`，两边复验通过。SDK行为没有为此改变。

## 当前必须调查的卡点

新的20万次变异运行**没有完成**。进程启动后约0.6秒保存了一份908字节的CBZ输入，此后记录时间不变、CPU持续增加，尚未输出首个10000次进度。已停止该进程并保留样本；目前没有调用栈证据，不能断言卡在CBZ、图片或ZIP的哪一个函数。

- 样本：`C:/Users/Oscar/exr-gcc/fuzz-stalled-cbz.bin`
- 格式记录：`C:/Users/Oscar/exr-gcc/fuzz-stalled-cbz.bin.format`，内容为`cbz`
- 字节数：908
- SHA-256：`449011aa8cdd09984120b894e94309570113d7d6f7ccbbced27792824f9f48a7`
- 原长测输出文件：`C:/Users/Oscar/exr-gcc/fuzz-campaign.bin`及同名`.format`，停止后保留。

下一步先对保留输入做**有时间界限的单次重放**，确认卡顿，再取调用栈和最小回归。不要先重跑整批20万次。相关入口包括`src/cbz.c`的打开/图像头读取和`src/images.c`的尺寸解析，具体位置须以证据定位。修复应落在实际循环或进度判断处，不能靠跳过CBZ或改回EPUB路由关闭问题。

## 复验入口

现有构建目录均已启用`EXR_BUILD_FUZZ=ON`：

```powershell
cmake --build C:/Users/Oscar/exr-gcc --parallel 4 --target exreader-fuzz exreader-fuzz-test
ctest --test-dir C:/Users/Oscar/exr-gcc --output-on-failure -R native-fuzz

cmake --build C:/Users/Oscar/exr-build --config Release --parallel 6 --target exreader-fuzz exreader-fuzz-test
ctest --test-dir C:/Users/Oscar/exr-build -C Release --output-on-failure -R native-fuzz
```

单次重放由外部进程设置超时；被测程序命令为：

```text
C:/Users/Oscar/exr-gcc/exreader-fuzz.exe --replay C:/Users/Oscar/exr-gcc/fuzz-stalled-cbz.bin
```

## 完成条件

1. 保留的908字节输入能在声明的时限内成功或以明确错误结束，并进入固定回归；如果无法复现，记录准确二进制、输入散列、环境和调用栈排查结果。
2. 两套编译器的28项驱动检查及smoke继续通过；新增长测中CBZ的attempts非零，并用原始有效CBZ直接重放证明解析成功。
3. 原5种子、seed1、20万次运行完成，保存各格式尝试/成功计数、输入及程序散列。不能把本次中止记为“无崩溃通过”。
4. CI验证POSIX截断、sanitizer驱动检查和样本/格式附件；本地没有sanitizer结果，不得代记通过。
5. 补齐验证记录和更新日志，再提交推送。当前为3.38.0验证工具修复，不逐项另升SDK版本。

整体WP16的字体/排版/绘制目标及每目标24 CPU小时仍未完成；本任务不等于WP16交付。

## 工作约束

不改写历史；不覆盖未提交内容；构建/测试期间不修改其输入。保留第三方版权和现有MIT许可，不新增贡献规范或与软件功能无关的署名内容。使用UTF-8。不要扩大本次任务到其他工作包。
