# Apple 本批 14 项独立验收核对表 — 2026-10-29

计分基准：[固定清单审计 40920714977](https://github.com/NoGod3524/EXReader/actions/runs/40920714977)，`f406ab02de173e3431db548de1c30b24f7074788`，**94/108（87.0%）**。本批 14 项中已关闭 11 项，批注 3 项仍计零分。

下表是独立宿主功能范围。macOS 是 Actions 原生宿主；iPhone/iPad 是模拟器。SDK 3.41 证据与 SDK 3.42 接入、真实设备及最终六端同源码验收分别记录。

| 固定 ID | 结论 | 原始生产运行与源码 | 独立核查 | 覆盖 |
|---|---|---|---|---|
| `H.macos.font_library` | 已关闭 | [40627627614](https://github.com/NoGod3524/EXReader/actions/runs/40627627614) / `d23fc1de44d9` | [40904394809](https://github.com/NoGod3524/EXReader/actions/runs/40904394809) | 独立字体导入、重排、坏字体回滚、去重、lease 释放及重开；字体与程序二进制重验 |
| `H.iphone.font_library` | 已关闭 | [40627627614](https://github.com/NoGod3524/EXReader/actions/runs/40627627614) / `d23fc1de44d9` | [40904394809](https://github.com/NoGod3524/EXReader/actions/runs/40904394809) | 独立字体导入、重排、坏字体回滚、去重、lease 释放及重开；字体与程序二进制重验 |
| `H.ipad.font_library` | 已关闭 | [40627627614](https://github.com/NoGod3524/EXReader/actions/runs/40627627614) / `d23fc1de44d9` | [40904394809](https://github.com/NoGod3524/EXReader/actions/runs/40904394809) | 独立字体导入、重排、坏字体回滚、去重、lease 释放及重开；字体与程序二进制重验 |
| `H.macos.original_export` | 已关闭 | [40647623322](https://github.com/NoGod3524/EXReader/actions/runs/40647623322) / `e0926aee809a` | [40904394809](https://github.com/NoGod3524/EXReader/actions/runs/40904394809) | 真实系统目录选择、保存和 7724 字节 EPUB 逐字节回读；原工件无应用二进制，程序哈希来自原记录 |
| `H.iphone.original_export` | 已关闭 | [40905868673](https://github.com/NoGod3524/EXReader/actions/runs/40905868673) / `127cdb7c6277` | [40910291131](https://github.com/NoGod3524/EXReader/actions/runs/40910291131) | 真实系统目录选择、保存和 7724 字节 EPUB 逐字节回读；原工件无应用二进制，程序哈希来自原记录 |
| `H.ipad.original_export` | 已关闭 | [40905868673](https://github.com/NoGod3524/EXReader/actions/runs/40905868673) / `127cdb7c6277` | [40910291131](https://github.com/NoGod3524/EXReader/actions/runs/40910291131) | 真实系统目录选择、保存和 7724 字节 EPUB 逐字节回读；原工件无应用二进制，程序哈希来自原记录 |
| `H.macos.annotation_exchange` | 未关闭 | [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266) / `622b9558f79e` | 尚未通过 | 真实 JSONL/Markdown 保存、系统导入、预览/确认/取消、坏文件拒绝及并发/NULL 保留待新结果 |
| `H.iphone.annotation_exchange` | 未关闭 | [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266) / `622b9558f79e` | 尚未通过 | 真实 JSONL/Markdown 保存、系统导入、预览/确认/取消、坏文件拒绝及并发/NULL 保留待新结果 |
| `H.ipad.annotation_exchange` | 未关闭 | [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266) / `622b9558f79e` | 尚未通过 | 真实 JSONL/Markdown 保存、系统导入、预览/确认/取消、坏文件拒绝及并发/NULL 保留待新结果 |
| `H.macos.sync_account_status` | 已关闭 | [40914421686](https://github.com/NoGod3524/EXReader/actions/runs/40914421686) / `6c7d043d416c` | [40920468235](https://github.com/NoGod3524/EXReader/actions/runs/40920468235) | 实际 HTTPS 取消/重试、401 详情、授权更新、失败时原书/outbox 保留及 256 分片恢复 |
| `H.iphone.sync_account_status` | 已关闭 | [40914421686](https://github.com/NoGod3524/EXReader/actions/runs/40914421686) / `6c7d043d416c` | [40920468235](https://github.com/NoGod3524/EXReader/actions/runs/40920468235) | 实际 HTTPS 取消/重试、401 详情、授权更新、失败时原书/outbox 保留及 256 分片恢复 |
| `H.ipad.sync_account_status` | 已关闭 | [40914421686](https://github.com/NoGod3524/EXReader/actions/runs/40914421686) / `6c7d043d416c` | [40920468235](https://github.com/NoGod3524/EXReader/actions/runs/40920468235) | 实际 HTTPS 取消/重试、401 详情、授权更新、失败时原书/outbox 保留及 256 分片恢复 |
| `H.iphone.organization` | 已关闭 | [40911140164](https://github.com/NoGod3524/EXReader/actions/runs/40911140164) / `b259db57103c` | [40915032673](https://github.com/NoGod3524/EXReader/actions/runs/40915032673) | 原六项测试；实际标签/系列成员增删、恢复、进程重启；日志、步骤和截图复核 |
| `H.ipad.organization` | 已关闭 | [40911140164](https://github.com/NoGod3524/EXReader/actions/runs/40911140164) / `b259db57103c` | [40915032673](https://github.com/NoGod3524/EXReader/actions/runs/40915032673) | 原六项测试；实际标签/系列成员增删、恢复、进程重启；日志、步骤和截图复核 |

原字体运行 40627627614 和 macOS 原件运行 40647623322 的整体失败仍保留；上表只授予已通过的指定宿主专项结果。同步独立工件未保留应用二进制，程序哈希沿用原收集器记录；它不授予完整系统钥匙串/隐私审计。

批注失败保留：40911433448（三端原始结果）和 40920156829（macOS leading-click 试验）均未用于计分。后者其他四组原生回归通过，批注用例仍失败。原 iPhone 还保留系统主题失败；原 iPad 保留特性用例超时和基础翻页失败。当前修复 40923468266 保持所有原断言、测试数量和预算；结果及独立工件核查前不关闭目标。

SDK 3.42 接入源码仅暂存于 `codex/apple-sdk342-host-continuation-stage-20261029` / `4a68d80fbaa524fc28f899d209d795248627080b`，尚未验证，未新增计分。最终联合交付仍是 1/12；本表的宿主专项完成不替代 F01、F02–F05、F07–F12。
