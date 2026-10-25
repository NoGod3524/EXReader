# J13 root 复审与修复

交回 HEAD `2d67b87830a1fabad602aef2ac7bdb3ef579190e`，原 owner 工作树未改。root在独立分支`codex/reader-account-profiles-review`修复下述明确activation边界。

两处具体边界及修复：

1. `reader_account_profiles_verify_activation()` 只重新检查 `plan->private_directory` 的目录链，未检查 `plan->original_directory`。prepare后将真实originals目录换成符号链接或Windows junction时，三个路径字符串仍相同、private目录和library绑定也仍有效，verify可以遗漏该替换。应核两个派生目录的真实链，并补prepare后替换originals的真实负例，拒绝后证明目标未触碰。
2. 固定容量activation输入的 `plan->profile.profile_id[37]` 直接进入 `ap_uuid_valid()`，其内部使用无界`strlen`。该字段缺NUL时可能越过结构体；应在共享UUID校验函数限制最多37字节，补整个plan填充非NUL的真实内存检查负例。普通profile验证中的有界字符串检查不能保护直接verify入口。

进一步核对公开README：真实目录链和绑定拒绝适用于两阶段activation；宿主使用其私有配置目录，不能跳过关闭旧session/SDK及最终verify。普通配置load仍采用普通文件路径读取，本次不授予通用文件系统沙箱能力。

最终受测source `10bbfe06669b57b11a35aa931402b0f846b3f7b7` / run `40155371601` / attempt1 四作业success；三平台各42项，原40项与两个新增真实负例全部通过。Linux `121055537573` 的ASan/UBSan实际执行非NUL堆plan，未报告内存或未定义行为错误；Windows `121055537450` 的真实junction替换同样拒绝且目标不变。macOS `121055537252` 及strict `121057196212` success，9个篡改报告负例拒绝，`problems=[]`。已只读核对这些云端日志，本地没有构建、运行测试或处理工件。

证据HEAD `a0746156b37db7cd750fb805899a616ef2c6a80f` 与受测源码仅差两份模块证据文档，旧交回记录保留。复审关闭，等待共同源码与宿主账号切换接入。
