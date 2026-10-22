# H9 Apple 有界 EPUB 候选

本包在 `fd210224a4eba206762c08de435a5e9edfdf2a90` 上准备 Apple 局部实现；最终 SDK K 和 Windows pilot 尚未授予。
候选未获验收。构建、Swift 编译、夹具生成、测试与证据计算只在 GitHub Actions 执行。

## 路径

新 EPUB 通过 FileHandle 随机 source 导入 SQLite；publication 从书库 source 打开，保持稳定取消上下文。
每章使用 bounded pager，保留两页/8 MiB 缓存与4个/2 MiB检查点，解析工作区16 MiB、窗口16 KiB。
UI只拥有当前页图像和最多2 MiB页文字，不保留 EPUB 章全文或全书快照。
part/path、章内 UTF-8 point 和同章 notes 使用 schema7 公共 API；旧memory模式仍走原global记录。
同 owner 更新保留source；外部SQL提交的source失效遵循SDK契约，失败不当作EOF。

前后翻页跨reading-order章节，重复path由part区分。新进度重开只将FOUND视作精确恢复；
未匹配/歧义保存记录保持原样，界面明确显示从章首浏览，显式用户移动后才保存新点。
异章notes先显示待定位，跳转时建立目标章pager并实际解析，只有FOUND发布页面。
选择上下文包含book/frame/part/path/章内起点；原生选文UI和原始UTF-8转换保留。

## 验收契约

原12 UI/61具名步骤/46附件、21legacy、21SDK桥接、18Model保持。
原Model数字回滚回归明确使用公开memory import准备legacy书，继续验证真正global写入。
新增三平台第13个UI用例、6步骤、3截图，覆盖source导入、跨章、notes跳转、重开、前翻。
新增macOS安装SDK消费者13项：source/模式/取消、稳定取消owner、重复path、跨章、notesCRUD、
字号/窗口/重开、歧义拒绝、非法路由、原重复样本歧义、旧memory兼容、50MiB单章后段读取。
长章范围为首屏渲染与后段文字/章末point，不宣称全章分页或全局性能门槛。

原重复Sample保留为Repeated.epub负例；正例Sample使用独立编号语料，避免把真实歧义冒充精确匹配。
严格汇总继续绑定八作业/八工件同run/source/attempt，数据库必须schema7，逐书核marker/part/path/point/notes命名域，
host-state升级schema2并与SQL逐项比较。新增缺marker、缺point、错误路由/global冒充/错误note owner等拒绝用例。
进程RSS由独立消费者子进程的high-water采集，包含字体、accepted/candidate frame和分配器；编译器排除。

真机安装/签名、VoiceOver、全格式有界化与产品完成仍独立跟踪。`complete_product=false`。
