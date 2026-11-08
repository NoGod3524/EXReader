# Linux 验收

当前：x86_64 `libexreader.so` 已从 ubuntu-22.04 CI 下载；389 个核心入口齐全，额外导出 2,410 个。GNU nm 与本轮解析器独立读数一致（2,799 个已定义动态符号）。本机无 WSL 发行版、无 Docker，以下 Linux 加载/功能命令尚未本地执行。

## 安装与加载（Linux Bash）

```sh
set -e
export SDK="$PWD/downloads/EXReader-C-Linux"
file "$SDK/lib/libexreader.so"
ldd "$SDK/lib/libexreader.so"  # 必须无 not found；CI 产物不是 musl/Alpine 包
python3 tools/abi/check_exports.py "$SDK/lib/libexreader.so" --allow-extra
python3 tools/abi/prepare_smoke.py build/smoke
cmake -S tools/abi -B build/probe-linux -DCMAKE_BUILD_TYPE=Release -DEXR_SDK="$SDK"
cmake --build build/probe-linux --parallel 4
mkdir -p build/linux-acceptance
LD_LIBRARY_PATH="$SDK/lib" ./build/probe-linux/exreader-acceptance \
  build/smoke/smoke.epub build/smoke/font.otf build/linux-acceptance \
  > build/linux-acceptance/acceptance.log 2>&1
cat build/linux-acceptance/acceptance.log
# 完整桌面宿主还需要 GTK3 开发包和桌面显示服务器；无显示服务器只执行上面的 SDK 探针。
python3 tools/build_linux_host.py --sdk "$SDK" --output build/linux-host
find build/linux-host -maxdepth 2 -type f -perm -111 -print
```

保留完整 SDK 的库别名（例如 `libexreader.so.1`），应用可用 `$ORIGIN` rpath 或上面的进程级 `LD_LIBRARY_PATH`；无需改系统 `/usr/lib`。若自己构建，命令见 [artifacts.json](../../evidence/platforms-20261108/artifacts.json)，随后 `ctest --test-dir build/linux --output-on-failure`。发行版的 libc/CPU 指令集需要与构建目标匹配。

## 五项最小功能验收

以下五项均由同一次 `exreader-acceptance` 执行；任何条件不满足返回非零。PNG 是实际引擎渲染产物，不是界面示意图。各端使用相同 EPUB 和固定字体；探针验证 SDK 功能，原生阅读器的触控、菜单、无障碍和平台持久化仍需另做装机验收。

1. [ ] **打开一本书**：`acceptance.log` 必须出现 `PASS open status=0 pages=`，页数至少 20；打开 `page-01.png` 可见英文正文。这里使用生成的一章 EPUB，避免封面/版权页不足 20 页影响验证；19 本真书属于独立回归。
2. [ ] **连续翻 20 页**：必须出现 `PASS turn status=0 rendered=20 last=page-20.png`；`page-01.png` 至 `page-20.png` 共 20 个文件，均可打开。它验证连续页渲染和读取；触控翻页与应用帧率不在此探针范围内。
3. [ ] **搜索一个词**：查询 `deliveryneedle`，必须出现 `PASS search status=0 found=1 part=0 offset=0 length=14`；这是 `exr_publication_search` 的实际返回值，不是用字符串查找模拟。
4. [ ] **修改字号**：必须出现 `PASS fontsize status=0 from=18 to=24 pages_before=... pages_after=...`，after 大于 before；`font-24.png` 字号大于 `page-01.png`，首页结束偏移减少。探针会同时断言这些值。
5. [ ] **添加一个高亮**：必须出现 `PASS highlight status=0 stored=1 resolved=FOUND changed_pixels=` 且值大于 0；`highlight.json` 为导出的 W3C 标注，探针写入、关闭、重新读入并解析；锚点恢复到相同 UTF-8 范围。`highlight.png` 的第一个 `deliveryneedle` 有黄色背景。绘制由参考宿主按引擎字形坐标完成，不能据此宣称产品菜单已验收。

最后必须出现 `PASS acceptance checks=5`。保留完整日志、22 张 PNG（20 页 + 字号 + 高亮）、标注 JSON、设备/模拟器型号、OS 版本、实际库 SHA-256 和命令；失败时保留输出，不能把本页勾选项当成已通过记录。

## 已知限制

- 尚未在本地 Linux 进程中 dlopen；native CI desktop (ubuntu-22.04) 已成功，作业快照见 [ci-jobs.json](../../evidence/platforms-20261108/ci-jobs.json)。
- 此五项不要求 X11/Wayland，因此可用于容器/SSH；GTK 窗口、输入法和真实交互截图仍待桌面装机。
- 核心接口完整不等于严格同集合通过；内部/第三方导出收敛需要后续主构建修改。
