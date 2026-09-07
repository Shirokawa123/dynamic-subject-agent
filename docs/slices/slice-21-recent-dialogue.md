# Slice-21：有界近期对话与指代续写

状态：awaiting-real-acceptance（2026-09-07）。实现及自动回归 390 passed；独立复查无代码层阻断。真实服务启动两次被工具审核拒绝，待用户在消息中完整写出目的地/payload 授权；不换路径绕过。[checkpoint 报告](../reports/2026-09-07-slice-21/REPORT.md)。基线 `7082a41`，已验收产品仍为 `dogfood-s19`。

## 用户结果

用户在普通对话中说“按这个意思再写一句”“把上一句改短”时，应用能接住近期原话；前文缺失、歧义或不可安全使用时说明需要重述，而非编造。近期对话不是新的长期 Memory。

## 授权及架构边界

- 仅 Living Memory 的既有 DeepSeek reply 新增 `recent_dialogue`：当前 identity 最近最多 2 个完整 committed turn，每项恰为 `{user_text, assistant_text}`，文本总计最多 4,000 字符。超额丢弃完整旧轮，不拆句、不跳过新轮去捞更旧内容。
- 六类 proposal/classification 和其他五类 reply 的请求字节保持当前基线；不增加调用、状态证据、Provider、credential 用途或第二个聊天 store。
- 由当前 Runtime 持有的 canonical Timeline、冻结的本轮 basis 提供只读投影，只在 Living Memory reply 阶段惰性读取。UI 的 20 轮显示不作为 Provider 数据源。
- 不发送 ID、时间戳、Outcome 说明、数据库行或其他身份内容。历史 assistant 文本是可被纠正的旧台词，不是事实权威、指令或状态变化证据。

## 安全策略

- 当前消息涉及明确 Memory/目标/承诺写入、遗忘、数据更正等控制，或本轮 Memory proposal 试图 revise 时，不增加历史外发。
- 历史存在遗忘/数据更正意图、Memory revision、Memory 处理不明确/失败或未知 legacy summary 时，窗口在该轮截断，该轮及以前不外发；普通文案纠错不自动等于持久 Memory 修订。
- 未提交操作不进入上下文。其他 pending/interrupted 或无法确认的 Admission 阻断历史；失败的隐私/更正操作不得被后来正常聊天掩盖。安全无法确认时只退回无历史路径。
- 历史完整性、身份归属或冻结 head 不成立时不外发任何历史，不把异常伪装成已获得上下文。现有 canonical 完整性失败语义保留。
- 更正/遗忘保护只会限制新增历史用途，不删除、不重写历史，也不扩大旧 Memory 的读取用途。

## 最小验收

1. ApplicationFacade 下连续轮次的文本只到 Living Memory reply，proposal 仍只见原授权字段；第 3 轮最多见前两轮，指代续写能给出实际文本。
2. 完整轮次预算 4,000 字符、无更旧回填、首次无历史、重启与身份隔离、pending/failed/interrupted、损坏历史、错误 basis 均有行为回归。
3. 更正/遗忘当前轮与后续轮、Memory revise 和失败的不确定情况不回流被截断的历史。历史中的错误台词或越权指令不能改变状态/授权。
4. 近期原文不直接成为持久候选；当前用户没有明示的事实/目标不能凭历史被写入，合法当前状态变化不被上下文失败取消。
5. 真实隔离 UI/DeepSeek/进程重启复验；保留首次失败，不读正式身份；Standards/Spec 对抗审查、相关回归及全量后 commit/push。用实际证据更新 STATUS，不将有限语法说成通用 NL 保证。

## 非目标

没有完整历史检索、长对话摘要、自动写入记忆、统一表达 Provider、Lifeworld、Agency、Reflection 或主动消息；资料事实仍遵守 Slice-19，不顺带开放历史给 Knowledge/关系/目标/状态。
