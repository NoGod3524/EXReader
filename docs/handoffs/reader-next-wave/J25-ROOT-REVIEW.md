# J25 root复审返修

受审源码 `db7f13a323db4ea633db7660e20c92098e9c1bb4`，证据HEAD `4fb7f326593c7148b1c783741d42a498c312fb43`，run `40135232301` 的三个作业success。当前不授予共同源码合入；下列结论来自源码复读，须由新Actions证据验证。

## 配置路径被替换成不可用的占位符

`sanitize_stage.py` 对实际六份 `.pc` 的绝对前缀调用通用 `distlib.rewrite_occurrences()`，后者写入 `<path:键>`。这能清除被扫描字节，却无法在搬迁后指向实际库/头文件。CMake消费者成功没有验证pkg-config元数据；可逆和幂等也不证明这些配置可用。

请对功能配置采用真正可重定位的路径（例如按每个 `.pc` 所在位置计算 `${pcfiledir}` 相对prefix），保留库名、依赖、flags和安装布局；不把路径抹成不存在的占位符。用实际被搬迁的所有 `.pc`，由真实pkg-config/pkgconf读取变量，确认include/lib目录存在且位于新prefix，并至少编译链接一个实际安装组件消费者。保留原文件/修改审计、旧扫描负例、CMake C/C++、九格式、闭包与同轮严格汇总。SDK保护树不改。

## 解包上限在分配之后检查

`distlib.read_zip()` 先 `archive.read(info)` 得到完整解压payload，之后才累计total并检查1GiB上限。一个超过上限的单项已经在拒绝之前完成解压和大分配，硬上限没有约束实际资源使用。

请在读取前核对条目数量、单项声明大小与累计声明大小，再用有界流式读取/hash校验实际字节，拒绝重复/不安全成员。增加“声明超额且不进入内容读取”和实际截断/篡改的具名负例；不要在Actions分配超大内存来制造测试。保持现有真实发行归档仍完整通过。

## 汇总未要求全部具名结果

`aggregate_artifacts.py` 的 `summary-named-results-pass` 只要求results非空且所有status为pass；删除一个乃至保留唯一一个pass仍满足该条件。请复用 `verify_distribution.REQUIRED_RESULTS` 及固定必需负例名单，拒绝缺项、重复、未知/替代名称和错误状态，保留同源/run/attempt及真实ZIP重算。增加对真实报告形状的缺项/重复/替代名等拒绝回归。

原owner唯一修改原工作树/原分支与本包白名单。所有构建、测试、语法、夹具与工件解析仅Actions；新源码完整重验，保留旧绿和失败，两份证据文档单独 `[skip ci]`。
