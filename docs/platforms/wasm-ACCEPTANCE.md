# Web / WASM 验收边界

**不支持；当前无法产出。** 本仓库没有 Emscripten 目标、浏览器宿主、JS 绑定、浏览器打包与验收流程；文件访问和原生音频适配尚未接入浏览器环境。WASM 的线性内存/指针布局也不能直接沿用 Windows DLL 的装载方法。本轮明确不做移植，因此不提供 `.wasm`、npm 包或声称可安装的网页。

## 状态检查（任意 Python 3.11+ 主机）

```sh
python tools/abi/platform_status.py --json > platform-status.json
python -c "import json; r=[r for r in json.load(open('platform-status.json',encoding='utf-8'))['artifacts'] if r['platform']=='WASM'][0]; assert r['status']=='当前无法产' and not r['exists'] and r['observed_sha256'] is None; print('PASS wasm unsupported; no fabricated artifact')"
```

输出是支持范围的负向验收，**不是 Web 功能通过**。没有可用的安装/加载命令；`python -m http.server` 只能托管文件，不能把原生 SDK 转成 WASM。

## 五项功能条目（均不适用，不得勾成已通过）

1. [ ] **打开一本书**：N/A，不存在浏览器宿主和文件选择桥。判定：状态 JSON 中 `platform=WASM`、`exists=false`、`path=null`；没有“打开成功”日志或截图。
2. [ ] **翻 20 页**：N/A，无 WASM 分页/渲染 consumer。判定：没有 Web `page-01.png` 至 `page-20.png`、没有 `PASS turn` 记录；原生 PNG 不算浏览器证据。
3. [ ] **搜索一个词**：N/A，无 JS/wasm 搜索入口。判定：没有浏览器运行返回值；原生 `exr_publication_search` 的 389 符号契约不能证明 JS API 存在。
4. [ ] **修改字号**：N/A，无浏览器字体资源加载和画布宿主。判定：没有 Web 的 18→24 输出/截图，不能用 CSS 改页面文字替代引擎重排。
5. [ ] **添加高亮**：N/A，无浏览器选择、绘制和持久化适配。判定：没有 Web 高亮 JSON/截图；其他平台标注不算 Web 操作。

## 后续实现才可启用的门槛

提供真实 Emscripten 构建、JS 入口、浏览器字体/文件/存储适配、确定的包安装命令，并在至少一种浏览器运行同样五项流程后，才更新支持状态。届时应另定义 wasm32 的调用/内存契约，不能伪造 C DLL 导出表通过。
