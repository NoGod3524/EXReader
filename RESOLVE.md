# 通用收尾：解冲突 + 补 API 文档 + 推送（PR #113）

## 你的任务

让 PR #113 变成 CI 可绿的状态。两件事，按需做：
# 通用收尾：解冲突 + 补 API 文档 + 推送（PR #127）

## 你的任务

让 PR #127 变成 CI 可绿的状态。两件事，按需做：
# 通用收尾：解冲突 + 补 API 文档 + 推送（PR #107）
让 PR #107 变成 CI 可绿的状态。两件事，按需做：
# 通用收尾：解冲突 + 补 API 文档 + 推送（PR #129）

## 你的任务

让 PR #129 变成 CI 可绿的状态。两件事，按需做：

### A) 解冲突（它现在 `Cannot update PR branch due to conflicts`）

```powershell
cd C:\Users\Oscar\Documents\Codex\EXReader-resolve-113-20261111
cd C:\Users\Oscar\Documents\Codex\EXReader-fix-127-20261111
cd C:\Users\Oscar\Documents\Codex\EXReader-resolve-107-20261111
cd C:\Users\Oscar\Documents\Codex\EXReader-fix-129-20261111
git fetch origin main
git merge origin/main
```

**冲突处理原则：取并集，不二选一。** 本仓库已因为"取一边"损失过工作。

- 报告/日志文件（`OUT*.txt`、`*-OUT.txt`）：两侧内容都保留，追加即可
- `CMakeLists.txt`、`tools/layers.json`：两边新增都留
- 源码：功能都保留；若有语义冲突，以"两侧测试都通过"为准

### B) 补 API 文档（若 CI 报 `sdk-doc-coverage`）

门禁在 `tools/check_sdk_docs.py`，规则：

```
include/**/*.h 里每个 EXR_API 函数，必须在 docs/API.md 里有 "### `exr_xxx`" 条目
条目里六个标签一个都不能少：**签名** **ABI** **参数** **返回与失败** **线程** **所有权**
**签名** 必须与头文件里的声明逐字符一致
```

先跑一遍看缺哪些：

```powershell
python -X utf8 tools\check_sdk_docs.py
```

按报错的 `undocumented functions: [...]` 逐个补。**签名从头文件复制，不要手打。**
新加的 API 一律 **ABI**: `实验`。

## 硬约束

```
❌ 不许改 tools/check_sdk_docs.py（检查本身不许放宽）
❌ 不许改 tests/check_reading_release.py（SHA256 必须仍是 6eb22a30…）
❌ 不许重排 tools/version_literal_exceptions.json（保持 indent=2）
❌ 不许启动 EXReader.exe 或任何 GUI、不许 SendInput、不许改系统设置
✅ 新增 src/*.h 必须在 tools/layers.json 登记
✅ 提交信息不得出现 CI 跳过标记
```

## 完成标准

```powershell
# 1. 冲突清零
git status --porcelain          # 无 U 标记
# 2. 文档门禁通过
python -X utf8 tools\check_sdk_docs.py    # exit=0
# 3. 推送
git push origin HEAD:claude/review-cleanup-20261109
git push origin HEAD:codex/large-book-2-20261110
git push origin HEAD:codex/artifact-signing-20261109
git push origin HEAD:codex/opds-catalog-20261110
```

**不要合并 PR，不要动 main。** 推完就停，主控会接着合。

## 报告

写进 `RESOLVE-OUT.txt`：

```
① 冲突文件清单与解决方式（每个文件一句话）
② 补了哪些 API 文档（函数名列表 + 各自的 ABI 分类）
③ check_sdk_docs.py 的 exit code 与最后三行输出
④ 还有没有别的失败项（列出 CI 里看到的名字）
```

