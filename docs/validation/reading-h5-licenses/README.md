# H5 云端证据：阅读 preset 许可证材料

分支 `handoff/reading-h5-licenses`，起点 B=`b529513b7e8e8992786f8c679c0ec6c92110b035`。
工作流 `.github/workflows/reading-licenses.yml`，`ubuntu-22.04`，CMake 3.31.6，
每个 preset 从干净 checkout 配置、构建、安装后检查。结论只是材料齐备检查，不是法律判断。
清单与未解决项见 [READING-LICENSES](../../READING-LICENSES.md)。

## 原库存候选（保留）

受测 SHA `e3fa3f7748e9b06896487ba5c7cd48d9cf290b5b`，run `39858675511`，attempt 1，结论 success。

| Job | id | 材料检查 | 失败 | 待处理 | 自检 |
| --- | --- | --- | --- | --- | --- |
| `licenses (reading-core)` | `120103386597` | 通过 | 0 | 2：expat 顶层 `COPYING`、libwebp `PATENTS` 未安装 | 23 个反例拒绝，1 个待处理例，21 个清单组件 |
| `licenses (reading-library)` | `120103386041` | 通过 | 0 | 3：同上，加 SQLite 无随包许可证文件 | 同上 |

两份报告的 `source_sha` 均为受测 SHA；音频 / MP3 / AAC 开关均为 OFF，构建层无 `audio`，
`_deps` 无 minimp3、FAAD2。libaom 上游 `CHANGELOG` 实测版本 3.15.2，与 notices 声明一致。
此处旧库存结果仍有上述 pending，不授予后续新增的 `release_ready`。

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

## 四项材料修补后的严格候选

分支 `codex/reading-license-fixes`，基线 `b365de7d31a2daca4f208dc625d064691fc331ec`。
受测完整 SHA `72c1e89659679b7d7b76504007a84d6d8c453db3`，
run [39862694733](https://github.com/NoGod3524/EXReader/actions/runs/39862694733)，attempt 1。
两 preset 从干净 checkout 配置、构建、安装；严格检查明确带 `--require-release-ready`。
`material-pins` 诊断作业在正常验收模式跳过，不属于两 preset 验收。

| Preset | job | 结果 | 材料检查 / 严格发布条件 | failures / pending / mandatory_missing | 自检 |
| --- | ---: | --- | --- | --- | --- |
| reading-core | 120117102454 | success | true / true | 全为空 | 31 项反例、1 项缺口阻断例、3 项材料正控、21 组件 |
| reading-library | 120117102853 | success | true / true | 全为空 | 同上 |

两份报告 `source_sha` 均为 `72c1e896…`。31 项反例包含原 23 项，新增缺 PATENTS、
缺独立根 COPYING、旧 zlib 错目录副本、缺安装声明、源头 dedication 改动、
重打包声明改动、缺来源元数据、源版本漂移 8 项。
缺口阻断例证明“未登记安装的上游 PATENTS”即使库存检查通过，也会产生
`mandatory_missing` 且 `release_ready=false`。

| 成功工件 | ID | 字节 | digest | 到期 |
| --- | ---: | ---: | --- | --- |
| reading-licenses-reading-core-39862694733-1 | 12462960815 | 80652 | `sha256:efd44315fbb963cc7794bdbc4948dee5a9cddbe6ae867912b3166a9800a34264` | 2027-01-20T22:08:19Z |
| reading-licenses-reading-library-39862694733-1 | 12461459484 | 81548 | `sha256:c342decd63ecd140f398a1804c8ccf617a50dbea0e14e0af5f5d6ace8ab39e50` | 2027-01-20T22:08:19Z |

工件 API 共两项，`workflow_run.id/head_sha` 同本轮 run／受测源码，均非空、未过期，digest 格式有效。
逐项结论来自同次完成日志中的 JSON 报告；未下载 ZIP。

### 新材料来源与观测

| 原文／声明 | 安装路径（`share/exreader/licenses/` 下） | 字节 | 实际 SHA-256 |
| --- | --- | ---: | --- |
| Expat R_2_9_0 子项目 `expat/COPYING` | expat/COPYING | 1144 | `31b15de82aa19a845156169a17a5488bf597e561b2c318d159ed583139b25e87` |
| Expat R_2_9_0 根 `COPYING` | expat/upstream-root/COPYING | 1144 | `73cc92f80889ab23c7287b1a11dd50fdec190c3f26ebe5938c579043817d651e` |
| libwebp v1.5.0 `PATENTS` | libwebp/PATENTS | 1436 | `cc3273e0694ea5896145e0677699b53471b03ea43021ddc50e7923fbb9f5023c` |
| zlib v1.3.1 `LICENSE`（只装自身目录） | zlib/LICENSE | 1002 | `845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243` |
| 仓库 SQLite 原文声明 | sqlite/sqlite-public-domain.txt | 761 | `abc1b93c15fe0a92ec55020569e10fb8206de2cf535c30e70f7f9d5428e20bcc` |

SQLite 仅在 reading-library 活跃；reading-core 明确不安装该文件。
library 报告确认 `sqlite3.h` 版本 3.54.0，实际固定下载源码 `sqlite3.c` SHA-256 为
`2da161e310ef0aba3465f22a4d12b8a43723236f0942fa76e8aac523c3317243`。
仓库声明包含固定归档 URL／归档散列／版本及逐字 dedication，检查器同时匹配真实源头与随包文字。
它不被描述成上游提供的 LICENSE。

声明文件散列由非验收 pin run `39862424521`、job `120116192066` 在 GitHub Actions
执行 `sha256sum` 取得；该 run 的受测源为 `bcaa45c3407eb5fef855dec857f3f120e287f8a4`，
只运行 material-pins，两个 preset 未验收。散列随后固定到检查清单，最终通过仍只认上述完整 run。

### 本轮保留的失败

前候选 `659c7cb495c6305cb8a4decd3654bf9dbbf086b4`，run `39862581613` attempt 1：
reading-core job `120116715422` success；reading-library job `120116714977` 在材料检查失败。
唯一失败为 `sqlite: original license source missing licenses/sqlite-public-domain.txt`。
原因是旧检查器对 fetched 组件的 `origin=repository` 文件错误地从 `_deps/sqlite-src/` 查来源；
实际安装字节、原文摘录及版本已正确。修复按 origin 选择仓库根／上游目录，并增加独立正控，
随后以 `72c1e896…` 整轮两 preset 重跑；没有将旧 core 的成功拼入新候选。

| 保留工件 | ID | 字节 | digest |
| --- | ---: | ---: | --- |
| reading-licenses-reading-core-39862581613-1 | 12461499566 | 80653 | `sha256:fba50b341176221bc45f567dee843c82268be833c88801a8d6ddee64595992b8` |
| reading-licenses-reading-library-39862581613-1 | 12462786360 | 81574 | `sha256:97170414a5a86e5c1f1eea8e0e992ebacbac1e7b6e746b22c3d832a11ab97f06` |

`release_ready` 仅授予声明的 Linux 两种静态 SDK preset 材料范围，`legal_judgment=not performed`。
没有修改默认分支保护、仓库 About、SDK API，或给其他平台／宿主／音频包转授结果。
