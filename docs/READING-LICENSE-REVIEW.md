# H5 阅读包许可证材料独立复核

H5 原交付的两份 Linux preset 登记清单一致性检查通过，但留有发布材料缺口。
后续修补 `72c1e89` 已在两 preset 严格通过；尚未合入 R5 共同源码。
下文保留原交付的问题与身份，修补结果另列。
本复核只读云端源码、作业日志和工件身份元数据，并核对本工作树安装规则；未下载工件或执行本地检查。

## 后续修补：两 preset 严格通过

分支 `codex/reading-license-fixes`，受测完整源码 `72c1e89659679b7d7b76504007a84d6d8c453db3`，
文档 HEAD `e0efc43a334677d100f1d12dcfb01e33df9826dd`。
run [39862694733](https://github.com/NoGod3524/EXReader/actions/runs/39862694733) attempt 1：
core job `120117102454`、library job `120117102853` 同源成功；可选 material-pins 作业按条件跳过，不计为发布检查。

两份完成日志均确认干净构建/安装、`materials_check_passed=true`、`release_ready=true`，
`failures=[]`、`pending=[]`、`mandatory_missing=[]`；31 项反例、1 项必需材料缺口阻断、3 项正控通过。
WebP PATENTS、Expat 根 COPYING、SQLite 来源声明已装入，zlib 在 libtiff 目录的重复材料已移除。

成功工件 `12462960815`（core，80652 B）、`12461459484`（library，81548 B）
同 run/source、未过期，Actions digest 均为合法 SHA-256。
前轮 `39862581613` 因 repository-origin 路径错误失败，修复后两 preset 整轮重新执行；旧失败保留。
这授予 Linux 两阅读 preset 的发布材料门禁通过，其他平台和宿主字体仍分别验收。

## 固定身份与云端结果

| 项目 | 身份/结果 |
| --- | --- |
| 分支 | `handoff/reading-h5-licenses` |
| 受测源码 | `e3fa3f7748e9b06896487ba5c7cd48d9cf290b5b` |
| 文档 HEAD | `b365de7d31a2daca4f208dc625d064691fc331ec`，直接父提交为受测源码，只有两篇文档新增 |
| 云端 run | [39858675511](https://github.com/NoGod3524/EXReader/actions/runs/39858675511)，attempt 1，success |
| `licenses (reading-core)` | job `120103386597`，全部步骤 success；报告 `failures=[]`、pending 2 项 |
| `licenses (reading-library)` | job `120103386041`，全部步骤 success；报告 `failures=[]`、pending 3 项 |

两个 job 的 `head_sha` 与完成日志 `source_sha` 都等于受测源码。
各 job 包含干净 configure、build/install、材料检查、拒绝回归和上传步骤；
自检日志均为 `negative_cases=23`、`pending_cases=1`、`manifest_components=21`。

| 工件 | ID | 字节 | Actions digest |
| --- | ---: | ---: | --- |
| `reading-licenses-reading-core-39858675511-1` | 12460308703 | 79546 | `sha256:cd727c19fe2cb05d6992d26642d317661fd751b848519aea062d60bb63c9ef0d` |
| `reading-licenses-reading-library-39858675511-1` | 12460902628 | 79734 | `sha256:437745e7bfc0bbfd0d367edd679c49ab4dfadf9a5cf3cf24a7cc068e183a832f` |

两份工件的 `workflow_run.id/head_sha` 同源，均未过期，到期时间为 `2027-01-20T21:36:50Z`。
上表核对的是 Actions 提供的工件身份；逐项报告结论取自同次完成日志。

## 门禁实际语义

以受测源码的 [`tools/check_reading_licenses.py`](https://github.com/NoGod3524/EXReader/blob/e3fa3f7748e9b06896487ba5c7cd48d9cf290b5b/tools/check_reading_licenses.py) 为准：

- 第 369、377、389 行把组件 pending、无法确认版本、未登记安装的上游 notice 加入 `pending`。
- 第 431–435 行的成功条件只有 `materials_check_passed: not failures`。
- 第 453 行的退出码只看该成功字段，完全不检查 `pending`。
- [`tests/check_reading_licenses.py`](https://github.com/NoGod3524/EXReader/blob/e3fa3f7748e9b06896487ba5c7cd48d9cf290b5b/tests/check_reading_licenses.py) 第 155–157 行明确要求：新增上游 `PATENTS` 而不安装时，仍应材料检查通过，同时产生 pending。

这与 H5 文档所说的“只检查已登记材料、未解决项另交集成人”一致。
但该工作流不能直接作为“发布材料齐备”的通过门槛：未知或漏装的原文可以在绿色 job 中继续存在。

最小修法是保留库存检查字段，另提供严格发布条件：
`release_materials_ready = materials_check_passed and not pending`。
发布作业必须检查严格条件；可用一个 `--require-no-pending` 开关控制退出码，普通审计仍可列出 pending。
新增回归应证明缺 `PATENTS`/SQLite 材料时严格模式拒绝，修复后严格通过；不要删除现有 23 项拒绝回归。

## 材料问题与最小修法

下列安装行号来自受测 `CMakeLists.txt`，本工作树对应规则一致。

| 项目 | 已确认事实 | 最小修法 |
| --- | --- | --- |
| WebP `PATENTS` | 第 974 行只安装 `COPYING`；两份完成日志都列出 `libwebp: upstream notice file PATENTS is not installed`。上游固定 v1.5.0 的 `PATENTS` 是独立附加专利授权文本 | 同一 `EXR_ENABLE_IMAGE_WEBP` 条件下，把 `${libwebp_SOURCE_DIR}/PATENTS` 加入已有安装规则；在组件清单登记原路径、目标路径和固定散列，再跑两 preset |
| SQLite 随包声明 | 仅 reading-library 启用；脚本检查 `sqlite3.c` 头部一句 public-domain dedication 并把缺少随包文件列为 pending。当前没有 SQLite license 安装规则 | 新增 `licenses/sqlite-public-domain.txt`，原样保留固定 amalgamation 头部 dedication 并注明版本/来源；在 `EXR_ENABLE_LIBRARY OR EXR_BUILD_TEXT_INDEX` 下安装到 `share/exreader/licenses/sqlite/`。清单登记并核对来源文本，不伪造上游不存在的 `LICENSE` |
| zlib 放在 libtiff 目录 | 第 977 行把 zlib 的 `LICENSE` 安装为 `licenses/libtiff/LICENSE`，第 978 行又正确安装到 `licenses/zlib/LICENSE`。组件清单将这两份都登记为 zlib，因此错误目录不会触发失败 | 从第 977 行移除 `${zlib_SOURCE_DIR}/LICENSE`，保留 libtiff 的 `LICENSE.md` 和第 978 行；同步删除清单中的 zlib 重复目标。干净安装应证明旧误导路径不再出现 |
| Expat 两份 COPYING | 第 970 行只安装 `expat/COPYING`。固定上游根 `COPYING` 年份是 2001–2026，子项目文件是 2001–2025；两份日志均列根文件为 pending | 保留既有子项目文件，另把根 `COPYING` 安装到 `licenses/expat/upstream-root/COPYING`，清单分别固定散列。使用子目录可保持源文件名，兼容检查器当前不允许 rename 的规则 |

WebP 与 Expat 原文已直接读取各自固定上游 tag 核对；这些是实际不同的文件。
zlib 是文件归属目录误导与重复材料问题，脚本中的组件归属本身仍是 zlib，不能说它错误识别了许可证字节。
SQLite 上游没有单独许可证文件；这里要求补的是可随 SDK 审阅的来源声明材料。

关于 Apache-2.0 来源，H5 已记录 PDF.js 数据未在构建时下载、其上游 NOTICE 未由本工具确认。
该项仍列发布前待核，不扩展成新扫描平台；先检查固定来源是否有适用 NOTICE，有则同样登记原文并安装。

## 接续出口

H5 当前可接收为“两 preset 的依赖来源、开关、链接归档、已登记安装材料与 23 项反例检查”的交付。
不能把它转授为发布材料全部齐备，也不能扩大到 Windows/macOS/Android、宿主字体或音频构建。

后续只需一个小修复包：调整上述安装规则/SQLite 声明，更新固定清单，加严格模式与缺材料拒绝回归，
在同一新源码上重新运行两 preset。交付应同时给出 `failures=[]`、`pending=[]` 与严格发布条件通过。
旧 run 与 pending 原样保留；本轮只复核，不修改 H5 脚本、安装规则或分支。
