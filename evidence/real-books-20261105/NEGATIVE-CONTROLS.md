# Pass A 负例与去重复核

结论：**检查器可信**。结果只保留机器侧证据，未记账。

语料为本地商业书，不入库；本目录只含元数据与结果。三个派生输入只写入经核对的本地 Temp 专用目录，运行后全部删除；原 16 个书籍文件及其 SHA-256 未改变。

同一计时 CLI 与同一 SDK DLL，哈希均与正例一致；每次通过 `Start-Process -WindowStyle Hidden -Wait` 执行，stdout/stderr 重定向至仓库外临时文件。

本轮未在交互桌面上创建任何可见窗口。未启动 GUI、未改产品代码、未跑 CI。

- CLI SHA-256：`c0aa73928a5a8458e12e442efed9acdaedc707abbd4073a7e02ba6fca72ce510`。
- SDK DLL SHA-256：`3cde779eb65b0ace00165b9dbe18d85a44833653d374567301a8a0bf1e0c4ab8`。

## 截断 EPUB

保留 Mango Street 前 26167 字节（原 87225 字节的 30%，向下取整），截去其余 70%。
- 临时输入：`truncated-head-30-percent.epub`，26167 bytes，SHA-256 `f0e30f43e947569451e758916a25d5895c5c244f4aec0b73ec823866d4ae7d22`。
- 实际 exit code：`1`；预期格式拒绝：`true`。

实际 stderr 首行：
```text
ZIP read outside the source
```

实际 CLI JSON：
```json
{"schema":1,"engine_version":"3.42.0","status":5,"stage":"open","parts":0,"completed_parts":0,"pages":0,"text_bytes":0,"complete":false}
```

## PDF 改名 EPUB

PDF 原字节不变，仅改扩展名为 .epub。
- 临时输入：`pdf-renamed-as-epub.epub`，1713322 bytes，SHA-256 `c9373b7dbda128fea031616b444ca490a3cd59dccb3f02cb2512fd9957a0fdb7`。
- 实际 exit code：`1`；预期格式拒绝：`true`。

实际 stderr 首行：
```text
Invalid ZIP source
```

实际 CLI JSON：
```json
{"schema":1,"engine_version":"3.42.0","status":5,"stage":"open","parts":0,"completed_parts":0,"pages":0,"text_bytes":0,"complete":false}
```

## 仅 mimetype 的 ZIP

ZIP 只含 mimetype=application/epub+zip；无 container.xml、OPF 或章节。
- 临时输入：`mimetype-only.epub`，134 bytes，SHA-256 `6351c2bc30ba69ab0eba51f98ee553aee98c75815c3e20496250e06a9eb01bce`。
- 实际 exit code：`1`；预期格式拒绝：`true`。

实际 stderr 首行：
```text
ZIP member missing: META-INF/container.xml
```

实际 CLI JSON：
```json
{"schema":1,"engine_version":"3.42.0","status":5,"stage":"open","parts":0,"completed_parts":0,"pages":0,"text_bytes":0,"complete":false}
```

## 四行抽样

| 文件 | bytes | parts | pages | first_render_ms |
| --- | ---: | ---: | ---: | ---: |
| The House on Mango Street (Sandra Cisneros) (z-library.sk, 1lib.sk, z-lib.sk).epub | 87225 | 4 | 179 | 5.679 |
| The Fire This Time A New Generation Speaks about Race (Jesmyn Ward) (z-library.sk, 1lib.sk, z-lib.sk).epub | 6496058 | 46 | 314 | 20.745 |
| The Autobiography of Malcolm X. (Malcolm X, Alex Haley) (z-library.sk, 1lib.sk, z-lib.sk).pdf | 1713322 | 1 | 279 | 50.984 |
| Zami A New Spelling of My Name - A Biomythography (Audre Lorde) (z-library.sk, 1lib.sk, z-lib.sk).mobi | 590081 | 1 | 602 | 3.293 |

first_render_ms 实测第一次栅格化 API 的墙钟耗时：EPUB/MOBI 为 exr_render_page_color，PDF 为 exr_fixed_render。计时从调用前至返回后，不含打开、解析、分页或屏幕显示。这四行均为非零且互异；首屏耗时不要求随整本大小或页数单调增加。

## 去重

- 从测试语料清单移除：`Between The World and Me (Ta-Nehisi Coates) (z-library.sk, 1lib.sk, z-lib.sk) (1).epub`。
- 重复 SHA-256：`3d909ac99c4388022a6576475b81c5d458490337aba08b0e7ba311bc18ab68a5`；415133 bytes，逐字节比较全等。
- RESULTS.csv 现为 15 本（13 EPUB / 1 MOBI / 1 PDF）；原始商业文件未物理删除。原始 16 次实测的双版本对比保留在 README 供追溯。
- 保留的无 (1) 后缀版本：parts=14，pages=178；两版的结构统计一致。
