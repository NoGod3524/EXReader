# S11 原件导入持久化故障回归 — 交回状态

**accepted = false**：本包自有实现与三轮 CI 证据齐全，但最后一行失败指向一处 **owner 契约
不一致**（cloud 私有 staging 失败被报成 REMOTE），需 root/owner 决定后重跑一次收尾。
未降断言、未改 owner 代码、未刷 CI（三轮即止）。

## 1. 源码与分支

| 项 | 值 |
| --- | --- |
| 实现起点 | 0889f7d1e9a537c6c1b05456547e016b26e1cd85 |
| 批准 SDK（树内 3.41.0） | edddc463c06ed5731195cdb8f06b2df6dff7699e（与起点树的 src/include/cmake/CMakeLists.txt 完全一致） |
| 受测 SHA | 56ffaf519e9b604a585a604025805935541b8077 |
| 远端分支 | codex/reader-fw-s11 |
| docs-only 封存 | 提交本文件的 docs-only 提交（SHA 见 git log / 最终消息；带 [skip ci]，因此没有独立运行） |
| 新增路径 | tests/reader_final_s11/（consumer 探针 + fixture 生成器 + 故障注入 + judge + 工件核验）、.github/workflows/reader-final-s11.yml、docs/reader-final-s11/、本文件 |
| 未改动 | SDK（src/include/cmake/CMakeLists.txt/bindings/tests/fixtures）、apps/、extras/、原 tests/、原 workflow、预算与账号配置；workflow 的 guard 每轮都验证这一点 |

## 2. 做了什么（最小补充，不重复既有交付）

被测面是四个**既有的公开接口**：EXReaderSideload、EXReaderBatchImport、EXReaderCloudImport、
EXReaderLocalDownloads。新写的只有一个安装了包的 C 消费者探针（tests/reader_final_s11/consumer/s11_probe.c）
和一个 judge（check_s11.py），把**私有 staging + 提交边界**的故障矩阵跑成可复现的行表
（docs/reader-final-s11/CONTRACT.md）：

- 磁盘受限：Linux 真 tmpfs（256 KiB / 512 KiB，先试写超过容量证明 ENOSPC），三处（batch 拷贝、
  cloud 下载、SDK 库卷）。
- 只读：POSIX 0555 / Windows icacls deny WD,AD，注入后先试写证明真写不进去；batch/cloud/ld 三处。
- 原件变化：枚举后换书、两阶段之间改 staged 字节（同长/变短）、提交后改调用方原件。
- 中断：staging 前/复制中/两阶段之间/提交前/写完 BEGUN 后取消。
- 重开：每次都以新进程打开 SDK 库、用 exr_library_source 逐字节读回并算 SHA-256。
- 坏/超限文件保留原状态；已提交不撤销；每项 status/committed/created 逐字断言；staging/state
  目录行末必须为空、行目录不得出现未声明条目或残留 SQLite journal。

## 3. 三轮运行（全部为 push 触发的自有 workflow，attempt 均为 1）

| 轮 | 受测 SHA | run | 结论 | 根因 |
| --- | --- | --- | --- | --- |
| 1 | 4844c923 | 40214586775 | 失败 | 本包自身缺陷两处：C 探针用 C 驱动链接 C++ 的 libexr_webdav（Linux/macOS undefined reference/DSO missing）；judge 把"平台不支持该故障"判成失败而非 pending（Windows 35 项后停） |
| 2 | d56297fc | 40215157859 | 失败 | 本包自身缺陷一处：check_s11.py:404 用 equal() 只给两个参数（TypeError）；此前 Windows/macOS 102 项、Linux 113 项全过 |
| 3 | 56ffaf51 | 40218428719 | 失败（停在 C2） | **owner 契约不一致**：cloud.missing 期望 io，实际 remote；同一行其余不变式全部成立 |

三轮的 jobs 与工件（GitHub Actions artifacts API 元数据；本机未下载/未解析任何工件字节）：

| run | job | conclusion |
| --- | --- | --- |
| 40214586775 | 121232863642 windows / 121232863880 macos / 121232864008 ubuntu / 121234177103 evidence | 全 failure |
| 40215157859 | 121234597680 windows / 121234597562 macos / 121234597685 ubuntu / 121236310941 evidence | 全 failure |
| 40218428719 | 121244517770 windows / 121244517614 macos / 121244517784 ubuntu / 121248308896 evidence | 全 failure |

