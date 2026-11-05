# HANDOFF-RESULT-C05

分支 `codex/reader-next-c05`，固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`。

## 结论

Windows FB2 查找差异是**消费者错误**：F5 消费者用 `char **argv` 取查询，Windows ANSI 代码页 1252 把 Cyrillic 变成 `?`（`Бретёр`→`3f3f3f3f3f3f`，`портрет`→`3f3f3f3f3f3f3f`）。SDK 3.41 对精确 UTF-8 字节的投影与 find 在两平台一致。没有 SDK 缺陷，故没有 SDK patch。原 F5 文件、预期、F5 的“未命中”记录都未改动。

## 固定身份

- 代码/验收源 SHA：`1659f83491985baa26b609f287a02a01744bc6b2`（工作流在此 SHA 执行；其后只增加文档与本文件，均 `[skip ci]`，不改被验收代码）。
- 文档与本文件：本分支其后的提交（`docs/reader-next-c05/README.md`、`HANDOFF-RESULT-C05.md`）。
- SDK 源：`edddc463c06ed5731195cdb8f06b2df6dff7699e`（CI 隔离 worktree 构建；`src include cmake CMakeLists.txt` 相对本 SHA 零差异），版本 3.41.0 / ABI 1。
- F5：提交 `278d63691a4c73e7aa932d71a40a5938c5427514`，清单 blob `72841cba…`，LF SHA-256 `be300d9a…`，CRLF 形式 `2651b03d…`（即 F5 记录值）；原消费者源 `consumer.c` `f2b5d06d…`、`CMakeLists.txt` `545147fa…`，均由 CI 校验。
- 原件：`fb2-breter` 196,462 B `8a62c0fb0b84560cbdca693953533b71b7572568440c6da988e41f26b0d0d74d`；`fb2-portraits` 424,614 B `10f671903db641921c67b8a9af198dd6d6f7f55be52085bc0749b197ea6f27e7`。读回 SHA 与原件一致。
- 全文投影 SHA-256：breter `16a7b7e5a2b87de8…`（184,330 B，匹配 21 处，首偏移 30），portraits `ca358522ba003c9c…`；Windows 与 Linux 一致。

## CI

通过轮次：run `40227530028`，attempt 1，成功；jobs：guard `121271980501`、linux `121272029722`、windows `121272029760`、aggregate `121272882327`。

工件（30 天，到 2026-11-24）：

| 名称 | ID | 字节 | SHA-256 |
| --- | --- | --- | --- |
| c05-windows | 12611572090 | 3,209,759 | `9bab6475f8a643961e66ca48f46ba202e919ffe1ab4afa50d0dce9fe5afa9983` |
| c05-linux | 12612460301 | 2,216,008 | `af913fba413011d16a411c510f5182726c9d7cf91c1d7647b15970126b7d434b` |
| c05-aggregate | 12611424945 | 1,144 | `59cfe7c37a8b05afe3d8f974c194920619c649df24e2ad917f078999506db92a` |

程序 SHA-256：
- 新消费者 Windows `093f32da5253c69e9635650323acdab9d8c85bf9cb355a70afe02eed5187de33`；Linux `c266f6d809486efc01cbdce7eef961a7dac7c3c899535a620ef61dc566fa3d27`
- 原 F5 消费者重建 Windows `84e508a9…`；Linux `53db485c…`
- Windows `exreader.dll` `710ebf27be42c0acb90eefa759a59eab426089c5432ac665deee1cd5e5443388`；Linux `libexreader.so.3.41.0` `05f4425193c61bd7086d3816b05d6c900d4f64bc90ba4f478a33f02892b6cd40`
- Windows 源字符集对照（`/utf-8` 关闭）`c47e33fb…`（诊断，不作门禁）

结果：每平台 summary `accepted:true`，Windows 948 项、Linux 968 项具名检查零失败；聚合 14 项零失败（两平台来源/run/attempt/F5 身份一致，五份文件输入与全文投影 SHA 逐一相同）。

## 保留的旧失败与对照

- 原消费者在同一 3.41 SDK 上复现：Windows 两份均 `find=miss`，回显查询字节为 `3f…`；Linux 两份 `found`。
- Windows ACP=1252、OEM=437、控制台 65001；MSVC 19.51；`/utf-8` 开启。raw argv 查询未命中（0 处），宽命令行路径收到精确字节并命中 21/8 处。
- 失败轮：run `40227105735`（`1856e342…`）。探测两平台均通过，聚合失败于 `same_identity`——我把含每个 runner 下载次数/CDN 最终 URL 的 identity.json 整体比较，属我的判定代码错误；已改为比较去除下载记录的稳定身份。该轮工件保留在云端，未作验收证据。

## 范围与未验证项

- 覆盖：公开导入/读回、文件与内存两路打开、全文投影、独立扫描、find（文档与 fixed-text 两条公开入口）、取消/重试、anchor 创建/解析/取消/重开、Cyrillic/NFC/NFD/非 BMP/混合换行正负例、两平台投影一致。
- 未验证：页面布局/渲染与页数（F5 原值 128/65 与本次 143/74 的差来自 Arial 与 DejaVu 字体，未建断言）；Windows 之外的 ACP（如 936/932）；3.40 冻结 SDK 上的原失败重放（原失败在 3.40 记录，本次只在 3.41 复现）；未做 SDK 保护树或 root 的最终同源验收。
- 未使用额外 agent、cpuse；未建 PR/tag/Release；仅推功能分支。共 2 轮 CI（上限 3）。
