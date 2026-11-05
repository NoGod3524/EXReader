# G07：账号同步故障一致性专项

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-sync-resilience`。
类型：测试；优先级：P0；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_sync_resilience/**`
- `.github/workflows/reader-sync-resilience.yml`
- `docs/READER-SYNC-RESILIENCE.md`
- `docs/validation/reader-sync-resilience.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

只新增独立消费者/故障服务与验收，不改session/sync/revisions/WebDAV实现。复用已安装原生包和公开API，补原20项以外的故障边界。
覆盖PUT远端已落盘但客户端尚未ack、GET验证前后、原件下载临时文件/原子发布前后、outbox提交后进程退出；真实401/403/429/503、断连、timeout、重复请求与同账号重开。
用受控HTTP服务的阶段握手触发真实进程kill；无生产test-hook时在外部可观测边界测试，不为命中行号改共享实现。核对幂等、不错误覆盖、原件身份、history/outbox保留及账号隔离。
发现共享缺陷时交最小复现/建议补丁给root，本包不得偷偷修改其他owner。

## 云端出口

Windows/Linux/macOS实际原生HTTPS和独立进程，保留原20项；每个新增具名边界列预期/实际和持久记录。
输出无秘密的协议操作轨迹、真实进程退出身份、公开API回读和原件SHA；任何未命中边界记未覆盖。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/reader_session/check_session.py`
- `tests/reader_sync/check_sync.py`
- `apps/reader/session/include/reader_session.h`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