第三轮工件（有效期 2027-01-23T17:50:52Z，sha256 为 API 发布的 digest）：

| 工件 | id | 字节 | sha256 |
| --- | --- | --- | --- |
| reader-final-s11-Windows-40218428719-1 | 12608289431 | 5086242 | c8c8b7bf92ce867c5c3d3d98819bc07dd602e64c8d5e150f82bae9ea8457691f |
| reader-final-s11-macOS-40218428719-1 | 12608847191 | 5119079 | 43482c18a3afa8ca360e19889337a6f2c56b892d1269a8cb97b1acef072b5c83 |
| reader-final-s11-Linux-40218428719-1 | 12608765607 | 5723767 | fee11638fac8a5286e159eaa0cfd8c836886c5cd82654413dc6fc10628d4e1c1 |
| reader-final-s11-evidence-40218428719-1 | 12609166928 | 507 | 3a16b435ebe5ac7baae60d6a865de6ba8751f761f61892f3dfaad88f6eecbffb |

第 1/2 轮的 8 个工件 id/字节/sha256/有效期记在 docs/reader-final-s11/validation.json。

## 4. 实际通过项（受测 SHA 56ffaf51）

- **batch 组 105 项（Windows/macOS）、116 项（Linux）全过**：B1 缺失 staging、B2 staging 是文件、
  B3 真只读 staging、B4 真 ENOSPC（Linux）、B5 故障解除后精确入库、B6 枚举后换书、
  B7 损坏+超限混批、B8 提交后取消。
- **cloud C1（真 TLS WebDAV）21 项全过**：staged SHA-256 = 原件 SHA-256、committed=1/created=1、
  staging 已删、重开后字节与 SHA-256 一致。
- 合计 127 项（Windows/macOS）、138 项（Linux）。

## 5. 未通过 / 未验证

**未通过（owner）**：row C2 cloud.missing —— reader_cloud_download 对"staging 目录不存在"返回
READER_CLOUD_REMOTE，而头文件把"staging file unreadable, missing or unwritable"定义成
READER_CLOUD_IO。staged=NULL、无提交、无行、无残留、目录未被创建，其余不变式都成立。
精确复现与两种收口方案见 docs/reader-final-s11/FINDING-cloud-staging-status.md
（cloud_import.c:492-518 的 REMOTE 兜底 + webdav.cpp:173/184/201 的 EXR_DAV_IO）。

**未执行**：judge 按设计在第一条被违反的断言处中止（产出的报告永不等于通过），因此 C2 剩余断言、
C3–C8、S1–S6、L1–L6 在所有轮次中都还没跑过（清单见 validation.json 的 unverified_rows）。

**pending（不是通过）**：Windows/macOS 无法注入真 ENOSPC（需 root 挂载），batch.nospace 明确记为
pending 并附原因；cloud.nospace / sideload.nospace 同因，且本轮未执行到。

**不授予**：真机/读屏/USB/性能预算与本包无关，本包只报告三台 CI runner 上的原生库行为。

## 6. 下一步（建议，属 root 决定）

1. 就 FINDING 里的两种方案选一：owner 把 EXR_DAV_IO 映射成 READER_CLOUD_IO（推荐，host 才不会把
   本地权限/空间问题当网络问题无限重试），或在头文件把"下载阶段 staging 失败 = REMOTE 且
   webdav_code=IO"写清楚。
2. 在该决定之上重跑本 workflow 一次；C3–C9、S1–S6、L1–L6 将首次执行。若 C3/C4 同样期望 io，请一并
   按同一决定处理。

## 7. 合规声明

未开 PR、未推默认分支、未打 tag/Release、未签名或公证、未删除任何会话或文件、未修改 owner 代码或
原断言、未降低断言、未把不同 source/run/job 的片段拼成通过、未在本地构建/测试/语法检查/生成夹具/
下载解析工件。测试凭据只由 TLS fixture 在本 job 内临时生成，spec 文件用完即删，judge 结束时调用
fixture.assert_secret_free 扫描输出目录。
