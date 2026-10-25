# J04 root 复审与修复已关闭，Android宿主接线继续

独立 review 从原交回 `635ddcb3f865059fd481f8deb9f7927e75743c6d` 开始，未修改外部 owner 的原工作树。root 已复读最终 ticket/lease/可靠pipe/交付异常改动及严格工件认证器，并只读核真实云端终态与汇总日志。

修复包含 cancel/commit 共用短锁线性化；重复原件每个 ReadyRequest 独立 lease、最后一个释放后才删除；拒绝 foreign/stale/跨close对象误释放；可靠pipe checkError 抛出时也关闭 descriptor；query.SIZE只作声明校验，避免未知长度pipe小报后静默发布前缀；宿主直接Executor回调抛异常不会再被复制catch包装成第二个onFailed。

最终 tested source `f5046e1fbe2cc91d2ec71a51d2020c1c38e4d969` / run `40161341409` / attempt1 三作业 success：android `121073369108`、guards `121073369421`、summary `121074094360`。95/95含原78、42必需具名结果；20,000次真实双线程竞争、重复/跨代际lease、32次真实错流FD 108→108、直接Executor异常后Ready=2/Failed=0及两lease清理。strict `problems=[]`，Actions内重算原ZIP并绑定两真实上游作业。

证据 HEAD `e4f20df783872dd536f40a7431b200352aa2da17` 仅两docs区别。android工件 `12586462366` /11,536,095B /SHA256 `9ef65c6ee43a0f65fb64b0a2d865f68631ab906f375655aafd5b606cfdba60ac`，到期2027-01-23T04:17:26Z。首轮FD观测包含反复Activity启动的107→118失败、隔离pipe复制后的94项成功轮均保留，没有放宽原baseline+4限制。

授予仅API34 default x86_64模拟器组件；真实系统选择器/第三方provider/真机、同步Binder query/getType/open阶段取消deadline，以及128MiB暂存原件在当前32MiB宿主renderer的阅读能力仍不授予。

Android owner 已在新的 `reader-android-host-import` 独立树从共同 `e4356a6e` 普通合入最终证据，继续application controller、VIEW/SEND/SAF到原唯一SDK owner的实际接线。J04模块交付与Pan旧交付不再混写。
