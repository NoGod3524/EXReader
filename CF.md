# 把 PR #129 解到可合并（工作在这个 PR 自己的分支上）

## 你的分支（一字不改地在这里干）

```
工作树   C:\Users\Oscar\Documents\Codex\EXReader-b2-opds-20261110
分支     codex/opds-catalog-20261110          ← 这就是 PR #129 的 head 分支，已 track origin
```

**不许新建分支。** 上一轮九路就是因为建了新分支（`codex/fixNNN-*`），成果全落到 PR 看不见的地方，
后来靠主控手工 fast-forward 才搬回来。

## 现状

```
PR #129  mergeable = CONFLICTING
落后 main = 11 个提交
领先 main = 12 个提交（本 PR 的功能）
CI：因为 CONFLICTING，没有跑
```

## 要做的

### 1. 合并 main，解冲突

```powershell
cd C:\Users\Oscar\Documents\Codex\EXReader-b2-opds-20261110
git fetch origin main
git merge origin/main
```

**冲突处理原则：取并集，不二选一。** 本仓库已因为"取一边"损失过工作（#99、#124 都是教训）。

按文件类型：

| 文件 | 处理 |
|---|---|
| `OUT*.txt` / `*-OUT.txt` / `RESOLVE-OUT.txt` | 报告文件，**两侧内容都留**，只删冲突标记 |
| `CMakeLists.txt` / `cmake/modules.cmake` / `tools/layers.json` | 两边新增都留 |
| `examples/reader.c` / `shell_*.inc` | 功能都保留；语义冲突以"两侧测试都过"为准 |
| `src/**` | 同上；若有 API 形状冲突（同名结构体字段不同），**改名而不是删** |

### 2. 本地验证

```powershell
$bld = "C:\Users\Oscar\Documents\Codex\exr-build-cf129"
cmake -S C:\Users\Oscar\Documents\Codex\EXReader-b2-opds-20261110 -B $bld -G Ninja -DEXR_READER_WINDOWS_SHELL=ON `
  "-DFETCHCONTENT_SOURCE_DIR_MBEDTLS=C:/Users/Oscar/Documents/Codex/exr-deps/mbedtls-3.6.7"
cmake --build $bld -j 2
ctest --test-dir $bld -j 2 -E "^sdk-release$"
```

**`sdk-release` 在本机永远失败**（`LNK1181: lib\exreader.lib` 是 MSVC 导入库路径），纯净 main 上同样失败 ——
不是你的锅，不要为它改代码。

### 3. 推送

```powershell
git push origin HEAD:codex/opds-catalog-20261110
```

推完 CI 会自动跑。**不要合并 PR，不要动 main。**

## 硬约束

```
❌ 不许改 tests/check_reading_release.py（SHA256 应为 6eb22a30…）
❌ 不许重排 tools/version_literal_exceptions.json（保持 indent=2）
❌ 不许改 tools/check_ci_hygiene.py 的判定逻辑
❌ 不许开 GUI / SendInput / 改系统设置
❌ 不许新建分支
✅ 新增 src/*.h 必须在 tools/layers.json 登记
✅ 每完成一步追加写 OUT-CF.txt
```

## 交付

```
① 冲突文件清单 + 每个文件的解决方式（一句话）
② 本地 ctest 结果（通过数/总数，失败项名）
③ 推送后的 PR mergeable 状态
④ 还差什么（如果有）
```

