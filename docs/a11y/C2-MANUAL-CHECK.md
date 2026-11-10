# C2 人工验收交接

本轮仅编译、控制台测试和静态校验。下列项目全部待主控安排用户在场后确认，不能记为已通过。

自动脚本不启动应用、不附着 UIA、不模拟输入、不更改系统设置。

- [ ] **外部 UIA**：需要真实窗口，因为 UIA 必须读取运行中的控件树与 provider。用户在场时手动打开应用和有文字的书页，从独立 UIA 客户端检查 Name、HelpText、角色、可用状态、TextPattern/DocumentRange、ValuePattern、选择范围；翻页、选择、翻章和开关面板时核对 TextChanged、TextSelectionChanged、StructureChanged。封面无文本须单独记录。

- [ ] **Tab 与焦点恢复**：需要真实窗口，因为实际焦点受可见性、启用状态和消息循环影响。人工按 Tab/Shift+Tab 检查 返回书架→全文搜索→正文→目录→设置 循环；分别打开搜索、目录、设置检查子控件顺序，Esc 关闭后焦点回到正文，禁用控件不能困住焦点。

- [ ] **焦点环**：需要真实窗口，因为静态 token 不能证明实际绘制、裁切与缩放。人工检查目录、设置、搜索和各设置按钮的焦点环，在用户当前 DPI 下应清晰完整；正文聚焦时无额外页面边框。

- [ ] **对比度观感**：需要真实窗口，因为截图和颜色配置不能证明用户屏幕上的可读性。先在当前主题检查文字、选区、焦点环、禁用控件和面板；高对比度仅由用户本人决定是否切换并操作，检查完成由用户恢复。自动验收不得切换主题、高对比度、DPI 或输入法。

- [ ] **同步宿主呈现**：需要真实窗口，因为控制台只能证明同步数据和状态码。人工检查设置→云同步入口、错误和离线队列的文字、后台完成后的状态刷新及保存后密码框清空。

- [ ] **OPDS 宿主呈现**：需要真实窗口，因为控制台不能验证面板交互和进度呈现。人工检查书源入口、搜索/翻页/返回、下载进度与取消、下载后导入并打开、超时错误显示。

## 复用的旧截图

来源提交 `5cdc779c`，目录 `docs/ui/evidence/a11y-uia-20261110/run1`。仅作为历史证据，不代表当前构建已完成人工验收。

- [01-text-page.png](../ui/evidence/a11y-uia-20261110/reused/01-text-page.png) · SHA-256 `901d873f84c981095fb2b67da4ac0c47d23cffc2b6ded661a03e282b4f36c4db`
- [03-toc-button-focused.png](../ui/evidence/a11y-uia-20261110/reused/03-toc-button-focused.png) · SHA-256 `caa67c8b62818c1e2284b046510627dbc17dfc7e221ba8e6b7e2549f2aea620b`
- [04-settings-button-focused.png](../ui/evidence/a11y-uia-20261110/reused/04-settings-button-focused.png) · SHA-256 `3e275110b43c79dd837e78754099adaa6a72c000512416bfef081f3e4d340deb`
- [05-toc-open.png](../ui/evidence/a11y-uia-20261110/reused/05-toc-open.png) · SHA-256 `28fb2711346c390bc99ef5fc443662f1c537782c00e0ea617c3413ca521afd09`
- [06-settings-open.png](../ui/evidence/a11y-uia-20261110/reused/06-settings-open.png) · SHA-256 `1444637a4dbc94a068a51e7afa011dd63289e0ebadc4b94b557f1fd8065a1f8c`
- [08-high-contrast-text.png](../ui/evidence/a11y-uia-20261110/reused/08-high-contrast-text.png) · SHA-256 `6a1c1e01d74d944e6962b9ae1451e264dfdf537daea852e27a8a23242406aecc`
- [09-high-contrast-toc-focus.png](../ui/evidence/a11y-uia-20261110/reused/09-high-contrast-toc-focus.png) · SHA-256 `051fd257c427b23b5dd1f89123fc6917060074eebe4c4ab479cb21e9f8340169`
- [10-high-contrast-toc-open.png](../ui/evidence/a11y-uia-20261110/reused/10-high-contrast-toc-open.png) · SHA-256 `051fd257c427b23b5dd1f89123fc6917060074eebe4c4ab479cb21e9f8340169`
- [11-high-contrast-settings-open.png](../ui/evidence/a11y-uia-20261110/reused/11-high-contrast-settings-open.png) · SHA-256 `af77f1c8bd13bdfa48c6aaba3b9e15fba230d062bf18b42a77c88d143f6a0698`
