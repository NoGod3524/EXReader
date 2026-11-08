# Windows 验收

当前：已产出 x86_64 `exreader.dll`、`EXReader.exe`；核心严格 ABI **389/389**。本机共用探针已通过 5/5，ctest 211/211。DLL 的两个名字字节相同：FFI 可用 `exreader.dll`，现有 `EXReader.exe` 实际导入 `libexreader.dll`，交付时必须带上后者。

## 安装与加载（PowerShell）

在仓库根目录执行。`$Delivery` 指向仓库外的产物目录；其他机器先按 [README 构建/取件](README.md) 准备 SDK 和产物。

```powershell
$Delivery = (Resolve-Path '../tmp/platform-delivery-20261108/delivery').Path
$Sdk = (Resolve-Path '../tmp/platform-delivery-20261108/windows-sdk').Path
python tools/abi/check_exports.py "$Delivery/windows/x86_64/exreader.dll"
if ($LASTEXITCODE -ne 0) { throw 'ABI failed' }
# 现有桌面产品：复制整个目录；不要只复制 EXE。
& "$Delivery/windows/x86_64/EXReader.exe"
# CMake 消费完整安装 SDK，编译本轮共用探针。
python tools/abi/prepare_smoke.py build/smoke
cmake -S tools/abi -B build/probe-windows -G Ninja "-DEXR_SDK=$Sdk"
cmake --build build/probe-windows --config Release --parallel 4
Copy-Item "$Sdk/bin/*.dll" build/probe-windows
$Out = (New-Item -ItemType Directory -Force build/windows-acceptance).FullName
& ./build/probe-windows/exreader-acceptance.exe build/smoke/smoke.epub build/smoke/font.otf $Out > "$Out/acceptance.log" 2>&1
if ($LASTEXITCODE -ne 0) { Get-Content "$Out/acceptance.log"; throw 'Acceptance failed' }
Get-Content "$Out/acceptance.log"
```

MSVC 多配置构建把 EXE/DLL 放到 `build/probe-windows/Release`；上面是本轮使用的 MinGW + Ninja 单配置布局。生成输入默认复用 `tools/host_font.py` 下载并校验固定 OFL 字体；离线可传 `--font <已有字体>`，同时记录其哈希。新 SDK 的构建命令见 [产物元数据](../../evidence/platforms-20261108/artifacts.json)。

## 五项最小功能验收

以下五项均由同一次 `exreader-acceptance` 执行；任何条件不满足返回非零。PNG 是实际引擎渲染产物，不是界面示意图。各端使用相同 EPUB 和固定字体；探针验证 SDK 功能，原生阅读器的触控、菜单、无障碍和平台持久化仍需另做装机验收。

1. [ ] **打开一本书**：`acceptance.log` 必须出现 `PASS open status=0 pages=`，页数至少 20；打开 `page-01.png` 可见英文正文。这里使用生成的一章 EPUB，避免封面/版权页不足 20 页影响验证；19 本真书属于独立回归。
2. [ ] **连续翻 20 页**：必须出现 `PASS turn status=0 rendered=20 last=page-20.png`；`page-01.png` 至 `page-20.png` 共 20 个文件，均可打开。它验证连续页渲染和读取；触控翻页与应用帧率不在此探针范围内。
3. [ ] **搜索一个词**：查询 `deliveryneedle`，必须出现 `PASS search status=0 found=1 part=0 offset=0 length=14`；这是 `exr_publication_search` 的实际返回值，不是用字符串查找模拟。
4. [ ] **修改字号**：必须出现 `PASS fontsize status=0 from=18 to=24 pages_before=... pages_after=...`，after 大于 before；`font-24.png` 字号大于 `page-01.png`，首页结束偏移减少。探针会同时断言这些值。
5. [ ] **添加一个高亮**：必须出现 `PASS highlight status=0 stored=1 resolved=FOUND changed_pixels=` 且值大于 0；`highlight.json` 为导出的 W3C 标注，探针写入、关闭、重新读入并解析；锚点恢复到相同 UTF-8 范围。`highlight.png` 的第一个 `deliveryneedle` 有黄色背景。绘制由参考宿主按引擎字形坐标完成，不能据此宣称产品菜单已验收。

最后必须出现 `PASS acceptance checks=5`。保留完整日志、22 张 PNG（20 页 + 字号 + 高亮）、标注 JSON、设备/模拟器型号、OS 版本、实际库 SHA-256 和命令；失败时保留输出，不能把本页勾选项当成已通过记录。

## 已知限制和证据

- 已有 Windows DLL 为关闭部分可选编解码器的配置，公开符号仍齐全；不支持的格式返回 `EXR_UNSUPPORTED`。不能用这五项代表所有音频/图片格式通过。
- 共用探针的高亮是 SDK/参考绘制验收；真实 Windows 菜单与重开恢复的既有验收在 [ANNOTATIONS-ACCEPTANCE.md](../ui/ANNOTATIONS-ACCEPTANCE.md)。
- 本轮记录：[windows-acceptance.txt](../../evidence/platforms-20261108/windows-acceptance.txt)、[windows-exports.json](../../evidence/platforms-20261108/windows-exports.json)、[ctest.txt](../../evidence/platforms-20261108/ctest.txt)。图像和二进制留在仓库外，仅提交哈希。
