# S11 原件导入持久化故障回归 — 契约与行表

实现起点：0889f7d1e9a537c6c1b05456547e016b26e1cd85（树内 SDK = 批准 3.41.0 edddc463c06ed5731195cdb8f06b2df6dff7699e）。
本包**不修改** SDK、四个模块、apps/、extras/、原 tests/、原 workflow。

## 被测的四个既有公开接口

| 接口 | 头文件 | 私有 staging | 提交边界 |
| --- | --- | --- | --- |
| EXReaderSideload: exr_sideload_import_file | extras/sideload/include/exr_sideload.h | SDK 内部：整书复制进 SQLite（EPUB/CBZ/PDF 走 128 MiB 流式，其余 32 MiB 有界内存） | exr_library_import*_unique 成功返回 |
| EXReaderBatchImport: reader_batch_import | apps/reader/batch-import/include/reader_batch_import.h | 调用方给的 staging_dir 里每项一个 reader-batch-*.tmp，拷完先比 before/after 戳记，再交给 sideload | 同一 SDK 调用；committed 只在该调用返回后置 1 |
| EXReaderCloudImport: reader_cloud_download + reader_cloud_import | apps/reader/cloud-import/include/reader_cloud_import.h | 阶段一在 staging_dir 发布一个 cloud-<hex>.<ext> 并记录 SHA-256；阶段二重读并校验长度+SHA-256 | 仍是 sideload 调用；committed=1 胜过其后的取消 |
| EXReaderLocalDownloads: reader_ld_remove / reader_ld_reimport | apps/reader/local-downloads/include/reader_local_downloads.h | 自有 state_dir：intent.rdi / intent.tmp + originals/<sha>.open staging 副本 + originals/<sha>.orig | 先 BEGUN→PREPARED→UNMAPPED→DELETED 逐级推进；重新导入时先复制并哈希，再交 sideload，最后写映射 |

四个接口共用同一条语义：**私有 staging 写不成就不许提交；提交成功后原件与已提交行一律不撤销。**

## 行表（每个 row 一个独立工作目录、独立 SDK 库，进程每次重开）

| 行 | 故障（真 OS 注入） | 断言要点 |
| --- | --- | --- |
| B1 batch.missing | staging 目录不存在 | 聚合 IO、无 per-item 结果、0 行、不自动建目录 |
| B2 batch.notdir | staging 路径是普通文件 | 聚合 ARGUMENT、0 行 |
| B3 batch.readonly | staging 目录只读（POSIX 0555 / Windows icacls deny WD,AD） | 每项 FAILED、committed=0、SDK 码 IO、staging 空、0 行 |
| B4 batch.nospace | staging 在 256 KiB tmpfs 上，3 MiB 原件 | 写失败后同 B3；tmpfs 里无残留临时文件 |
| B5 batch.retry | 故障解除后同一原件 | IMPORTED/committed=1/created=1；重开后字节与 SHA-256 一致 |
| B6 batch.changed | 枚举后原件被换成另一本书 | 入库字节 = staging 当时那份；size_hint 不被信任；输入文件本身未被改动 |
| B7 batch.rejects | 同批：正常 + 损坏 EPUB + 超限 TXT | 正常项提交；损坏 FORMAT、超限 LIMIT，都 committed=0；三个输入 SHA-256 不变；staging 空；重开 1 行 |
| B8 batch.cancel | 提交 1 项后取消 | 已提交保留、后续 CANCELLED+committed=0；重开 1 行；补跑后 3 行且旧的没被撤 |
| C1 cloud.ok | 正常两阶段 | staged_sha = 原件 SHA-256；committed=1、created=1、staging 已删、重开字节一致 |
| C2 cloud.missing | staging 目录不存在 | 下载 io、staged=NULL、不建目录、0 行 |
| C3 cloud.readonly | staging 只读 | 下载 io、staged=NULL、staging 空 |
| C4 cloud.nospace | 256 KiB tmpfs + 3 MiB 远端 | 下载 io、无发布文件、tmpfs 无残留 |
| C5/C6 cloud.flip / truncate | 两阶段之间改动 staged 字节（同长/变短） | corrupt、committed=0、staging 已删、0 行 |
| C7 cloud.cancel | 传输中取消（第 2 次轮询） | cancelled、staged=NULL、无残留 |
| C8 cloud.cancel_import | 提交前取消 | cancelled、committed=0、只删 staging、0 行 |
| S1 sideload.ok | 正常 | created=1、重开字节/SHA-256 一致 |
| S2 sideload.cancel_before | 第一次轮询就取消 | CANCELLED、book_id=0、0 行 |
| S3 sideload.cancel_mid | 3 MiB 复制到第 5 次轮询取消 | CANCELLED、0 行 |
| S4 sideload.pdf_cancel | PDF（SDK 调用不可中断）提交前取消 | CANCELLED、0 行 |
| S5 sideload.mutated | 提交后改动调用方原件 | 库内字节与 SHA-256 仍是提交时那份 |
| S6 sideload.nospace | 库文件所在卷仅 512 KiB，3 MiB 原件 | IO/DATABASE、book_id=0；重开 0 行；扩容后重试 created=1 且字节一致 |
| L1 ld.basic | 正常映射 | catalog local=1、重开字节一致、无 pending |
| L2 ld.missing | state 目录不存在 | io、removed=0、映射与 SDK 行都还在 |
| L3 ld.readonly | state 目录只读 | io、outcome=none、state 内无文件、映射与行都在；恢复后删除成功，重开 0 行、local=0、状态目录清空 |
| L4 ld.reimport | 卸载后 state 只读时重新导入 | io、0 行、local=0；恢复后 attached、重开字节一致、local=1 |
| L5 ld.cancel_before | 启动前取消 | cancelled、removed=0、未进入任何 stage、无 pending |
| L6 ld.cancel_begun | 写完 BEGUN 后取消 | cancelled、映射与行都在；recover 只回滚，重开后仍 1 行且字节一致 |

## 共同不变式（每一行都断言）

1. status / committed / created / book_id 与公开头文件的语义逐字相符，不用"预期拒绝"替代。
2. 原始输入文件的 SHA-256 在故障前后不变；坏/超限文件保留原状态。
3. staging/state 目录在行结束后没有任何文件；行目录内没有未声明的新条目，也没有残留 SQLite journal。
4. 每次都重新起进程打开 SDK 库，用 exr_library_source 逐字节读回并计算 SHA-256。
5. 已提交的行在任何后续失败、取消或重开中都不会消失。

## 平台能力与 pending

- 只读目录：三平台都注入（POSIX 权限位 / Windows ACL deny），并在注入后先试写一次证明真的写不进去。
- 有界卷（真实 ENOSPC）：仅 Linux（sudo mount -t tmpfs，256 KiB / 512 KiB，先试写超过容量证明 ENOSPC）。Windows/macOS 无同等免管理员配额手段，对应行记为 pending 并附具体原因，而不是填通过。
- 云行复用仓库已有的 TLS WebDAV fixture（tests/reader_reviewed_composition/webdav_fixture.py），只读引用；自签证书只进本次运行的临时信任库。
