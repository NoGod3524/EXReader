# 确定性 provider 源目录交接

`extras/sqlite-provider/CMakeLists.txt` 在 MakeAvailable 后原样写出 `${CMAKE_BINARY_DIR}/provider-source.txt`。
workflow 读取 `build/sdk-provider/provider-source.txt`，不再解析 CMakeCache；文件缺失或为空时打印期望路径、实际为空及缓存候选路径，明确退出 1。
该文件纳入现有上传清单，供 R 候选轮保留配置来源。

本地仅重新配置 provider，确认生成文件非空且指向实际 sqlite3.c；原样 shell 读取通过，缺失/空文件两种诊断均以退出 1 通过核对。
原始输出在 `configure.log`、`read-source.log`、`missing.log`、`empty.log`；生成路径的内容已原样打印在 `read-source.log`。
没有编译、没有执行真实 Apple 控制、没有 CI；不能据此关闭负例验证。

**负例验证仍为 R 前阻断项，随 R 候选轮验证。**
本次未改检查器或测试断言、catalog、SDK 版本、默认分支；本提交只包含两处源码改动及本次四态输出与边界记录，提交信息包含 `[skip ci]`，不运行云端。

边界：本修复涉及 `extras/sqlite-provider/**` 与 `sdk-shared-sqlite-contract.yml`，二者都不在八项受保护树内，因此不扩大 R 候选的改动面。

四态退出码：正常读取 0；缺失 1；空文件 1；配置成功 0。

原始输出 SHA-256：

- `read-source.log`: `b09373c5dac522aede7fef8c3a08b7b495e31c7f181c2319dddacd6adca4e0b4`
- `missing.log`: `caea1c3d930f02582edfd3f0a33afeae38121ce16e3eefdd6207eadc49648719`
- `empty.log`: `caea1c3d930f02582edfd3f0a33afeae38121ce16e3eefdd6207eadc49648719`
- `configure.log`: `186cc054e0a3f7dc0d8b181bcb713d9d87538d3b7029dad437ed9cfc723b9d4b`
