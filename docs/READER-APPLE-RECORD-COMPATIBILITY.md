# Apple 旧阅读记录的明确升级策略

## 当前独立标签互通修复（原生与策略范围已验）

后继分支 `codex/reader-parser-tag-interop` 处理真实源码中的标签不一致：Android的原JNI formatter为 `exreader-sdk-<exr_version()>`，其Java reflow/EPUB及CBZ resolver要求该精确前缀；Windows/GTK/Apple写入纯版本号，Apple也曾精确要求纯版本号。因此同SDK也会互拒。

仅在实际3.41消费者增加明确的四个已知标签：`3.41.0`、`exreader-sdk-3.41.0`、`3.40.0`、`exreader-sdk-3.40.0`。旧3.40行为保持原样，未知标签不作通用strip/semver猜测。Android原formatter、真实runtime与所有旧wire保持不变；原件、模式、FOUND与复捕获校验仍执行。

受测源码 `b1a7b7891cd394671842164a07a86c8e316dace3` / [40176647484](https://github.com/NoGod3524/EXReader/actions/runs/40176647484) attempt 1 已通过原生作业与严格汇总：18 个进程阶段、两个 SDK 各 19 项原 owner 检查、Android 纯 Java 策略 20 个正反例及 6 项协议拒绝均通过。

本轮新增公开 G03 生成的两组前缀协议夹具、原 owner 拒绝对照及修正 Apple owner 读取。这些前缀夹具按原 JNI 的精确拼法生成并绑定实际 SDK runtime，**不是 Android 设备发送端**。Android 实际宿主接收和真实双向交换仍由独立任务验证。下文保留原 `898e773c` 的裸版本号升级结果。

当前原生工件 `12592549982` 为 53,257,384 字节，SHA-256 为 `af40a35b4b916c68f4cc4ea9307e6baf4be165375d7d79698c0a31f40b8da88e`；严格汇总 `12594080612` 为 566 字节，SHA-256 为 `e03a340b56e3df8e8454864ad60ecd7349b1471c9ac98be88fb6cb9150bebe2a`。两者有效期至 `2027-01-23T08:26:53Z`。本次证据更新只改文档，不把已通过原生范围转授给跨设备互通。

独立分支从 Apple 主题候选 `eea3087c2ef27b9d45e00333ef0a16e586a0ac6e` 创建。SDK 保护树仍逐字等于已验候选 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，原冻结 3.40 提交和 wire/schema/预算不变。

实际 Apple 宿主的 `HostReadingWorker.decoded` 与私有请求校验此前要求记录 parser 等于当前 `exr_version()`，因此 3.41 会拒绝真实旧3.40记录。D01只读矩阵已证明公开selector可解析，但不授予宿主接纳。

本候选只增加明确的单向版本对：实际3.41允许读取保存为3.40的记录及显式重试原请求；同版本沿用原规则，其他版本、未知标签和旧宿主降级读取新标签仍拒绝。它只允许进入后续校验，实际宿主仍独立核对原件format/hash/bytes、产品图与预期heads、FOUND及真实重捕获。旧wire、记录parser、待完成请求ID和原selector均不改写，恢复/重试仍是用户明确动作。

独立Actions把两份SDK从固定提交分别构建安装，用实际原Apple owner源码在两个SDK上编译对照，再编译修正owner。真实旧进程保存TXT/有界EPUB/PDF/CBZ的进度与书签，关闭后新进程重开同一库副本；旧owner+新SDK必须拒绝，修正owner+新SDK必须精确解析并保持旧wire，另有同版本与反向拒绝对照。实际旧进程在原请求持久化后/提交后退出，新进程显式重试核对原ID、capture、parser与created=1/0。两个SDK分别保留原19项owner/recovery完整测试。未知parser与错误原件仍拒绝。

所有构建、测试、夹具和工件处理只在Actions。

## 实际验收

受测源码 `898e773c322fdd8d82184cacb0ce23c983af2edf` / [40173356985](https://github.com/NoGod3524/EXReader/actions/runs/40173356985) attempt 1 已success。实际原生生产者 `121108728132` 与严格认证作业 `121110070831` 均success；11个真实进程阶段、两个SDK各19项原owner/recovery检查、6项认证拒绝均通过，`problems` 无缺口声明替代测试。

其中四格式共8份真实旧进度/书签，在同一旧库副本上分别由原3.40 owner读回、原owner＋3.41拒绝、修正owner＋3.41精确解析及复捕获。严格汇总逐项比较相同revision、原wire字节散列、book key、真实producer parser。真实新3.41记录同版本读回通过，原3.40 owner反向读取按原规则拒绝。两种真实进程退出边界后，新进程显式重试保留旧capture、revision和parser，分别created=1/0。

| 工件 | ID | 字节 | SHA-256 |
| --- | ---: | ---: | --- |
| 原生原件、程序、库、报告 | 12591740607 | 53067165 | `23a4259f920adb75b6803bd05be4b63e6926a218f3b8ba15df8555dcae455130` |
| 严格汇总 | 12591950169 | 534 | `c1bfec976ce0a7756582f609c43f3bf8db3df5b2e33303f8f5c366b9ec1d6a7a` |

两份工件有效期至 `2027-01-23T07:35:40Z`。汇总在Actions认证同源码、attempt、成功作业、唯一未过期ZIP、大小/散列、原报告与实际二进制；本地只读云端日志及API元数据。证据提交仅更新本文及验收JSON，`[skip ci]`。

授予范围仅为本轮macOS原生Apple owner进程的8份点记录及两种待完成请求重试。原19项同版本测试还覆盖高亮、编辑、删除、恢复和旧v1，但不能把它们计作这些项目的跨版本UI验收；D01原公开selector矩阵仍保留自己的范围。尚不授予iOS实际旧库、宿主UI、降级兼容、物理设备或完整产品。共同3.40分支仍未合入此修复。
