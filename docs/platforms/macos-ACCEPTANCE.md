# macOS 验收

当前：ARM64 `libexreader.dylib` 已从 native CI 下载；389 个核心入口齐全，但额外 2,410 个导出，严格同集合未通过。macos-15 的实际产物是 ARM64；x86_64 **待 CI 产物**。本机 Windows 无 Apple SDK，未执行 macOS 装机步骤。

## 安装与加载（macOS Bash）

```sh
set -e
export SDK="$PWD/downloads/EXReader-C-macOS"
file "$SDK/lib/libexreader.dylib"
lipo -archs "$SDK/lib/libexreader.dylib"  # 本轮应为 arm64
python3 tools/abi/check_exports.py "$SDK/lib/libexreader.dylib" --allow-extra
python3 tools/abi/prepare_smoke.py build/smoke
cmake -S tools/abi -B build/probe-macos -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DEXR_SDK="$SDK"
cmake --build build/probe-macos --parallel 4
mkdir -p build/macos-acceptance
DYLD_LIBRARY_PATH="$SDK/lib" ./build/probe-macos/exreader-acceptance \
  build/smoke/smoke.epub build/smoke/font.otf build/macos-acceptance \
  > build/macos-acceptance/acceptance.log 2>&1
cat build/macos-acceptance/acceptance.log
# 可选：安装完整原生宿主，保持 bundle 内库和资源的布局。
python3 tools/build_apple_product.py --sdk "$SDK" --target macos --build build/apple-products
python3 tools/build_apple_host.py --sdk "$SDK" --platform macos --output build/macos-host
open build/macos-host/EXReader.app
python3 tools/check_apple_host.py --bundle build/macos-host/EXReader.app --device macos --output build/macos-host-check
```

完整 SDK 中的版本名/链接名需一起保留，尤其 `libexreader.1.dylib`。仅复制顶层别名可能导致 `dyld: Library not loaded`。若宿主内含动态库，用 `otool -L` 保存依赖，按自身分发方式签名；本轮不提供公证/签名安装包。

## 五项最小功能验收

以下五项均由同一次 `exreader-acceptance` 执行；任何条件不满足返回非零。PNG 是实际引擎渲染产物，不是界面示意图。各端使用相同 EPUB 和固定字体；探针验证 SDK 功能，原生阅读器的触控、菜单、无障碍和平台持久化仍需另做装机验收。

1. [ ] **打开一本书**：`acceptance.log` 必须出现 `PASS open status=0 pages=`，页数至少 20；打开 `page-01.png` 可见英文正文。这里使用生成的一章 EPUB，避免封面/版权页不足 20 页影响验证；19 本真书属于独立回归。
2. [ ] **连续翻 20 页**：必须出现 `PASS turn status=0 rendered=20 last=page-20.png`；`page-01.png` 至 `page-20.png` 共 20 个文件，均可打开。它验证连续页渲染和读取；触控翻页与应用帧率不在此探针范围内。
3. [ ] **搜索一个词**：查询 `deliveryneedle`，必须出现 `PASS search status=0 found=1 part=0 offset=0 length=14`；这是 `exr_publication_search` 的实际返回值，不是用字符串查找模拟。
4. [ ] **修改字号**：必须出现 `PASS fontsize status=0 from=18 to=24 pages_before=... pages_after=...`，after 大于 before；`font-24.png` 字号大于 `page-01.png`，首页结束偏移减少。探针会同时断言这些值。
5. [ ] **添加一个高亮**：必须出现 `PASS highlight status=0 stored=1 resolved=FOUND changed_pixels=` 且值大于 0；`highlight.json` 为导出的 W3C 标注，探针写入、关闭、重新读入并解析；锚点恢复到相同 UTF-8 范围。`highlight.png` 的第一个 `deliveryneedle` 有黄色背景。绘制由参考宿主按引擎字形坐标完成，不能据此宣称产品菜单已验收。

最后必须出现 `PASS acceptance checks=5`。保留完整日志、22 张 PNG（20 页 + 字号 + 高亮）、标注 JSON、设备/模拟器型号、OS 版本、实际库 SHA-256 和命令；失败时保留输出，不能把本页勾选项当成已通过记录。

## 已知限制

- 本轮只有离线产物与符号证据，没有在本机执行 dyld 或上述图像检查。
- Intel 构建需 macOS CI 上执行 `-DCMAKE_OSX_ARCHITECTURES=x86_64` 的完整构建；不能重命名 ARM64 库得到 Intel 库。可选通用库须两份构建后 `lipo -create`，并对每个切片校验；本轮没有通用库。
- reading-core/reading-library CI 绿色证明对应静态组件和消费测试；其 preset 设置 `EXR_BUILD_SHARED_COMPAT=OFF`，不证明聚合 dylib 已产出。本文 dylib 来自 native 作业。
