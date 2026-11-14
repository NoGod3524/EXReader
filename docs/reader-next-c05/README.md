# C05 Windows FB2 查找差异：根因与验收

固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，分支 `codex/reader-next-c05`。
SDK 为批准的 3.41 源码 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，CI 在隔离 worktree 构建并安装；本包不改 SDK，也不需要 SDK patch。

## 归因

**消费者错误，不是 SDK 文本投影或 find 缺陷。** F5 消费者以 `char **argv` 接收查询。Windows 的 `main` 把命令行按 ANSI 代码页（runner 上 ACP=1252）转换，Cyrillic 无法表示，被替换为 `?`：

| 文件 | 发送的 UTF-8 查询 | Windows 消费者实际收到 |
| --- | --- | --- |
| fb2-breter | `d091d180d0b5d182d191d180` | `3f3f3f3f3f3f` |
| fb2-portraits | `d0bfd0bed180d182d180d0b5d182` | `3f3f3f3f3f3f3f` |

SDK 对 `??????` 找不到是正确结果。MSVC `/utf-8` 在原消费者里已生效，不是原因；`C05_SOURCE_UTF8=OFF` 的对照构建只影响 `u8""` 字面量（被二次编码），普通字面量仍是 UTF-8，且不影响本问题。原 F5 文件与预期未改，原消费者由固定源码（SHA-256 `f2b5d06d…`）在 CI 原样重建并重跑，Windows 复现 `find=miss`，Linux 为 `found`。

新入口 `candidates/reader-next-c05/probe.c` 以 ASCII 十六进制传查询字节；另外分别探测 raw argv 与 Windows `GetCommandLineW` 宽路径（后者给出精确 UTF-8）。

## 验收内容

- 输入：F5 固定清单 `278d6369` 的两份真实 FB2（字节与 SHA-256 与清单一致，CI 下载后校验）和三份合成 FB2（Cyrillic 预组合/组合字符/大小写、非 BMP、混合换行）。
- 每个文档：公开 `exr_library_import`+`exr_library_blob` 读回、`exr_document_open` 与 `exr_document_open_memory` 两条路径的全文投影一致、投影按独立 Python 扫描复核（UTF-8 合法性、标量/非 BMP/CR/LF/组合字符计数）。
- 18 个正负查询（NFC/NFD、大小写、无分音符、非 BMP、换行拼接、`?` 误码、缺失、非法 UTF-8）：`exr_document_find` 与 `exr_fixed_text_find` 的计数/首末/前 16 个偏移必须等于独立 `bytes.find` 扫描；合成文件另有事先声明的计数。
- 5 档取消点 × 重试（`find`）与 3 档 × 重试（`anchor_resolve_ex`）：取消不留结果，重试结果与基线相同。
- 首/末出现处的真实 anchor capture/resolve，重开（文件与内存两路）后再次 resolve。
- 跨平台聚合：两平台输入、全文投影 SHA-256 逐文件一致。

页数不属本包范围：原失败时两平台页数不同（128/65 与 143/74）仅因字体不同（Arial/DejaVu），未作为本包断言。

结果、run/attempt 与工件身份见仓库根 `HANDOFF-RESULT-C05.md`。
