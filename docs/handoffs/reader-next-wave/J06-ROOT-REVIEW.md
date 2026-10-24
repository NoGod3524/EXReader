# J06 root源码复核：外链百分号转义

受检HEAD：`1fa410b75889606c46ec4658a4b46bf1caf2df9e`；受测实现：`e175a00fbf7f623993698a276e8f066c392ad061`。两者仅两份证据文档有差异，模块源码相同。原run `40123584995` 的模块验收记录保留；root尚未授予共同源码集成。

## 合入前修正

`apps/reader/link-policy/include/reader_link_policy.h` 将 `ENCODED_CONTROL` 定义为“%00 anywhere; other controls in path/host”；实现 `src/policy.c` 的 `external()` 却对整个scheme后的内容调用 `check_escapes(rest, rest_len, 1, ...)`，使路径中的 `%0A`、`%0D`、`%7F` 也通过该检查。例如 `https://example.com/%0A` 经后续authority校验后会成为 `NEEDS_HOST`，与公开契约不符。已有 `mailto:...?body=x%0D%0Ay` 正例属于query，不能通过删除这个正例来掩盖路径缺口。

同一公开头把坏UTF-8百分号转义列入 `BAD_ESCAPE`。内部路径通过 `check_path_bytes()` 验证解码UTF-8；内部fragment却只经 `check_escapes()` 检查十六进制和控制字节，`#a%FF` 因此进入 `INTERNAL`。这也需要实际负例与明确的一致契约。

建议保持包的现有职责：只补齐各URI组成部分的转义验证，保留原文及SDK解析归属，不新增URL/书籍解析器，不自动打开链接。至少增加上述path/fragment负例、合法UTF-8 fragment、原有mailto query正例；在原三平台安装消费者和同轮ZIP认证中整轮重验，保留旧失败与旧绿的源码身份。

此记录来自源码分支推导，本地未构建或运行测试；修补后的实际行为必须由Actions证明。原owner尚未收到本记录的执行指令，避免把记录存在误记为已派发。
