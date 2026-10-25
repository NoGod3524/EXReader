# J14 root复审关闭，宿主接线待集成

独立分支 `codex/reader-library-health-review` 从原证据HEAD `71f271eb48b2c15f1be18be6fc140a620163cf82` 开始，不修改外部交付树。

复读公共头、扫描器、取消/进度/访问回调、原安装消费者和工件认证器后，修复两处边界：初次取消回调发生在active置位前，可再次进入step或destroy；最后一次read进度请求取消后，原逻辑仍可能推进游标并交付healthy行。现在先设置active并通过统一出口释放；观察结束后、游标推进前再轮询取消。

新增实际消费者回归在取消回调内逐次尝试step/destroy并要求REENTRY；仅在最终read进度请求取消，要求零交付与逐字不变游标，再使用该游标恢复完成。原2202行、分批重放、跨线程、源失效、16MiB有界读取、C++安装消费者和只读数据库断言保留。严格工件认证另核原始新增用例、ZIP成员唯一、工件有效期与真实两个消费者的字节/SHA。

tested source `10b038a55fabea493e3ef858d3171e8c65a54f0b` / run `40163483001` / attempt1 四作业全部success：Linux `121079688096`、Windows `121079688074`、macOS `121079687887`、strict `121080471739`。strict重新下载三个原ZIP，`problems=[]`，各2202行且共同摘要 `88c481146e90464229df4963b9d338a5d46e58d5a59ceaa83ddf4a2674035fce`。

最终证据HEAD `cac8ec718647afb99b66a9b3fdc8a968f83dd002` 与受测source仅两份证据docs不同。工件：Linux `12587327597` /8,555,484B /`sha256:c4b8a3bbea30be370ce33241e661f8e11af30cb9eb30d9767e8bb9f4e4999218`；Windows `12587710839` /5,813,353B /`sha256:ed65deee145795a0630a1d418a427df42add815537a9f5626e463df7e2eb93d3`；macOS `12587730399` /7,369,379B /`sha256:02d8f53f1faaa3a5e82d5ab114b247b2567e31bf2529ca9135714e35ab004da4`。均到期 `2027-01-23T04:52:42Z`。

原source `a600cf3d` 的详细测量、原失败与原工件继续保留在JSON中，明确归原source。当前仅授予三桌面包接口；正式宿主UI、用户可见修复操作、产品性能及六目标产品仍未授予。
