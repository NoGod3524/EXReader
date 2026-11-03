# 第 7 步：零 CI 证伪

检查对象：已推送的 `8ce084eb` 工作树；本地 Windows / Git Bash，CMake 4.4.2。没有重跑 CI，没有重新构建 SDK 或产品。
这些命令读取本地文件，不能冒充已销毁的 macOS runner 现场；CI 的 provider CMakeCache 不在已上传 ZIP 中。

## 原样结果

`01-configure-paths.log`：

```text
61:          cmake -S extras/sqlite-provider -B build/sdk-provider -DCMAKE_BUILD_TYPE=Release \
69:          cmake -S . -B build/sdk-core -DCMAKE_BUILD_TYPE=Release \
77:          cmake -S apps/reader/store/native -B build/sdk-catalog -DCMAKE_BUILD_TYPE=Release \
86:          cmake -S extras/sqlite-provider/integration -B build/sdk-integration \
```

第 7 步读取 `build/sdk-provider/CMakeCache.txt`，与 provider 的配置目录一致，未发现路径不一致。
`02-actual-read-path.log` 记录原样提取和非空检查，随后打印：

```text
got=[]
test_rc=1
```

为打印空值，本地诊断 shell 未启用 `-e`；原 CI 的 `bash -e` 在该非空检查失败时会直接退出。诊断没有调用检查器。
`03-all-caches.log` 保留 `find build -name CMakeCache.txt` 的所有 9 个路径；随后在所有缓存 grep 目标键，没有匹配，grep 返回 1。
本地 provider 已安装并测试，但曾使用 `FETCHCONTENT_SOURCE_DIR_EXREADER_SQLITE_SOURCE` override，因此另加不带 override 的独立实验核对。

## 第四种结果：MakeAvailable 成功，但普通变量不在缓存

`probe-CMakeLists.txt` 使用同一个 FetchContent 名称、同一份 hash 匹配的 SQLite ZIP，执行 Declare + MakeAvailable；仅把 URL 换成本地已验证归档，未设置 source override，未编译代码。
`04-fetchcontent-probe.log` 原样输出：

```text
-- MakeAvailable completed
-- normal_SOURCE_DIR=[C:/Users/Oscar/.codex/tmp/exr-fc001-20261103/_deps/exreader_sqlite_source-src]
-- sqlite3.c exists=YES
-- SOURCE_DIR_cache_key=NO
```

这反证“Declare + MakeAvailable 必然生成同名 SOURCE_DIR 缓存键”。普通变量有值、源已展开，并不保证 CMakeCache 里有该键；`_deps/.../sqlite3.c.o` 构建日志同样不能证明缓存键存在。
probe 缓存及原始实验源码已保留。首次实验遇到 Windows 长路径和本地 file URL 表达问题，原始失败日志也保留；采用短输出目录和普通本地归档路径后配置成功。

结论：已排除 workflow 字面路径不一致；本地已复现“正确缓存路径 + 缺普通变量对应缓存键 → got 为空 → 裸 test 返回 1”的 harness 缺陷。
这属于 P 的缓存接口假设问题，不是 MakeAvailable 未执行，也不能据此断言检查器放行了内嵌 SQLite。
CI 现场的同一根因仍缺 provider cache 直接证明。真实负例尚未验证，继续作为 R 前阻断项；不降为普通 open item，不关闭完整负例验收。

P 的两条强制规则及复用范式见 `../ci-hygiene-CI-ADMISSION-001/P_CI_HYGIENE.md`。

## 行尾与改动边界

review.md 统一恢复 LF；证据目录新增 `*.md text eol=lf`，让文档遵循仓库根规则。原始日志及其他原始工件字节保持不变。
不改 catalog、workflow、检查器、测试断言、SDK 版本、默认分支；本次不触发 CI。
