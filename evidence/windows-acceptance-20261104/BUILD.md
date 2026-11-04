# Windows 交付包 — 2026-11-04

- 源码：main 当时 tip `4efd33666640e8bd8409e15c432767572894226c`；Release tag `windows-preview-20261104-4efd3366` 指向同一提交。
- 构建：[run 41909199114](https://github.com/NoGod3524/EXReader/actions/runs/41909199114)，attempt1，`native.yml` 输入 `scope=p-windows, fault=none`；仅 windows-packaging 执行并通过，其他 job 全部跳过。
- CI 宿主自检：26 项通过，SDK 3.42.0，Windows x64；PE 头验证为 AMD64。10 项人工验收未执行，见 [CHECKLIST.md](CHECKLIST.md)。
- [Release 页面](https://github.com/NoGod3524/EXReader/releases/tag/windows-preview-20261104-4efd3366)；[直接下载 ZIP](https://github.com/NoGod3524/EXReader/releases/download/windows-preview-20261104-4efd3366/EXReader-Windows-4efd3366.zip)。
- ZIP：`EXReader-Windows-4efd3366.zip`，17614556 字节，37 个文件。
- SHA-256：`d9b914a33af1a668dd3344f11f0c06f4a25d903205acd6c2b8d6bcf00d709d71`。
- [完整包内清单](PACKAGE-FILES.txt)：每个文件的路径、大小和 SHA-256；[整包校验值](SHA256SUMS.txt)。
- 下载保留：Release 附件不自动到期，覆盖至少 90 天窗口（2026-11-04 至 2027-02-02）。[原始 CI artifact](https://github.com/NoGod3524/EXReader/actions/runs/41909199114/artifacts/13362830087) 由 GitHub 登记 90 天，到期 `2027-02-02T20:42:50Z`。原始 artifact 中的旧 ZIP 未含交付说明，最终交付以 Release ZIP 为准。

## 组包与核对

从成功 run 下载原始 artifact13362830087，核对原始 build.json 的 source_sha、26 项 self-test 报告和全部 33 个原始文件 SHA-256；原始 ZIP 检验无损坏。最终 ZIP 只新增 README.md、FONT-README.txt、BUILD-INFO.json、SELFTEST-report.json；EXReader.exe、exreader.dll、字体、示例和许可证字节保持不变。最终 ZIP 37 个文件再次通过 CRC 和清单核对；没有修改源码、治理文件或修复 bug。

最终 ZIP 含 EXReader.exe、exreader.dll、Reader.otf/OFL.txt、Sample.epub、Sample-positive.epub、两个 PDF 示例、README.md、FONT-README.txt、构建/自检记录、LICENSE.txt、THIRD_PARTY_NOTICES.md 与 licenses/。README 给出解压启动、独立测试 profile 和数据清理说明；字体说明记录固定来源和 OFL 许可。

本轮只完成构建与交付，不将自动自检当作人工产品验收。没有执行人工交互用例；发现问题按 CHECKLIST 记录，不在本轮改动产品。
