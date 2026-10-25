# C07 root 裁判审查

原 C07 受测源码 `d3f7ec5bb57b372a0b61d13446e7ce8ea2d1ae4f`、run `40227524890` 的 76 项和两方向通过作为历史记录保留。root 在独立分支审查裁判，不修改原分支、宿主、批准 SDK 或 raw 七模块。

## 修正

原 strict 把 `transport_vs_reconstruction` 的 `numbers_equal`、`selectors_equal` 和 `route_equal` 仅写入报告，没有加入 `accepted` 判定。root 新增 `capture_contract.py`，逐记录硬性要求：

- 接收端记录的 revision、role、kind、mode、anchor_version 与该轮真实 Android sender manifest 完全一致。
- transport capture 与 sender manifest 的原 capture 完全一致；接收端实际 recapture 的 numbers 与 nullable counted selectors 完全相等。
- 非 EPUB 的五项 route 完全相等。EPUB mode 2 仅允许既有 owner 合同的 chapter 重建：transport route 为 `[book, parser, part_path, null, null]`，recapture 为 `[book, parser, part_path, null, part_path]`；part_path 必须是同一非空字符串，其余字段不能改变。
- 宿主 reconstruction 与实际 SDK recapture 完全相等。

EPUB 规则来自冻结 owner [HostReadingRecords.swift](https://github.com/NoGod3524/EXReader/blob/e67d87cbeabb2457e0852f681ef0b27b2c0da4d8/examples/apple/HostReadingRecords.swift#L290)：SDK chapter 由显式 part_path 重建，wire 的 chapter 保留给 reflow-global 模式。规则同时通过原真实工件验证；没有设置任意 EPUB route 例外。

## 真实工件负例

轻量 [40236652862](https://github.com/NoGod3524/EXReader/actions/runs/40236652862) 在 Actions 认证原 C07 Android-sender/Mac-receive 两个原 ZIP 的 source/run/attempt、字节、digest 与 expiry。四个实际接收阶段共 44 条记录全部符合合同；从这些真实记录逐项深拷贝构造的 640 个负例全部被拒绝。

负例包括数字偏移、mode、selector 字节、NULL/allocated-empty 区别、五个 route 域、短 route、仅改变 reconstruction、记录 role/kind，以及 transport/recapture/reconstruction 同时改变的伪相等。EPUB 额外覆盖未重建 chapter 和非 NULL transport chapter。原 ZIP 不被修改，不将这些负例当作真实原生 capture。

完整 root 链仍复用原 Android/macOS 原生 owner 与 HTTPS 256 分片入口，并在最终 strict 中对本轮认证工件再跑同一批正/负例。受测源码、运行和最终结果见同目录 `root-review-validation.json`。

root 完整第 1 轮 [40236707415](https://github.com/NoGod3524/EXReader/actions/runs/40236707415)，源码 `18f1d1d242185b635ab7d2f863bc47759c164f38`：五执行作业全 success，81 检查通过，两个方向 true，pending/failed 为空。本轮实际 44 正例、640 负例通过。随后轻量 [40238010988](https://github.com/NoGod3524/EXReader/actions/runs/40238010988) 再下载并认证该 strict 原 ZIP，逐项核实以上计数、640 个拒绝的唯一键、所有 numbers/selectors 相等与 route 合同通过。

## 范围与接入

只覆盖 Android API34 default x86_64 模拟器与 macOS 的原生 owner/协议；两个方向都必须拥有同 run/attempt 的完整原件、wire、父图、实际程序与 SDK 证据。跨 job 的真实包通过认证 GitHub 工件接力，各端实际 Session 经认证 HTTPS fixture 收发。

本包 macOS 执行 send/operations/session-push 三进程，以及 direct receive/reopen、Session receive/reopen、NULL receive/reopen 六进程。原驱动中存在的 kill/replay 函数并不等于本包执行了这些阶段；本包没有重新授予原 130 项/18 阶段全集，也不授 GUI、其他平台、真机、性能、真实公网云盘或完整产品。

共同主线接入另行建立显式 workflow/guard wrapper，登记本包新增文件与真实 owner/SDK/raw 树，使用实际共同 source SHA 重跑。保留原两提交和历史 run；不把旧 guard 的 branch/target 替换成当前 HEAD 后沿用旧同源结论。本轮没有修改 common 工作树。
