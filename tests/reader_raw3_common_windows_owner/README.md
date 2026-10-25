# 共同源码 Windows raw owner 完整叶子（准备稿）

起点 `bd8c3638019280bea6496b778339abf04629bd27`；本包只新增自身五文件及一个工作流，
尚未推送或执行。root 需先明确批准这六条 `combined.py::EXTENSIONS` 路径；否则源码正例按设计拒绝。
这里不授予当前 bd8c 的完整 Windows raw 验收。

## 当前缺口

当前共同 Windows 叶子只运行完整原 OFF/F3/atomic13 链，没有运行原 `host_build.py` 的
真实 legacy/raw 双 profile、owner 九报告、三次外部 TerminateProcess、真实账号窗口 TLS 接收
和 Mac11 在两个独立真实进程里的公开 SDK FOUND/recapture。因此不能用该 OFF 叶子代替 raw owner 叶子。

## 固定来源与完整保留

原 host workflow、host_build.py、authenticate.py 及 suite 固定来自
`c4bb1feac3e2b404777810a526da43198b106723`；独立原认证参考 run `40222024767/1`。
它只是历史实现/证据参考，本工作流不读取或拼接该旧运行的验收结果。

新 host job 的 workflow 反向投影必须等于原 `reader-windows-raw3-host.yml`：
仅工作流名/分支与 source guard 入口变化，附加独立认证 job。原 `host_build.py` 整体原样执行：

- legacy/raw 两 profile 的真实安装 SDK、模块、Win32 host；原 compact22 和 bulk21 各执行两份。
- legacy suite、raw suite/fresh，以及两处 raw kill 的旧拒绝/新恢复、旧 pending kill 的新拒绝/重试，共九份 owner 报告。
- 三次外部 `child.kill()`（Windows TerminateProcess），保留 flushed marker、PID、原 pending 字节及消费后的恢复结果。
- 原 `network.py` 实际账号窗口、原生 Win32 TLS、认证请求、全部 256 revision shards、四格式实际打开。
- 固定 Mac 原包四原件、15 wires、11 reading records；同一个真实 Windows owner 的两个独立进程分别 READ，
  再经独立公开 SDK resolve/capture，各 11 个 FOUND；READ 自身不能冒充 FOUND，NULL callback 必须拒绝，状态保持不变。

SDK3.41、raw 七包、Windows owner/metadata/bulk、原 suite/driver/strict 全部逐树 pin，生产源码不改。
WebDAV 使用共同树已经批准的 `98fa8e0f…` 修复，不回退到旧生产实现。

## 新 guard 与认证入口

新 source report 为 `guard_kind=common-windows-owner`、`legacy_guard_executed=false`、`accepted=false`。
它写入自己的 `common-source.json`，不伪造原 guard 的 report.json。
只纯加载 root EXTENSIONS，不调用 configure、不修改 sys.modules；root 批准的包装器文件可变化，
其他 bd8c 旧文件锁定。全局相对1a6d的新增文件集必须恰好等于 root 清单，且普通100644文件；
没有预先宽泛允许未来文件。

旧独立 authenticate 要求一个已经 completed/success 的单 host job 旧 workflow；同次新认证正在运行时，
整个新 workflow 不可能先完成。为此仅作三处可反向逐字验证的适配：

1. 独立 run 入口改为实际当前 event source/run/attempt、新 workflow 与精确 host/authenticate 两 job；
   host 必须本 attempt completed/success，认证 job 必须当前 in_progress。没有伪造 API 状态或 GITHUB_SHA。
2. 原所有 ZIP/程序/九报告/真实 kill/TLS/Mac11 断言执行后，认证同一原 ZIP 内的 common source/负例报告，
   并强制原来条件性的 network/Mac11 路径确实已经执行成功。
3. 原报告写出前额外绑定 common 来源，强制 owner_reports=9、真实 TLS 和 Mac11；原断言正文保留。

旧 authenticate.py 文件不改。云端严格入口从固定原源码构造上述适配版本，先验证反投影完全相等，
再完整执行；不拦截 assert、不伪造旧 guard 成功，也不把旧认证 run 作为新运行输入。
17 项独立拒绝控制仅在 Actions 执行，含实际 Git mutation tree、workflow 变更、event SHA 及认证正文改动。

成功范围仍是本次共同源码 Windows owner 叶子，不含完整产品、物理设备或共同双向互通。
原 Mac peer 固定来源 `15dab6b2… / 40196978163/1`，不会改称共同源码发送方。
完整原 OFF/F3/atomic13 是另一叶子，最终必须与本叶子在同一最终源码重新执行后由 root 汇总。
