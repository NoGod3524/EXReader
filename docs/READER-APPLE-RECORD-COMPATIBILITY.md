# Apple 旧阅读记录的明确升级策略

独立分支从 Apple 主题候选 `eea3087c2ef27b9d45e00333ef0a16e586a0ac6e` 创建。SDK 保护树仍逐字等于已验候选 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，原冻结 3.40 提交和 wire/schema/预算不变。

实际 Apple 宿主的 `HostReadingWorker.decoded` 与私有请求校验此前要求记录 parser 等于当前 `exr_version()`，因此 3.41 会拒绝真实旧3.40记录。D01只读矩阵已证明公开selector可解析，但不授予宿主接纳。

本候选只增加明确的单向版本对：实际3.41允许读取保存为3.40的记录及显式重试原请求；同版本沿用原规则，其他版本、未知标签和旧宿主降级读取新标签仍拒绝。它只允许进入后续校验，实际宿主仍独立核对原件format/hash/bytes、产品图与预期heads、FOUND及真实重捕获。旧wire、记录parser、待完成请求ID和原selector均不改写，恢复/重试仍是用户明确动作。

独立Actions把两份SDK从固定提交分别构建安装，用实际原Apple owner源码在两个SDK上编译对照，再编译修正owner。真实旧进程保存TXT/有界EPUB/PDF/CBZ的进度与书签，关闭后新进程重开同一库副本；旧owner+新SDK必须拒绝，修正owner+新SDK必须精确解析并保持旧wire，另有同版本与反向拒绝对照。实际旧进程在原请求持久化后/提交后退出，新进程显式重试核对原ID、capture、parser与created=1/0。两个SDK分别保留原19项owner/recovery完整测试。未知parser与错误原件仍拒绝。

所有构建、测试、夹具和工件处理只在Actions。当前尚无成功运行，不授予迁移、宿主UI或物理设备范围；首次运行可能暴露构建或探针假设问题。
