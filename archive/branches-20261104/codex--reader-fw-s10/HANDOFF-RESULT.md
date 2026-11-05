# S10 电脑传书入口与能力证据 — 交回状态

状态：**accepted（同 source / run / attempt 通过），带明确 pending**。最终产品授予由 root 决定；
本文件与 `docs/reader-final-s10/` 的提交是 docs-only 封存（不触发 workflow）。

## 1. 身份

| 项 | 值 |
| --- | --- |
| 固定实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| 受测完整源码 SHA | `9f49b736ecee0baeee8d9524e7e75a40592ae5d0` |
| 远端分支 | `origin/codex/reader-fw-s10` |
| docs-only 封存 SHA | 本文件所在提交（`git log -1 --format=%H -- HANDOFF-RESULT.md`） |
| run / attempt | [40218271618](https://github.com/NoGod3524/EXReader/actions/runs/40218271618) / 1，5/5 success |
| SDK | 3.41.0 / ABI 1（`src include cmake CMakeLists.txt bindings tests/fixtures` 相对起点逐字节不变） |

## 2. 作业与工件（同一 attempt；summary 在 Actions 内重新认证 job 身份、ZIP 字节/SHA/有效期）

| 作业 | job id | 结论 | 工件 id | 字节 | ZIP SHA-256 | 有效期 |
| --- | --- | --- | ---: | ---: | --- | --- |
| guards | 121244044679 | success | 12608745043 | 4064 | `61da68730017ded8195d8059dfdf1dd06caf2ec0b605e1c092a6d53cb47369cb` | 2027-01-23T17:48:56Z |
| android | 121244044649 | success | 12608329499 | 7686 | `b89adf8a8d179571f7818fdbf5b8d70867717e988cea992eaf60e23824818c0a` | 2027-01-23T17:48:56Z |
| apple | 121244044513 | success | 12609011496 | 53650661 | `d121579d68ebad9935b3c5509bb5c3fa900bb11dd743f232c6ab8ad56faf9e29` | 2027-01-23T17:48:56Z |
| desktop | 121244044692 | success | 12608640524 | 20847 | `0338489b09eab5940a0fe3090083588cb4a36ac2af164d4e3efea3f7874926ed` | 2027-01-23T17:48:56Z |
| summary | 121247475395 | success | 12608596187 | 7624 | `17b45691ed01e5d80c5b61ad6ce8147577e6180415a35d40ad9c09deb193c9fb` | 2027-01-23T17:48:56Z |

程序/夹具 hash 均在上述工件内：guards 的 `fixtures-manifest.json`（本次交付字节的 SHA-256）、
android 的 `report.json`+`owner-events.jsonl`+`probe.exrlib`（SDK 书库原件）、apple 的
`iphone|ipad/driver-report.json` 与驱动 bundle、desktop 的 `entry-report.json` 与导出原件。
summary 的 ZIP 摘要即覆盖这些文件的真实字节。

## 3. 实际执行的检查

- guards：所有权 7 项；入口契约 **20** 项真实声明检查 + **13** 个具名变异反例（每个变异必须恰好让声明的
  检查失败）。覆盖 Android manifest/SAF owner、Apple Files 共享钥匙与安全作用域 owner、macOS、Windows、
  GTK 桌面入口，以及全库「禁 WebView / 禁监听套接字」。
- android：API 34 x86_64 模拟器 **9** 项——模拟器内文件 SHA 与 fixture 一致、owner 收到的 `ready.id`
  等于 `<fixture sha256>.epub`、无失败事件、`commit(created=1,bookId>0)`、`readback.equal=true`、
  staging lease 释放、独立 SQLite 读回 `books.source` 与 fixture 逐字节一致。
- apple：iPhone 与 iPad 模拟器各 **14** 项——bundle 声明 Files 共享、交付文件在 Documents（Files 共享目录）、
  owner `importFile(url:)` 完成且无错误、owner 自身 `sourceFingerprint` 与交付字节一致。
- desktop：**9** 项——真实 `text/uri-list` 载荷的 1 个真实文件项/1 个目录项/远程 URL/远程主机/虚拟项分类正确、
  `exr_sideload_import_file` 建书、`exr_sideload_export_original` 导出字节数与 SHA-256 与投放文件一致。
- summary：21 项严格汇总（拒绝混源、缺平台、未认证或未过期工件），`problems: []`。

## 4. 首轮真实失败（保留，不拼接）

[run 40214657202](https://github.com/NoGod3524/EXReader/actions/runs/40214657202) / source
`1dfdd4a019d815a719bc12e1cb64a721f6289bbc`：guards（121233078344）与 desktop（121233078143）失败，
android（121233078504）与 apple（121233078315）通过，summary（121237159297）skip。工件保留：guards
12607400235（1022B，`ab3892325a29cf222e8586f16101a4edeead059aca75f5ab81ffc1d33c39f06f`）、android
12606623967（7684B，`784e78c909a867d59f37b50f43b38bebfcc4249c4050c2d7f016dbb5f288c760`）、apple
12608185207（53650704B，`bf2fccabf9a2006a3c60fb6d230b260156141a3794751489168e88944805e8a8`）、
desktop 12606484332（19276B，`590c6a11295bf087a14653639470fe46974e3766cb7dcaf20b539d51ea4bfe29`），
有效期均 2027-01-23T17:04:01Z。

- guards 失败原文：`mutation mutate.gtk.drop-target failed  instead of gtk.entry.drop-target`。
  根因：自测只替换首个出现处，而 `examples/linux/drop_import_ui.inc` 两次出现
  `x-special/gnome-copied-files`。修复：变异对所有出现处生效（断言强度未变）。
- desktop 失败原文：`json.decoder.JSONDecodeError: Expecting value: line 15 column 3 (char 681)`。
  根因：本包 `entry_check.c` 序列化 drop items 时写了尾逗号。修复：前置逗号分项写出，并让
  `run_desktop.py` 在解析失败时保留原始字节后判失败。

两处均为本包工具缺陷，未修改任何 owner 文件、未降低任何原断言。

## 5. 未验证 / pending（不预填通过）

1. 真机与线缆：Android 手机 + USB/MTP 复制、iPhone/iPad + Finder/iTunes 或 iCloud Files 传输均未执行
   （Actions 无设备、无线缆）。CI 的文件送达是模拟传输，**不构成** USB 真机通过。
2. 系统选择器 UI：Android SAF 选择器与 iOS Files 选择器的点击未驱动；两者背后的授权/安全作用域代码路径
   已实际执行。
3. 桌面可执行：Windows（`GetOpenFileNameW`、shell 路径参数）与 macOS（`.fileImporter`）仅静态契约通过，
   未在本轮构建/运行；实际执行的是 Linux `text/uri-list` 桌面入口。
4. 性能、商店分发、签名/公证未涉及。

## 6. 复现

`.github/workflows/reader-final-s10.yml` 只由 `codex/reader-fw-s10` 的
`tests/reader_final_s10/**` 或该 workflow 自身变更触发（`concurrency` 保证同分支同一时刻一个 run）。
matrix 未使用；四个互不依赖的 producer 作业 + 一个严格 summary，summary 只读取本 attempt 已认证的
工件 ZIP。夹具全部在 CI 生成（`make_fixtures.py`），不入库。
