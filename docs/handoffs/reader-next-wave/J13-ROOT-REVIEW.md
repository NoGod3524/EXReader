# J13 root 初步复审：待修复

交回 HEAD `2d67b87830a1fabad602aef2ac7bdb3ef579190e`，原 owner 工作树未改。已初读公开契约、activation路径及平台文件实现；尚未完整复审，不关闭。

两处具体边界需 root 在独立分支修复和 Actions 复验：

1. `reader_account_profiles_verify_activation()` 只重新检查 `plan->private_directory` 的目录链，未检查 `plan->original_directory`。prepare后将真实originals目录换成符号链接或Windows junction时，三个路径字符串仍相同、private目录和library绑定也仍有效，verify可以遗漏该替换。应核两个派生目录的真实链，并补prepare后替换originals的真实负例，拒绝后证明目标未触碰。
2. 固定容量activation输入的 `plan->profile.profile_id[37]` 直接进入 `ap_uuid_valid()`，其内部使用无界`strlen`。该字段缺NUL时可能越过结构体；应在共享UUID校验函数限制最多37字节，补整个plan填充非NUL的真实内存检查负例。普通profile验证中的有界字符串检查不能保护直接verify入口。

另待进一步核清：profiles文档读取及锁文件打开在POSIX/Windows上会跟随末级链接，目录检查是否覆盖每个公开入口、是否符合声明的链接拒绝范围。不能只依靠prepare之前放置链接的旧检查来证明verify时的替换也被拒绝。

这些为源码定位，本地没有执行构建、测试或工件处理。原交回的云端通过仍归原source，尚不作为root复审通过或共同源码集成许可。
