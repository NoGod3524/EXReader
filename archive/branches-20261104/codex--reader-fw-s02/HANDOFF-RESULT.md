# S02 Linux 可迁移候选包核验 — 交回状态

**accepted = false**（桌面入口启动这一段未在 CI 中跑完；其余搬迁、审计、默认启动与原件回读全部通过）。

- 分支：`codex/reader-fw-s02`（远端已推，无 PR、无 tag、无 Release）
- 固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`
- 独占路径：`tests/reader_final_s02/`、`.github/workflows/reader-final-s02.yml`、
  `docs/reader-final-s02/`、本文件；现有 apps/SDK/tests/workflow 一字未改（`guard.py` 证明 14 个改动全在白名单）

## 受测 source

| 角色 | SHA | run / attempt |
| --- | --- | --- |
| 主证据（verifier） | `60a41b77f474540de80e18494475f4df2ca648ff` | **40215120505 / 1** |
| 第二次验收 | `1a99c6d2b5ea52bfccf33c3022f59d3de8f85086` | **40215528466 / 1** |
| 已提交的修复（`[skip ci]`，**未执行**） | `d6232efde80b906e2764cebe77adb39a80aea4e4` | 无 |
| GTK 简洁 producer（只读消费） | `57203a52aee439be5194ee0a4b13563a975e8daf`，封存 `9fc407a5…` | producer run **40206458217 / 1** |
| J24 原语 | `2f5677f13efc34b200af697f1b6f7bff2b656e3b` | 只读 |
| AT-SPI 客户端 | `67e2f8c4941205c5581e82fd5a1469d18f696019` | 只读 |

## 原始工件（Actions API 元数据 + CI 内重算，未在本地下载）

- producer：`reader-gtk-341-final-40206458217-1`，id **12604604561**，**112,659,381 B**，
  `sha256:8d6c52593dd2017a6e13ffc2cf75fd3fd4546cdf3a5179b0da5afd55ac1fb685`，有效期 **2027-01-23T15:20:23Z**；
  payload 27 文件，程序 hash `d715588d1c1fafa3a1d9677e78ff9410db41606789ba500b5e47f3ad8c2cd5a3`（`3.41.0 1`）
- 本包证据（run 40215120505）：`12606944249`，168,626 B，`sha256:3c9bad29…`；
  report `12607366313`，12,802 B，`sha256:f162b0d7…`；均 2027-01-23T17:09:47Z 到期
- 本包证据（run 40215528466）：`12608086229`，171,297 B，`sha256:9c925f36…`；
  report `12608146128`，12,743 B，`sha256:2ab5ebfe…`
- 候选归档：`EXReader-Linux-3.41.0-linux-x86_64-relocatable.tar.gz`，**18,286,243 B**，
  `sha256:aa6fd3cf…`，27 文件；搬迁到 `/tmp/s02-portable/EXReader Linux 3.41.0 (portable)`（工作区外、含空格括号）

## 实际通过项（run 40215120505，59 项中 55 pass / 2 observed / 2 fail）

- **producer 认证 11/11**：run 完成且 source==pin；ZIP 字节/digest/有效期；tar 与散装成员一致；
  `build.json` 逐文件一致；`--version`；producer 自己的 44/44 compact 报告与 program hash 对齐
- **候选制作 7/7**：复用 J24 `seal/extract/walk/tree_problems`；单根无链接归档；工作区外搬迁；
  解包逐文件身份；程序 hash 不变
- **静态审计 10/12（2 observed）**：无绝对 RPATH/RUNPATH、NEEDED 16 项无 SDK/路径项、
  ldd 无 not found 且全落系统目录、89 个 dpkg 归属包、`Reader.otf` 为 OTTO 且 17 份许可、
  `desktop-file-validate` 通过且 `Exec` 指向搬迁后可执行文件、XDG 布局
- **默认无参启动 11/11**：窗口 1040x820；`Import book`/`Continue reading`/`More reader actions`；
  空书库 `Continue reading` 不可用；`strace` 证明字体从包内 `Reader.otf` 打开；
  `library.sqlite`/`reader.ini` 落在 `XDG_DATA_HOME`；`HOME/.local/share/exreader` 不存在；
  工作目录空；构建树 open 0 次
- **原件回读 10/10**：导入 CI 生成的 TXT 后 `book=1 books=1 error=0 page=0 start=0 end=389 font=24`；
  AT-SPI 文本含本次 run 唯一 marker `S02 RELOCATED READBACK 40215120505 1`；原文件 hash 未变；
  三次启动后 payload 逐字节不变；`LD_DEBUG=libs` 无 HOME/payload/工作区库
- 记录项（不计通过）：`bin/exreader-linux` 内一处编译期字符串 `EXReader/EXReader/build`（运行期 0 次访问）；
  producer payload 不含 `.desktop` 与图标（候选在安装位置生成入口）

## 未完成与原因

1. **桌面入口启动**（`gtk-launch exreader`）：run 40215120505 因镜像没有 `gtk-launch` 失败；
   run 40215528466 补装了 `libgtk-3-bin`，但 `subprocess.run(PIPE)` 等的是被启动应用而非启动器
   （`TimeoutExpired 180s`），泄漏实例又污染了回读阶段。
   修复已提交（`d6232efd`：启动器输出写文件、每阶段先清理残留实例、desktop 阶段自带 finally），
   **但没有再跑 CI**：本包已用掉三轮 preflight 失败与两轮验收（run 40214626449、40214783375、
   40215019518、40215120505、40215528466），按“最多三轮后归还 root、不刷运行”停在此处。
2. 因此 `summary.accepted=false`，report 作业的 `s02_summary_accepted`/`s02_jobs_succeeded` 也随之为 false；
   没有把不同 source/run 的绿色片段拼成一次通过。

## root 需要做的

- 用 `workflow_dispatch` 在 `codex/reader-fw-s02`（HEAD `d6232efd` 或其后）跑一次
  `reader-final-s02.yml`，即可补齐桌面入口启动与同轮 summary/report；
- 记录项里的编译期字符串由宿主 owner 决定是否清掉（不改本包断言）。

## 未验证范围

只测 Ubuntu 22.04 runner x86_64 + Xvfb/openbox/AT-SPI；其它发行版、Wayland、真机、读屏、
性能预算、系统级安装/包管理器/图标主题、Windows/macOS/Android/Apple 均未测。
详细证据见 [docs/reader-final-s02/EVIDENCE.md](docs/reader-final-s02/EVIDENCE.md)，
字段见 [docs/reader-final-s02/validation.json](docs/reader-final-s02/validation.json)。
