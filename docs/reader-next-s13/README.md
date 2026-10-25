# S13 CBZ 前导斜杠只读名称兼容候选

状态：**未接纳候选**（candidate-not-adopted）。源码 patch 仅存在于本目录，Actions 在
隔离 worktree 中应用；冻结 SDK 树、原测试、原夹具、其他包路径均未改动。

## 目标源码、SDK 与程序来源

| 项 | 值 |
| --- | --- |
| 固定起点 | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`（`codex/reader-next-round-20261025` 上的 `codex/reader-raw3-common-integration`） |
| 本包分支 | `codex/reader-next-s13` |
| 批准 SDK | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41.0）；旧 3.40 冻结于 `9854061be331fe603a1822d9b2b36ee357154927` |
| 基线树 | `git worktree add --detach build/s13/base e67d87c`，与批准 SDK 的 `src/ include/ cmake/ CMakeLists.txt` 逐字节相同（Actions 用 `git diff --quiet` 认证） |
| 候选树 | 同一起点 + 唯一 patch，`git status --porcelain` 必须只有 `" M src/cbz.c"` |
| 消费者程序 | `tests/reader_next_s13/reader_next_s13_probe.c`，只 include 公开 `exreader.h`，链接安装后的 `EXReader::exreader`（`find_package(EXReader 3.41.0 EXACT CONFIG COMPONENTS core pdf library)`） |
| 真实文件 | F5 固定清单 `tests/reader_real_corpus/manifest.json@278d6369` 的 `cbz-pepper-01/02`，字节与 SHA-256 逐条钉死，仅 Actions 下载 |

## 补丁范围

唯一改动 `src/cbz.c`（+45/−2，单文件），patch `s13-cbz-leading-slash.patch`，
后像 `candidates/reader-next-s13/src/cbz.c`。三份字节由 `manifest.json` 钉死并在
Actions 中互相校验（patch 应用后必须是后像的 blob）。

只做一件事：**ZIP 成员名恰有一个前导 `/` 时，在校验与分类处去掉它**。

- `exr_canonical_path` 本身**不改**（EPUB/HTML/导出等其它调用者行为不变），
  也**不**扩展到文件系统解压；CBZ 始终按 ZIP 成员索引只读取字节。
- 页面稳定 ID、排序键、`ComicInfo.xml` 识别、扩展名白名单、条数/字节/工作预算、
  取消点全部沿用原实现。ID 保持 ZIP 内的**原始成员名**（不重写发布方名字），
  因此任何返回的 page id 都是真实 ZIP 成员名，可在原归档中精确 lookup。
- `__MACOSX/`、`.开头`、`/.` 跳过规则改为作用在“去掉一个前导斜杠后”的名字上，
  与非斜杠归档保持一致语义。

明确保留拒绝（合成边界夹具逐条声明期望，见 `tests/reader_next_s13/cases.json`）：

| 形态 | 期望 |
| --- | --- |
| `//page.png`、`//server/share/page.png` | `Unsafe CBZ member path` |
| `/../page.png`、`/book/../page.png` | 先被既有 junk 规则（首字符 `.` 或含 `/.`）跳过，两树同为 `CBZ contains no supported image pages`；该类成员从不被读取 |
| `/C:/page.png`（驱动器） | `Unsafe CBZ member path` |
| `/dir\\page.png`（反斜杠歧义） | `Unsafe CBZ member path` |
| `/pa\0ge.png`（嵌 NUL） | `CBZ member name contains NUL` |
| `/a//b.png`（空段） | `Unsafe CBZ member path` |
| `/pa\xffge.png`（非法 UTF-8） | `CBZ member name is not UTF-8`（斜杠不绕过 UTF-8 门禁） |
| `/page.png` + `page.png`（规范化后重名） | `Duplicate CBZ member path after leading-slash normalization` |
| `/book/1.png` + `book/1.png` | 同上 |
| `page.png` + `page.png`（完全同名） | 原错误文本 `Duplicate CBZ page path or frame id`（旧行为逐字保留） |
| `/ComicInfo.xml` + `ComicInfo.xml` | `Duplicate ComicInfo.xml`（不作选择、不后者覆盖） |
| `/notes.txt`（无图页） | `CBZ contains no supported image pages` |

规范化碰撞检测发生在页展开之后、在原有 id 去重之前：键为“去掉一个前导斜杠”的名字，
只有**不同 ZIP 成员索引**命中同键才拒绝；同一成员的多帧共享键与索引，不会被误判。
既然后像 ID 保留原始名字（含斜杠），碰撞不会被原有 id 去重顺带覆盖，因此必须显式检查。

## 验收探针（公开 SDK）

`--probe <file.cbz> [library.sqlite]` 输出单份 JSON：打开状态/错误文本、页数、全部 page id、
几何、首/中/末页 `exr_fixed_render`（scale 1）尺寸与 RGBA FNV-1a 64 摘要、
同三页 `exr_fixed_draw` 实际交付的 image layer 摘要、越界页渲染拒绝与前后稳定性、
点捕获/解析（`exr_fixed_load_text`+`exr_fixed_anchor_create/resolve`）、进程内重开、
以及 SQLite 书架导入/笔记/重连。

CBZ 页无文本，因此捕获是**点书签**：`exact/prefix/suffix` 长度为 0，解析在空文档上按
公开语义落到页首的**零长范围**（FOUND，start==end==0，不凭空扩大范围）；同一选择器用
另一页 id 解析必须是 MISSING 且 start/end 为空，用于证明页路由而不是文本匹配。`--image <file>` 对**从原归档提取出的成员字节**单独
`exr_image_decode`，用于证明“page id → 真实成员 → 实际读取/渲染”三者一致。

## 云端验收项

Actions（`.github/workflows/reader-next-s13.yml`，仅 `codex/reader-next-s13`）在
Linux 与 Windows 各跑一遍：基线树与候选树各自 configure/build/install、各自跑**原
native ctest 全套**（JUnit 结果逐测试对比）、用安装后的公开 SDK 各编译同一份消费者，
再执行合成边界夹具（基线+候选各一次）、两份真实 CBZ（候选两份独立进程）、
成员字节独立解码对照，最后按声明期望比对并汇总。

判定：任一具名检查失败、缺失观测、进程非零退出、工件缺失都使 `accepted=false`；
文档封存用 `[skip ci]`。原两真实文件不改字节、不改预期拒绝：基线构建在同一
SHA-256 的字节上仍须给出 `Unsafe CBZ member path`。
