# Slice-20：关系子能力失败的有界维护

状态：completed / diagnostic-only（2026-09-07）。[诊断报告](../reports/2026-09-07-slice-20/REPORT.md)：原故障未复现，精确原因未定，没有行为修复；四次真实采样均解析成功，定向回归 28 passed。产品基线仍为 `f5ea73b` / `dogfood-s19`。

## 用户结果

普通记忆查询不应因可规范化的关系返回格式而被标为关系失败；真正的 Provider/本地失败仍须明确 FailedClosed，不冒充 NoOp，不影响其他无依赖能力。先确定上次失败能证明到哪一层，有证据再修复。

## 范围与停止条件

1. 读取 Slice-19 第 8 轮报告及仍存在的专用隔离根 `C:\Users\30252\AppData\Local\Temp\dsa-s19-ui-9u290eew` 中相关失败事实，仅定向只读，不打开正式身份、不恢复或新增该根的对话。
2. 通过 ApplicationFacade、现有 Module 只读诊断 Interface 或新临时 fixture 复现；真实 Provider 初始采样最多 4 次，只发送原合规 Relationship `{current_user_message, stance_summary}` 投影，输入为报告中的原创虚构内容。
3. 分类区分网络/返回格式/Domain 拒绝/本地异常。无原始响应时不声称已证明历史故障的精确原因；不能因后来成功抹去原失败。
4. 若复现为无语义差异的格式变体，只在既有 Adapter 规范化，保留 Domain 裁决。未知事件、非逐字证据、非法更新和真实 Provider 故障继续关闭。否则根据证据记录原因，不扩成新策略或无限重试。
5. 不改变任何 outbound 字节、Provider 数据用途、credential、请求预算、状态规则或 canonical store；不增加重试，不发送历史，不接入近期对话功能。
6. 有修复则先红后绿，既有成功/NoOp/Rejected/FailedClosed 与其他能力独立提交回归、真实隔离复验、两轴审查、全量及 commit/push 收口。无可修复原因则以证据限制和复现结果收口维护，不伪造完成修复。

## 后续

有界近期对话是下一项主要产品候选，但需要独立任务书及历史文本进入指定 reply 的明确数据用途授权。本切片不提前实现。
