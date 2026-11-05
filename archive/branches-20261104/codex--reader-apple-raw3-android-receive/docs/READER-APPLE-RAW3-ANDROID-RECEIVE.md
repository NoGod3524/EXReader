# 真实 Android → macOS 原始记录接收候选

状态：指定 Android → macOS 接收方向已通过。受测源码 `5062d5cd570eb9be9449e790895b5430d344d11d`，[run40210925809](https://github.com/NoGod3524/EXReader/actions/runs/40210925809) / attempt1，四个作业同轮全部 success。独立分支 `codex/reader-apple-raw3-android-receive` 从Mac封存44eabdc8建立，生产源码、SDK、七包与原全部Mac裁判逐字不变；新增只有接收测试、独立工作流和证据文档。

输入固定Android实际受测源 `4a04a9cc74dde67f755c87e87b278d63a254a3ac` / run40207467982 / attempt1。原19-wire /4原件/11记录ZIP12604233206，18,682B，SHA256 `a38bffdb57ca35699e21b902def18a9d584a6055b7fbef41995e61b240c6168c`；manifest SHA256 `65a7c6e2be7a0d80e1a7c9eed3731383aa9bdbc71cfd09f89ce63861193b5345`。真实native证明ZIP12604412854，113,970,957B，SHA256 `c3db2ad1a2e31bc53d01620f2ef90e02a976e3b4f90ac76ed2e179c7c9052805`，实际APK和其中SDK共享库逐字认证。

先同源完整重跑原Mac12阶段、原兼容18进程、两真实SDK各owner19以及Java20，并执行原未改严格裁判；这一步结束后才产生新接收工件，以保持原裁判的单工件约束。新接收job恢复该同源真实Mac程序及唯一动态SDK，原程序/SDK散列、链接归属和七包EXACT来源继续核对。

接收直接复用原未改的实际HostCatalog/HostSession/HostAccountSession程序：独立owner接收与新进程重开，然后真实Foundation HTTPS账号Session接收19条完整原wire和4原件，再新进程重开。每个进程逐项实际SDK FOUND、复捕获、原wire/完整父图与只读状态验证；网络阶段只从真实下载的原件导入，禁止手动receive补wire。实际SDK原始parser标签保留，按既有明确允许规则接纳Android的 `exreader-sdk-3.41.0`，不改写保留wire。

只授指定实际Android包到macOS接收方向。原Mac裁判里的Android互通false标记保留，新方向由新增身份闭合裁判单独授予；同源双向、iOS UI、真机和整个产品继续独立验收。构建、语法、工件下载/解析、证书信任和执行全部只在Actions。

## 同轮实际证据

| 作业 | ID | 结果 |
| --- | --- | --- |
| 原实际Mac程序与完整原控制 | 121221773472 | success；12 raw阶段、18兼容进程、两SDK各19 owner、Java20 |
| 原未改Mac严格汇总 | 121224098177 | success |
| 实际Android → Mac接收 | 121224143346 | success |
| 新身份闭合严格汇总 | 121224421216 | success |

接收原程序 SHA256 `1e5f146efd993f21fd24d7ea8ed350ba854b403498761b1c2da06765a7ea2897`；唯一动态SDK SHA256 `64fa27c57d88eebd0e348908c3f8831d900363a3220af7a24c80db00ee3f37e0`。同轮原程序重新编译，未替换为专用接收实现。

| 实际进程阶段 | PID | 原记录实际SDK FOUND/复捕获 |
| --- | ---: | ---: |
| 独立owner接收 | 2403 | 11/11 |
| 同owner新进程重开 | 2406 | 11/11 |
| 原生账号HTTPS接收 | 3027 | 11/11 |
| 同账号新进程HTTPS重开 | 3042 | 11/11 |

两次网络阶段各完成256 shard一整轮；认证与系统TLS信任检查通过，远端原wire/原件散列保持不变。新严格裁判实际下载ZIP认证大小、SHA256、有效期、同轮源码/作业身份，并闭合Android实际APK内SDK共享库、原19-wire完整父图、4原件与11记录及接收者四进程报告。

| 同轮工件 | ID | 字节 | SHA256 |
| --- | ---: | ---: | --- |
| 原native | 12605523032 | 77055617 | `101e88a6b3f6493fee5c320d1c5a6c3d2b512095f2bef4eed7e025bb20384ee5` |
| 原strict | 12606241221 | 509 | `efe414989943cfa344146104306582ff5903133272b05f43ada7099221eb4db1` |
| 实际接收 | 12605778060 | 41839337 | `e7d56df798b8d7cfe6b4c2682cf621a8f1139450ba73867cd8739bbb9d2cc136` |
| 接收strict | 12606012685 | 1075 | `08f89ffabac221789efb58cbd3aa277abe9075f3744ce6f1d1d8bcfbfdbf7297` |

四工件有效期均为 `2027-01-23T16:16:56Z`。封存提交仅更新本说明与验收JSON，受测身份保持上述5062d5cd。
