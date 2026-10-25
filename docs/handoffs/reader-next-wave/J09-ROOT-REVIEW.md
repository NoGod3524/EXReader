# J09 root 复审与修复

从原交回 `e32fa06aeb3508eb07f0c7ef7443a3750a1f0e43` 建立独立分支 `codex/reader-book-information-review`，原 owner 工作树不改。已阅读快照实现、公开契约、C探针、独立API比对及严格汇总。

源码缺陷：`read_parser` 内部取消或返回内存失败时，顶层直接返回该码，却留下入口清零的 `error.status=OK`。现复用原错误填充函数，保持取消/失败不发布快照；既有逐轮询点取消检查新增返回码/error.status一致及错误信息非空断言。

受测 source `aa76a35bfdec067da0850bcbb4a3c1d16cd096ff` / run `40154360163` / attempt1 全4作业success：Windows `121052432755`、Linux `121052432712`、macOS `121052432560`、strict `121053053726`。三平台各22个场景、795次断言通过，原九格式、公开API独立比对、错书身份、不可变寿命与库文件不变检查保留。strict实际认证三个上游作业及同轮ZIP，`accepted=true`、`problems=[]`；已只读核对真实云端日志，未本地运行或下载工件。

最终证据HEAD `723cd5e7f9849fe050f2159a9f3a125848cdbec4` 只改两份模块证据文档，旧交回的证据完整保留在JSON。复审关闭，等待共同源码接入，不授予宿主信息弹窗、性能或六目标产品验收。
