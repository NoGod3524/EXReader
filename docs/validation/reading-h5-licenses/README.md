# H5 云端证据：阅读 preset 许可证材料

分支 `handoff/reading-h5-licenses`，起点 B=`b529513b7e8e8992786f8c679c0ec6c92110b035`。
工作流 `.github/workflows/reading-licenses.yml`，`ubuntu-22.04`，CMake 3.31.6，
每个 preset 从干净 checkout 配置、构建、安装后检查。结论只是材料齐备检查，不是法律判断。
清单与未解决项见 [READING-LICENSES](../../READING-LICENSES.md)。

## 受测候选（有效）

受测 SHA `e3fa3f7748e9b06896487ba5c7cd48d9cf290b5b`，run `39858675511`，attempt 1，结论 success。

| Job | id | 材料检查 | 失败 | 待处理 | 自检 |
| --- | --- | --- | --- | --- | --- |
| `licenses (reading-core)` | `120103386597` | 通过 | 0 | 2：expat 顶层 `COPYING`、libwebp `PATENTS` 未安装 | 23 个反例拒绝，1 个待处理例，21 个清单组件 |
| `licenses (reading-library)` | `120103386041` | 通过 | 0 | 3：同上，加 SQLite 无随包许可证文件 | 同上 |

两份报告的 `source_sha` 均为受测 SHA；音频 / MP3 / AAC 开关均为 OFF，构建层无 `audio`，
`_deps` 无 minimp3、FAAD2。libaom 上游 `CHANGELOG` 实测版本 3.15.2，与 notices 声明一致。

| 工件 | id | 字节 | digest | 到期 |
| --- | --- | --- | --- | --- |
| `reading-licenses-reading-core-39858675511-1` | `12460308703` | 79546 | `sha256:cd727c19fe2cb05d6992d26642d317661fd751b848519aea062d60bb63c9ef0d` | 2027-01-20T21:36:50Z |
| `reading-licenses-reading-library-39858675511-1` | `12460902628` | 79734 | `sha256:437745e7bfc0bbfd0d367edd679c49ab4dfadf9a5cf3cf24a7cc068e183a832f` | 2027-01-20T21:36:50Z |

每个工件含该 profile 的 `licenses.json`（逐组件清单）、`CMakeCache.txt`、`exr-modules.json`、
安装后的 `share/exreader/`、根目录 `LICENSE` / `THIRD_PARTY_NOTICES.md` 与
`EXReaderDependencies.cmake`。本地未下载工件；以上数据读取自 run 日志与 Actions API。

## 保留的失败运行

受测 SHA `711984e1eec2c511c052d88f151454aa140ddbc7`，run `39858122616`，attempt 1，结论 failure。
两个 job（`reading-library` `120101527988`、`reading-core` `120101528582`）均完成构建与安装，
检查失败原因只有两类：19 个许可证原文尚未在清单固定散列；第一方 `LICENSE` /
`THIRD_PARTY_NOTICES.md` 在不固定散列时被误报为散列不符（检查器缺陷）。
本次运行观测到的散列随后原样写入清单，缺陷在 `e3fa3f7` 修正。自检只在真实清单未固定散列处停止，
合成正反例均已先行通过。该运行没有未登记的下载依赖、链接归档或许可证文件。

| 工件 | id | 字节 | digest | 到期 |
| --- | --- | --- | --- | --- |
| `reading-licenses-reading-core-39858122616-1` | `12459918371` | 79870 | `sha256:e1e25f263aa42f0814dc3d0291ad19f9b7073799f593dd44553f1c6b0e7533ad` | 2027-01-20T21:32:44Z |
| `reading-licenses-reading-library-39858122616-1` | `12459314795` | 80045 | `sha256:811df33056f679a4474d4a11c46ad380fcb8181bd7b4dfa3255cef604a9de55b` | 2027-01-20T21:32:44Z |

## 限制

- 只覆盖 Linux 静态 SDK；其他平台、原生宿主包与音频构建未运行。
- 后续纯文档提交不改变受测源码；新的工具或清单改动须重新运行，旧通过项不能拼入新候选。
