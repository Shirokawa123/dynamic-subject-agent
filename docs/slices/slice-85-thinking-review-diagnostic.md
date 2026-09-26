# Slice-85：审核思考配置的8项同题诊断准备

2026-09-26，基线`fa60fd2`。S84真实审核未过且24次已消费；本片仅按连续工程授权准备，不调用新的Provider请求。

## 用户结果和缺口

在放弃模型或继续改审核方法之前，先区分当前非思考配置是否是主要限制。选S84中8项既有候选/依据，固定规则与输入，仅改变审核推理配置；不能用一次非思考校准推断所有配置或整个模型能力。

## 实施前查证

按context7-mcp检索失败，web工具打开超时后，直接读取[官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)与[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)成功。确认thinking enabled、reasoning_effort=high、最终content与reasoning_content分开；无tools的独立请求无需回传推理；max_tokens覆盖生成completion。本片无工具调用链或历史输入。

采用同模型配置对照，复用S83审核/Gateway/安全Transport/一次性ledger。新模式响应中的推理正文只在内存解析时丢弃，不记录、打印、引用或回传，不把其作为证据。保留旧默认响应对非空reasoning的拒绝。心理学不决定此协议适配，内容标准沿既有知情/时间/观点规则；未改变审核语义或引入依赖。

## 范围与验收

- 审核CLI/prepare/composition增加明确profile：默认standard保持24项、600输出token、非思考及既有字节；新thinking-high限定8项、thinking enabled、reasoning_effort high、max_tokens4096、不发送无效temperature设置，JSON且stream=false。
- 8项只从S84取原样input/candidate，不改review policy、不发参考标签。冻结计划绑定新profile/参数，旧批准不能开启新模式。未批准路径0凭据/0网络。
- 响应处理仅新profile允许有界推理字段并丢弃；最终content、模型、usage边界、完整stop、tool_calls为空与已有审核结构仍检查。超限/截断或任何故障停止，不自动增加预算或重试。
- 测试默认旧路径/原计划兼容、新参数精确出站、新批准绑定、推理字段丢弃且不入审计、异常/超限/截断拒绝、重启不重发。
- 实际8项只prepare，对比S84证明审核输入与policy相同，差异只在配置/字节摘要及subset；给出可审参数后再请求真实次数许可。

状态：离线准备已完成；103项相关检查、独立复核及实际8项同源输入/旧plan兼容核对通过，新启动目录不存在，真实调用0。见[报告](../reports/2026-09-26-slice-85/REPORT.md)，待[8次配置诊断](../plans/review-thinking-diagnostic.md)批准。
