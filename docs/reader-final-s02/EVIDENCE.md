# S02 真实证据（Actions 内生成，未在本地下载或解析任何工件）

## Source 分离

| 角色 | SHA | 本包如何使用 |
| --- | --- | --- |
| 本包实现（主证据） | `60a41b77f474540de80e18494475f4df2ca648ff` | run **40215120505** attempt 1 的 verifier source |
| 本包实现（第二次验收尝试） | `1a99c6d2b5ea52bfccf33c3022f59d3de8f85086` | run **40215528466** attempt 1 |
| 本包修复（未执行） | `d6232efde80b906e2764cebe77adb39a80aea4e4` | `[skip ci]`，改的是 gtk-launch 捕获与阶段清理，**没有跑过 CI** |
| GTK 简洁 producer（受测） | `57203a52aee439be5194ee0a4b13563a975e8daf` | 只读消费 run 40206458217 的认证工件，未 checkout 该分支 |
| GTK 简洁封存 | `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e` | 记录为 producer 封存 |
| J24 可迁移原语 | `2f5677f13efc34b200af697f1b6f7bff2b656e3b`（contract.py blob `289b435f…`） | `git show` 取出并由 `git hash-object` 校验后 import |
| AT-SPI 客户端 | `67e2f8c4941205c5581e82fd5a1469d18f696019`（blob `50d51ac9…`） | 同上，由 `git hash-object` 校验 |

## 认证的 producer 原工件（run 40206458217 attempt 1）

- run：`40206458217`，workflow `reader-gtk-compact.yml`，head_sha `57203a52…`，conclusion `success`
- 工件：`reader-gtk-341-final-40206458217-1`，id **12604604561**，**112,659,381 B**，
  digest `sha256:8d6c52593dd2017a6e13ffc2cf75fd3fd4546cdf3a5179b0da5afd55ac1fb685`，
  有效期 **2027-01-23T15:20:23Z**（`expired=false`）
- CI 内重新下载并重算：字节与 SHA-256 与 API digest 完全相等（check `producer_zip_digest`）
- payload：`EXReader-Linux.tar.gz` 内 **27** 个文件；`build.json` 逐文件核对一致；
  ZIP 内散装 payload 成员与 tar 内字节一致；producer 自己的 `compact-ui/report.json`
  accepted=true、44/44 checks passed、source_sha=57203a52、program_sha256 与 payload 一致
- 真实程序 hash：`d715588d1c1fafa3a1d9677e78ff9410db41606789ba500b5e47f3ad8c2cd5a3`
  （`bin/exreader-linux`，`--version` = `3.41.0 1`）
- 另记录两个 summary 工件：`12605108334`（15,706 B，`sha256:9e5b43cb…`）、
  `12604909051`（19,348 B，`sha256:4533df7c…`），同一有效期

## 重定位候选（run 40215120505）

- J24 `contract.seal/extract/walk/tree_problems` 原样复用（`j24_primitives_reused` pass）
- 候选归档 `EXReader-Linux-3.41.0-linux-x86_64-relocatable.tar.gz`：
  **18,286,243 B**，`sha256:aa6fd3cff8dd9269298b4ceb6e68b34235b4395409d813ee3b6f98cf5215a3e0`，
  27 个文件，单根、无链接、逐文件摘要清单
- 搬迁目标：`/tmp/s02-portable/EXReader Linux 3.41.0 (portable)`（工作区之外、含空格与括号）
- 搬迁后逐文件字节身份 pass；程序 hash 仍是 `d715588d…`；`--version` = `3.41.0 1`

## 静态审计（run 40215120505）

- 动态段：无绝对 RPATH/RUNPATH，NEEDED **16** 项，无 `libexr*`、无路径形式的 NEEDED
- ldd：无 `not found`，全部解析到系统目录；每个 NEEDED 都有 dpkg 归属，共 **89** 个包，
  版本记录在 `audit.json`（Ubuntu 22.04 runner）
- 字体/许可：`Reader.otf` magic `OTTO`，`licenses/` 17 个条目，payload 内无 `.so`
- desktop：producer payload **不含** `.desktop` 与图标（observed finding）；
  候选在安装位置生成 `$XDG_DATA_HOME/applications/exreader.desktop`，
  `desktop-file-validate` 无 error，`Exec="/tmp/s02-portable/EXReader Linux 3.41.0 (portable)/bin/exreader-linux"`
- 记录项：`bin/exreader-linux` 内含一处编译期字符串 `EXReader/EXReader/build`（动态段干净、
  运行期 0 次构建树 open），作为 finding 交 root，不作为加载依赖

## 运行期（run 40215120505，Xvfb 1440x1200 + openbox + AT-SPI）

- 默认无参启动：窗口 `EXReader Linux` 1040x820；`Import book`/`Continue reading`/`More reader actions`
  可见且空书库时 `Continue reading` 无 sensitive；`strace` 里字体从
  `/tmp/s02-portable/EXReader Linux 3.41.0 (portable)/Reader.otf` 成功打开；
  `$XDG_DATA_HOME/exreader/library.sqlite` 与关闭后 `reader.ini` 都在 XDG 目录下，
  `HOME/.local/share/exreader` 不存在，工作目录保持为空，构建树 open 0 次
- 原件回读（显式字体/配置/观察文件）：导入 CI 生成的 `S02 readback.txt` 后
  `book=1 books=1 error=0 page=0 start=0 end=389 font=24.000`；开启文本面板后 AT-SPI 文本
  含本次 run 唯一 marker `S02 RELOCATED READBACK 40215120505 1`（2 个文本节点）；
  原始文件 sha256 未变；三次启动后 payload 仍逐字节不变；`LD_DEBUG=libs` 中无 HOME/payload/工作区库

## 本轮失败（原样保留）

| run / attempt | source | 失败位置 | 原始原因 |
| --- | --- | --- | --- |
| 40214626449 / 1 | `3cdd505b` | preflight selfcheck | `selfcheck_scan_tokens` 期望单 token，合成二进制含两个 |
| 40214783375 / 1 | `9346d360` | preflight selfcheck | 抽取器在 `with tarfile` 之外 `extractfile` → `TarFile is closed` |
| 40215019518 / 1 | `a11d77b0` | preflight selfcheck | `shutil.make_archive` 的 `.` 根被误当成多个根 |
| 40215120505 / 1 | `60a41b77` | smoke / phase_desktop | 镜像缺 `gtk-launch`（`FileNotFoundError`），其余 55/57 通过 |
| 40215528466 / 1 | `1a99c6d2` | smoke / phase_desktop | `subprocess.run(PIPE)` 等的是被启动应用 → `TimeoutExpired` 180s；泄漏实例又污染了回读阶段 |

后两条是本包 **桌面入口启动工具** 的缺陷，不是被搬迁程序的缺陷：静态 desktop 校验、
默认启动、XDG 位置、字体、原件回读在 40215120505 里全部通过。
