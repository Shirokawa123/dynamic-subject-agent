# Slice-87：安全失败分类与单项诊断准备

2026-09-26，基线`5e0f124`。S86首项失败且按约停止，根因未知。本片只改本地可诊断性并准备单项入口，真实调用0。

## 结果与证据

需要在不保留敏感正文的前提下区分传输/HTTP、响应信封、截断/预算、最终内容JSON、审核结构/引用故障。当前不同原因都成为reply-review-failed，21.363秒不能定因；原响应未保存，不声称能重放实际故障。

按diagnosing-bugs技能先用Fake Transport在Facade真实路径建立快速回归：至少“网络故障”和“finish_reason=length”当前输出同一码，改进后应不同。原始实际失败仍未解释，此测试只锁定诊断丢失。遵守仓库凭据边界，不按通用技能建议使用环境变量key或保留raw trace。

待证伪原因按优先级：①截断→预期安全码为response-truncated；②返回内容/审核格式或引用错误→对应JSON/schema/quote/label码；③HTTP/传输→闭集状态或transport码。不给耗时编原因，不修改模型/数据/规则/生成参数以混淆诊断。

## 范围

- 新增显式、默认关闭的安全诊断错误模式：只传播闭集阶段码及必要的受限HTTP状态码，不输出异常原文、response/header、reasoning、候选正文或凭据。保留unavailable/failed-closed/unknown语义。
- 对思考截断必须先看finish状态，再解析可能为空/不完整的最终content，使“截断”不被误记为一般JSON失败。旧默认成功/失败契约和出站字节保持。
- 审核Adapter→Gateway→候选→审计保留安全错误码，缓存校验只接受对应模式的闭集码，不允许任意异常字符串通过。正常supported/unsupported/uncertain行为不变。
- 同一审核CLI增加明确单项诊断profile（如thinking-diagnostic）：严格1个既有case，生成参数与S86完全相同（high/4096/30秒），plan绑定诊断模式及1次执行范围；默认prepare，新批准才允许发送。
- 原S86失败不能自动恢复；诊断入口不提供自动重试。后续允许多少次及如何根据新证据继续，由具体新授权决定，不改旧失败记录或余下7项状态。
- 本地行为测试证明错误分类、秘密标记不泄漏、默认旧码兼容、新旧批准隔离、失败停批及恢复不重发。实际单项只prepare并核对与S86首项模型输入/参数一致。

本片是诊断工程，哲学/心理学不直接解决错误分类；现有协议、Facade/Gateway/安全Transport与ledger复用，无新Provider/依赖/数据类型。若发现实际根因需新切片处理，不在本片猜测修复。

状态：本地实现、115项唯一用例覆盖及独立复核完成，0新增真实调用。首项已冻结并逐字节确认同S86；见[报告](../reports/2026-09-26-slice-87/REPORT.md)。后续真实诊断等待[新工作流指示](../plans/review-failure-diagnostic.md)，不恢复旧7项。
