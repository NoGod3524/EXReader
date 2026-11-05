# S02：Linux 可迁移候选包契约

本包从固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85` 独立实现，只写
`tests/reader_final_s02/`、`.github/workflows/reader-final-s02.yml`、`docs/reader-final-s02/`
与 `HANDOFF-RESULT.md`。宿主、SDK、apps/、原 tests/、原 workflow、预算与保护树一字未改。

## 复用与三种 source

| 角色 | 固定 source | 在 CI 中如何使用 |
| --- | --- | --- |
| 受测 producer（GTK 简洁 UI） | `57203a52aee439be5194ee0a4b13563a975e8daf`，封存 `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e`，run `40206458217` | **不二次 checkout**：用 `gh api` 读回该 run 的认证工件 ZIP，按 API digest 校验字节后只取 `compact-package/**` |
| J24 可迁移原语 | `2f5677f13efc34b200af697f1b6f7bff2b656e3b`（`tools/reader_distribution_unix/contract.py`，tree `2f28a436…`） | `git show` 精确取出该提交的 `contract.py`，`git hash-object` 必须等于 `289b435f…`；seal/extract/walk/tree_problems 原样复用 |
| AT-SPI 客户端 | `67e2f8c4941205c5581e82fd5a1469d18f696019`（`tests/reader_a11y_gtk/atspi_client.py`） | `git show` 取出，`git hash-object` 必须等于 `50d51ac9…` |
| 本包 verifier | 本分支 HEAD（`GITHUB_SHA`） | 全部 S02 工具与 workflow |

三种 source 在 `producer.json`、`package.json`、`summary.json`、`result.json` 中分开记录，
不合并其它功能分支，不把不同 run/attempt 的片段拼成一次通过。

## 工具与输入输出

- `guard.py`：HEAD==`GITHUB_SHA`、起点为祖先、改动全在白名单、producer/J24/AT-SPI 固定提交存在、
  抽取出的两个文件 blob 与固定值相等。
- `selfcheck.py`：在合成夹具上跑 12 条协议判据（readelf/ldd 解析、desktop Exec 绝对路径拒绝、
  observation 解析、build token 扫描、单根/越界/符号链接 tar 拒绝、树摘要篡改发现、路径分类、
  loader 记录解析、检查累加器）。
- `collect.py`：读 `gh api` 的 run/attempt/artifacts，下载该 ZIP 并**重算 SHA-256 与字节数**，
  校验 `digest`、未过期、`expires_at`；解出 producer 自带 `EXReader-Linux.tar.gz`（只这一份作为
  payload 权威字节，tar 保留 0755），与 ZIP 里散装 payload 成员逐文件比对；用 producer 自己的
  `build.json` 逐文件核对，并交叉核对 producer 自己的 `compact-ui/report.json`
  （accepted、source_sha、run_id、program_sha256、每条 check passed）。
- `package.py`：复用 J24 `contract.seal/extract/tree_problems`，把 payload 封成
  `EXReader-Linux-3.41.0-linux-x86_64-relocatable.tar.gz`（单根、无链接、逐文件 sha256 清单、
  固定 gzip mtime），再解包到 **工作区之外**、带空格与括号的长路径
  `/tmp/s02-portable/EXReader Linux 3.41.0 (portable)`，并证明搬迁后每个文件字节不变。
- `audit.py`：静态审计——readelf 动态段（NEEDED/无绝对 RPATH/RUNPATH）、ldd 解析（无 not found、
  全部落在系统目录）、payload 内无构建路径 token、字体与许可资源、producer 未提供 desktop 入口、
  候选按安装位置生成 desktop 入口并用 `desktop-file-validate` 校验、每个 NEEDED 的 dpkg 归属与版本、
  XDG 布局。
- `smoke.py`：三次真实启动，全部使用全新 HOME、全新 XDG 目录、空工作目录、无 `LD_LIBRARY_PATH`：
  1. 默认无参启动（`strace` 记录）：证明字体从**包内相对可执行文件**打开、书库与设置在
     `XDG_DATA_HOME` 下、HOME 与工作目录零残留、trace 中无工作区路径；AT-SPI 断言窗口、
     `Import book`/`Continue reading`/`More reader actions` 与空书库禁用态；
  2. 通过候选 desktop 入口 `gtk-launch exreader` 启动（`XDG_DATA_HOME/applications` 发现、
     pid 的 `/proc/<pid>/exe` 指向搬迁后程序）；
  3. 显式字体/配置/观察文件启动：用真实 GTK 文件选择器导入 **CI 生成的原始 TXT**，
     读 observation（error/book/books/page/offsets/font）、开启文本面板后用 AT-SPI 文本断言
     本次 run 唯一 marker，并证明原始文件 sha256 未变、payload 三次启动后仍逐字节不变；
     `LD_DEBUG=libs` 记录里不得出现 HOME/payload/工作区中的库。
- `summary.py`：合并四份证据，要求同一 `GITHUB_SHA`、同一 program hash、同一 run/attempt/artifact digest。
- `aggregate.py`（report job，全新 checkout）：用 `gh api` 读回本 run 的 jobs/artifacts，重算本包证据
  ZIP 的 SHA-256 与字节数同 API digest 比对，从证据 ZIP 内取 `summary.json`；再读回 producer run 与
  工件，**重新下载 40206458217 的 ZIP 并重算摘要**，与 summary 记录的 digest/字节数比对。

## 判据与硬边界

- 只有全部具名 check 为 pass 且四份文档无 problems 时 `summary.accepted` 才为真；`aggregate`
  还要求本 run 的 preflight/relocate 成功、证据 ZIP digest 相符、producer ZIP 重新下载后摘要一致。
- 不降低任何断言、不删失败、不把失败改成“预期拒绝”。任何工具异常都使 job 失败并保留原日志。
- 迁移候选只写 `build/` 与 `/tmp`，从不写源码树；evidence 只在 Actions 内生成、下载、解包与解析。
- 每包同时最多一个 live run（`concurrency: reader-final-s02`，不取消进行中运行），无矩阵。

## 明确未覆盖

- 仅 Ubuntu 22.04 GitHub runner 的 x86_64 环境；其它发行版、glibc 版本、musl、arm64 未测。
- 仅 Xvfb + openbox + AT-SPI；Wayland、真机、读屏软件、hidpi/触控、性能预算均未测。
- 不做系统级安装、包管理器打包、图标主题集成；producer payload 本身不含 `.desktop` 与图标，
  候选入口是本包在安装位置生成的，producer 侧的缺失如实记录而不是冒充已交付。
- 不改宿主源码；正式宿主接线与共同源码整合由 root 负责。
