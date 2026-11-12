# 续跑（第二版）：无窗口验收

> 上一轮你的会话因为**启动 GUI 被停掉**了。代码都在，改动已提交。
> 这一版只改一件事：**验收方式改成不开窗口**。

## 上一轮发生了什么（不是你的错，是我没写清规则）

你启动了 `EXReader.exe` 做宿主验收。那个窗口弹在用户的桌面上，
而且 C2 那路的对比度调色板让窗口变成黑黄高对比度外观 —— 用户以为电脑出问题了。

**现在这条是硬规则：**

```
❌ 启动 EXReader.exe 或任何 GUI 主程序
❌ SendInput / keybd_event / 模拟点击 / 模拟按键
❌ 改系统设置（主题、高对比度、DPI、输入法）
❌ 打开浏览器 / 用 CUA 类工具
✅ 控制台程序（不建窗口的 check_*.exe）
✅ ctest 的无窗口用例
✅ 直接读 .docx / .xml / .json 做断言
```

**如果某项验证非 GUI 不可 → 不要做。** 写清"需要真实窗口，因为……"，
把步骤列出来，交给主控决定。**不许自己开。**

## 你的任务：把验收改成无窗口

### 1. 先读你自己的进度文件

```
C:\Users\Oscar\Documents\Codex\EXReader-b2-opds-20261110\OPDS-OUT.txt
```

上面写着做到第几步、哪些验证还没跑。**接着干，不要推翻方案。**

### 2. 把 GUI 验收换成控制台等价物

你其实已经有大部分零件了，只是最后一步用了窗口：

**WebDAV（b1）**
- `examples/windows/mock_webdav.inc` —— 内存 WebDAV 服务器（真 TCP、Basic、ETag/If-Match、PROPFIND/GET/PUT/MKCOL）
- 目标：写一个**控制台驱动** `check_sync.c`，直接调用 `shell_sync` 的公开函数，
  对着 mock 服务器跑完 15 个场景（合并/首次上传/增量/冲突/墓碑/LWW/401/404/超时/403/重试/远端损坏/离线队列/重连/凭据）
- 已有 `windows-selection-sync` 这个 ctest 组，把它扩成完整覆盖即可

**OPDS（b2）**
- `examples/windows/check_shell_opds.c` —— 已经是控制台程序，对真实 Gutenberg 跑过
- 缺的是**本地慢服务器**场景（超时用例）：用 socket 写一个只 accept 不响应的本地服务，验证超时映射
- 把宿主 UI 的验收降级成"编译通过 + 控制台等价路径通过"，**不要启动 EXReader.exe**

**无障碍（c2）**
- UIA 的验证**必须**从外部读，但读的对象是正在运行的应用 → 这一项**不在本机做**
- 改成：① 静态断言（控件名称/HelpText 的注册代码路径）② 用 `/ui` 证据里已有的截图（不重拍）
③ 写一份 `docs/a11y/C2-MANUAL-CHECK.md`：列出需要在用户在场时人工确认的项（Tab 顺序、焦点环、对比度观感）
- `docs/ui/acceptance/check_a11y_c2.py` 改成"生成清单 + 校验静态配置"，不启动应用

### 3. 报告

```
① 上一轮做到哪（引用进度文件最后一行）
② 这一轮把哪些 GUI 验收换成了什么（逐条对照）
③ 验证结果：命令 + 实际输出
④ 仍然需要真实窗口的项：列清单，交主控
```

## 边界
- 工作树 `C:\Users\Oscar\Documents\Codex\EXReader-b2-opds-20261110`，分支 `codex/opds-catalog-20261110`
- 不改 `tests/check_reading_release.py`（字节 sha256 绑定）
- `tools/version_literal_exceptions.json` 保持 `indent=2`，只增删条目
- 新增 `src/*.h` 要在 `tools/layers.json` 登记
- 19 本真书：页数与哈希不变
- 完成后 push + 开 draft PR

