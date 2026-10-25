# iPhone / iPad 原始固定页记录独立宿主候选

状态：实现与Actions入口已准备，尚未授予iOS通过。独立分支 `codex/reader-apple-raw3-ios` 从Mac封存 `44eabdc86b3b84d986f81dbaf8cee92b1829cea8` 创建；共同MAX2主线不变。

SDK精确 `edddc463c06ed5731195cdb8f06b2df6dff7699e` /3.41.0/ABI1。raw七包精确沿Mac已通过家族；SDK与raw产品前缀分开安装，EXACT Config查询、C宏和Swift条件均显式，默认关闭。独立Ruby薄wrapper调用未修改原Xcode generator，为候选工程增加优先产品头/库路径与双宏；真实Mach-O/map要求唯一动态SDK、唯一产品SQLite、七raw provider，不嵌入第二SDK或旧reading resolver。

每个iPhone/iPad simulator先完整执行未修改原ReadingUITests七场景、原90秒wait和原夹具，再执行独立真实raw UI场景。同一8845B PDF（SHA256 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc`）通过实际导入、原生全选、实际记录动作产生点与非空NUL range；覆盖正文编辑、删除、显式源版本恢复、独立FOUND后的用户跳转、真实进程重开及提交两侧的原请求重试。旧OFF app实际留下v1/writer2 NUL失败请求，换装RAW app保持同一容器，原文件、ID、bootstrap、parents不变且仍拒绝；新RAW请求明确v2/anchor3。

review-only审计仅在实际owner队列读取已有SDK/catalog句柄、原wire和private文件；在原生产resolver本身完成时观察FOUND与复捕获，不额外打开SDK连接，不生成capture、不补wire、不写产品SQL。宏关闭不包含审计hook。实际simulator容器、原pending字节、实际程序、地图、全部xcresult/附件与逐文件hash在云端保留。

NULL和源v1/v2输入来自Mac真实通过run40196978163 / source15dab6b2 / attempt1 / 原ZIP12600789926（77,056,135B / SHA256 `92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5`）内operations profile的原始保留数据库。Actions认证ZIP与每个文件后，以只读SQLite读取原body BLOB/散列及完整父图，不重写wire；原件来自同ZIP登记的相同真实内容。既有账号UI通过真实匿名HTTPS HostAccountSession扫描256shard接收，再普通原件导入并检查typed NULL行没有导航/编辑动作；用实际v1/v2源记录执行UI编辑/删/恢复。测试CA仅装入隔离simulator信任，不关闭证书核验。

首轮范围仅iPhone/iPad simulator的实际raw记录UI、实际SDK owner及指定保留NULL原wire的原生HTTPS入站。完整移动同步、Android双向、真机、性能和整个产品仍独立验收。所有构建、语法检查、夹具、工件处理与测试均只在Actions运行。
