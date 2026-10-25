# C04 root 审查交付

**未接纳；原 F5 保持失败。** 解析修复已完成，剩余阻塞是旧清单中并不存在于正文的查询。

候选补丁 SHA-256 `2542b50eb2ae0d814b97670226ba704799fed44d347f60003d44982ef45a21fd`，仅修改批准 SDK `edddc463…` 隔离副本的 `src/rtf.c`；当前分支冻结 `src/include` 不变。

- 完整 root run [40234424624](https://github.com/NoGod3524/EXReader/actions/runs/40234424624)，受测源码 `bfc6447798d533c4d5d5fe7ca02e9a54fc928999`：Windows/Linux 各 169/169 原 SDK 回归、100 项安装后边界检查通过。两原件在 base 公开打开均为 `EXR_FORMAT=5`，候选均为 `EXR_OK=0`。
- Micro Republics 两平台原 F5 全过。Crowley 导入、原件读回、打开、全部翻页、重开成功；原查询 `Policy and Procedure TTR` miss，连带三项锚点失败，两个平台和严格汇总均失败。
- 诊断 [40235597650](https://github.com/NoGod3524/EXReader/actions/runs/40235597650)，源码 `ddb03807fc93f0aebcefbbbed124dd73831f4e3a`：同一候选 SDK/src tree、补丁和 `rtf.c` 哈希，公开正文 9215 B。原查询即使折叠大小写与空白也不存在；正文实际是 EH123 课程说明。
- root 完整 CI 使用 1/3 轮；轻量字节/工件检查与公开正文诊断不授验收。原两轮失败和 root 完整失败均保留。
- 最终认证 [40236000909](https://github.com/NoGod3524/EXReader/actions/runs/40236000909) 成功：在 Actions 下载三轮失败与公开正文诊断的原 ZIP，核对 source/run/attempt、digest、字节数和有效期；原 ZIP 与展开内容留在工件 `12614444667`。

根因与审查：高字体编号 31500 超出旧 4096 表；原件列表 definition/override 的 `listid=-2` 与 `ls2` 引用完整；另一原件有根组后的 NUL。列表兼容是对规范保留值的只读扩展，保留 signed int32 原值，独立 `ls` 范围和 duplicate 校验；不将外部 ID 与内部 0/-1/-2 哨兵或数组索引混用。新边界已实测 0、-1..-5、INT_MIN/INT_MAX、正负不碰撞、重复/缺失定义、字体 32767/32768 与旧坏流。

旧 wrapper 相对路径导致的 Cannot open file 已修为绝对路径；旧 base padding 失败与 candidate 成功分开保留，没有再把 base 错误当作候选错误。

详细身份、作业、工件 digest/bytes/expiry 见 [root-review-validation.json](docs/reader-next-c04/root-review-validation.json)。独立新版 F5 清单提案见 [F5-MANIFEST-CORRECTION-PROPOSAL.md](docs/reader-next-c04/F5-MANIFEST-CORRECTION-PROPOSAL.md)：建议使用正文连续句 `EH123 Rhetoric and Composition I`，必须另跑新版完整验收；旧清单未改。

本地仅源码/文档/Git 与只读 API/文本日志；所有语法、构建、测试、原件下载/处理和工件下载/解压/认证均在 Actions。
