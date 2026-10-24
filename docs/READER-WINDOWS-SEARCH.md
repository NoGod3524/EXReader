# Windows 原生书内搜索候选

从 G1 共同源码证据 HEAD `3bcc6511` 独立接续，分支 `codex/reader-windows-search-ui`。
默认配置不加入搜索；Windows账号宿主显式开启 `EXR_READER_WINDOWS_SEARCH` 后消费安装后的原样F1。

次级“书内查找”入口和 Ctrl+F 打开原生编辑框/32行结果列表；查询、下一批、定位、取消和关闭在面板内可达。逐字区分大小写，不包含OCR。SDK/产品schema/wire/预算不改。

每个现有串行worker内创建F1句柄、恢复纯值cursor、取最多32项、复制selector、释放结果并关闭句柄，不跨OS线程保留F1句柄。UI仅持有自有副本。原书SHA-256、长度、格式、投影版本绑定到打开的阅读会话；扫描和定位重新核对，变化则拒绝并要求重新打开。定位先在独立SDK对象上得到FOUND，再交现有renderer路径重新验证；固定页只按稳定page ID解析，不使用页号/旧偏移回退。恰好满批后的空尾批保留上一批结果。

当前未编译、未运行，验证记录 `accepted=false`。首轮Actions只授予实际执行到的范围；初始TXT控件检查不替代EPUB/PDF、实时取消、错源、换书/关闭/重启、键盘及UIA完整验收。后续还须同源执行保留的Windows检查与严格工件认证。
