# DeepSeek Flash 返回标识兼容

2026-09-13，真实head36–45远程能力均FailedClosed，本地目标创建/查询正常。HTTP200诊断只记录无密钥的包结构：5次响应model均为deepseek-flash，与原deepseek-v4-flash不一致；角色、JSON内容类型、无reasoning/tool_calls及token预算正常。原始诊断见raw/diagnostic-memory.jsonl；不保存响应reasoning或密钥。

用户明确同意纳入当前切片，在核实官方映射后兼容此返回名，原请求、凭据、用途和预算不变。当前环境工具目录中没有Context7 resolve/query或工具搜索入口，故退到官方原文核实：

- [官方更新日志，2026-09-10](https://api-docs.deepseek.com/updates/)：V4 Flash已退休，旧模型名deepseek-v4-flash暂时路由至V4.1 Flash，新调用名deepseek-flash。
- [官方发布公告](https://www.deepseek.com/en/news/deepseek-v4-1-flash/)说明相同兼容关系。

这不是旧模型权重未变的声明，实际服务已升级至V4.1 Flash。我们不增加新Provider、不改请求模型字段，不推断任意新模型可用；仅将六处返回模型校验统一为严格tuple(deepseek-v4-flash, deepseek-flash)。其他schema、reasoning、tool、token限制不变，旧请求名未来退役仍需新决定，不自动换名。

Adapter复现修正测试桩后2 failed / 10 passed；实现后别名正反与既有Provider共28 passed in 0.45s。未知/近似名、其他模型、null和数组均拒绝，两个接受路径均验证只发一次且请求仍为原模型名。全量和真实成功验收另见REPORT。
