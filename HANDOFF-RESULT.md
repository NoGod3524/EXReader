# C03 HANDOFF-RESULT

**状态：accepted=false。三轮CI已用尽，三轮均在构建阶段失败，C03 的任何具名检查都尚未执行。未验证项即全部检查。**

- 起点（固定）：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`；分支 `origin/codex/reader-fw-c03`
- 受测源码（run3）：`f5d87fdd7a1d025509fb7847ab90d237617fc7a1`；未经CI的修复提交（`[skip ci]`，见下）在该分支HEAD
- 无PR、无默认分支推送、无Release。

## 三轮运行（均为本包 workflow，repo NoGod3524/EXReader）

| 轮 | run/attempt | source | 失败位置与原因 | artifact（ID/字节/SHA-256/到期） |
| --- | --- | --- | --- | --- |
| 1 | 40213760389/1 | f5caba33d299bfcc5f015bfcbc9ce1e5976a0f50 | “构建冻结阅读库+cloud-import链”：现有 `tests/reader_webdav_import/consumer/CMakeLists.txt:16` 钉 `EXReader 3.40.0 EXACT`，而 0889 的 `reading-library` 预设安装的是 **3.41.0**（`CMakeLists.txt` project VERSION 3.41.0） | 12606343598 / 16753 / c11db10e65716112ecfaad493057382535b87d15386fc2da275a4be198ad4c32 / 2027-01-23 |
| 2 | 40213984264/1 | 330b83fd27316360cc2647ed5814b9cc9e061d53 | 同类：被只读 owner 模块 `apps/reader/cloud-import/CMakeLists.txt:16` 也钉 `EXReader 3.40.0 EXACT`，与 3.41.0 SDK 不兼容（我方探针 CMake 已去钉，但适配器本身不能） | 12606727556 / 16765 / 04fd2b63f48ef142272465bf4b33d48c1a2530bb89265a083ca0b450a7557482 / 2027-01-23 |
| 3 | 40214192654/1 | f5d87fdd7a1d025509fb7847ab90d237617fc7a1 | 已改为二次checkout冻结 3.40 SDK（`9854061be331fe603a1822d9b2b36ee357154927`，路径 `sdk340`）后，适配器已构建安装；**我方 `tests/reader_final_c03/probe/CMakeLists.txt` 只声明 `LANGUAGES C`，链接 `libexr_webdav.a`(C++) 缺 libstdc++ → `DSO missing from command line`**（自身工具缺陷） | 12607101836 / 18055 / d530c3b67bdf3a8bbdc2d664b0ec2dc0142d48e0a539518b7b6525dd0f9f6b92 / 2027-01-23 |

每轮另有 “authentication” 作业与 artifact（因生产作业失败，认证按预期失败，不构成通过）。

## 发现（交 root）

1. **owner 兼容性缺口（未改）**：0889 的 SDK 为 3.41.0，但 `apps/reader/cloud-import/CMakeLists.txt` 与 `tests/reader_webdav_import/consumer/CMakeLists.txt` 都 `find_package(EXReader 3.40.0 EXACT)`。cloud-import 适配器因此**无法**对 0889 自带 SDK 构建；本包改为二次checkout 冻结 3.40 SDK（独立 source=9854061）才通过适配器构建。若统一源码用 3.41 SDK，需 owner 放宽/更新该钉子（精确复现：run 40213984264 的 “Build the frozen reading library…” 日志，`CMakeLists.txt:16`）。
2. run3 的链接失败是本包缺陷，已一行修复：`project(reader_final_c03_probe LANGUAGES C CXX)`（提交带 `[skip ci]`，**尚未经过Actions验证**）。

## 已写成但从未执行的内容

`tests/reader_final_c03/check_c03.py`（HTTPS临时证书+随机口令；cloud-probe 与 resilience-consumer 两个原消费者；约30个具名检查：12种路径/编码穿越、显示名不成路径、符号链接暂存目录、重定向出根/环/预算/跨源/降级、TLS不受信/主机名不符、缺失/错误凭据、RST/停滞/取消、换发原件、恶意PROPFIND href、同步线格式损坏/未知version/未知字段/超限/哈希或id与文件名不符、监听越界、GET重定向出根、无凭据同步、停滞超时、账户命名空间隔离），`check_guards.py`、`check_artifacts.py`、workflow、`docs/reader-final-c03/CONTRACT.md`、`validation.json`(accepted=false)。其断言**全部是未验证的预期**：尤其“同步坏线格式是否 status≠0”我只断言了不拉取/不写（pulled==0、本地历史/outbox/缓存不变、无远端写）；资源穿透/符号链接若与预期不符将成为真实 owner 缺陷而非被放宽。

## 下一步（root 决定，我不再刷CI）

分支 HEAD 含修复，直接 `workflow_dispatch` 或推送 tests/ 路径变更即可作为第4轮。仍未覆盖（pending）：平台凭据库锁定/拒绝、下载与导入间暂存文件被换为符号链接（需新原生探针）、Windows/macOS/Android/Apple 执行、第三方真实 WebDAV。
