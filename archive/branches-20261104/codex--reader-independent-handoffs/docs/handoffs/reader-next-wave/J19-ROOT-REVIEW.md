# J19 root 复审返修：关闭失败与连接交接

受审源码 `2f4304c0a037e8f20b064bbfa248ea2e9371d436`，证据 HEAD `4f796a2a`，run `40138462305` 四种运行配置及汇总均 success。以下来自源码复审，旧绿保留，修复前不集成共同源码。

## 关闭线程创建失败会阻塞 owner

`extras/reader-tts-linux/src/reader_tts_linux.c` 的 `reader_tts_request_close()` 在 `pthread_create()` 失败时直接调用 `closer_main(h)`。后者调用 `drop_conn()` / `spd_close()`，可能在原调用线程做 socket 交互与线程 join；这与公开接口“request_close never blocks”的契约相反，而且没有覆盖此故障的实测。

请线程创建失败时不执行同步关闭，不丢失活动请求或把句柄留在无人推进的 CLOSING。返回明确现有失败状态，允许 owner 重试，并保留原请求、队列和连接；状态恢复必须与回调同步，不能把已结束请求复活。隔离测试注入实际线程创建失败，证明本次没有同步 close、输出/状态一致、destroy 仍正确拒绝、后续重试正常关闭。不得仅修改注释来接受阻塞。

## 旧连接结束前释放全局名额

`drop_conn()` 先 `slot_release(h)`，再取出并清空 `h->conn`、调用 `spd_close(c)`。另一个 owner 可以在旧连接的事件线程仍存活时取得 `g_conn_owner` 并建立新连接。共享回调忽略 client 参数，仅向当前 `g_conn_owner` 分发；这还破坏了模块自己声明的 libspeechd 进程单连接约束。

请保留名额直到 `spd_close()` 完成并 join 旧事件线程；关闭时不得持有回调需要的 `g_mu` 或 handle mutex。用真实关闭边界上的隔离门控，让另一个 owner 在旧关闭未完成时尝试创建/说话，证明仍不可取得名额；释放门控并证明旧线程结束后，新 owner 才可成功建立连接，旧回调不影响新请求。不得只循环顺序创建/销毁来覆盖该交错。

原负责人唯一修改原工作树 `C:/Users/Oscar/exreader-agents/j19-tts-linux` 和 `codex/reader-tts-linux`，保持原路径白名单及共同 C ABI。SDK、schema、wire、anchor 不改；全部构建、语法、测试、夹具与工件处理仍只在 Actions。新源码完整四配置与同轮严格汇总重验，保留原绿和全部失败；两份证据文档另以 `[skip ci]` 交回。不得重启已有无关运行。

## 返修复审已关闭，等待共同集成

返修受测源码 `0ee0bd0dcfa1b9646613d6b2a56e0a0aa49671a2`，文档 HEAD `fc40e84746c11d32d4029b8b284b697343f6835b`，远端分支与其一致。文档 HEAD 与受测源码只差两份证据文档。

root 已重读生产差异及真实故障用例：`request_close` 在线程创建失败后持 handle mutex 恢复有效状态并返回 MEMORY，不再同步执行 closer；完整请求、队列和连接保留，终止回调已结束请求时不会复活。`drop_conn` 清空旧连接指针后释放 handle mutex，等待 `spd_close` 及旧事件线程结束，最后才释放全局名额；等待期间不持回调需要的锁。

新故障测试通过 RLIMIT_NPROC 触发实际 pthread_create/EAGAIN，核对活动请求、队列、连接、名额和 destroy/BUSY；关闭边界门控中，第二 owner 无法取得名额，旧关闭结束后新 owner 才能连接并完成请求。新增17个具名检查保留在固定清单中。

[run 40143498768](https://github.com/NoGod3524/EXReader/actions/runs/40143498768) / attempt 1 的 Ubuntu 22.04／24.04 release／ASan 四配置各 `155 pass / 0 fail / 0 skip / 0 other`。作业为 `121019956628`、`121019956661`、`121019956767`、`121019956685`，严格汇总 `121025198294` 明确 `accepted=True jobs=4 cases=620`。root 已直接核对这五份云端日志及汇总协议源码。

两个原关闭缺口已修复；本包复审关闭，等待共同源码集成。旧源码、原绿和失败记录保留。该结论限 Linux 模块及其声明的真实 daemon／null 音频出口，不授予宿主 UI、真人听感、其它系统或完整产品。
