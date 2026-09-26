# Slice-85：8项同题思考配置准备

2026-09-26，基线`fa60fd2`。针对S84非思考审核失败，准备同模型8项配置诊断；**新增真实调用0，当前不启用自动审核，MVP未完成**。

## 变更与范围

现有审核CLI新增review_profile，默认standard保持原24项、600输出与plan/出站字节；thinking-high只8项，启用high思考和4096总completion，不发temperature，仍为单轮无工具JSON。新配置进入plan digest，与旧批准隔离。

响应helper新增显式bool discard_reasoning，默认False保留2048上限及拒绝reasoning；只有已验证thinking-high Adapter传True。新分支检查推理类型、原始usage整数及总量，丢弃推理正文，最终JSON/stop/空tool_calls/模型/结构检查保持。旧生成器及日常路径没有自动启用思考。传输仍30秒，超时/截断/任何故障停，不加预算重试。

Context7和web抓取失败后直接读取官方思考模式/Chat Completions成功，证实参数与独立无工具请求不需回传推理；具体来源及限制见[任务书](../../slices/slice-85-thinking-review-diagnostic.md)。此协议适配无新的心理学假设或依赖。

## 实际计划与验证

新计划`ff02e220deeec77e3249cd8ae2e1ee6bb8ce7aab2c3d8f65fdeded2ed300afec`。8项为原cal-02/06/07/09/10/14/15/19，4正向/4明确反例；每项projection及request_digest与S84相同，只有subset与推理配置/出站摘要改变。body为7558–13105字节，合计98471；新启动目录不存在。旧standard重新prepare仍得到原`dbd9e286…faa8b`，证明兼容未被换模式破坏。

候选文件SHA-256：`3cd9a0cd36fc97ef1a76addfd7619ad9a4aa2b44ca3e700cdcab4179a8158dbf`。输入、规则、标签和预览仅本地Git忽略保存，参考标签不外发。

新增thinking检查22项通过（56.74秒），原review/context trial/DeepSeek cognition/模型别名回归81项通过（138.26秒），共103项；覆盖精确参数、旧批准拒新配置、推理不入结果/审计、总量/截断/格式/工具拒绝及恢复不重发。独立Sol high只读复核未发现实质缺陷，未重复跑全量测试。

## 下一决定

准备的是更小诊断，不是又一轮提示词试错，也不是证明思考模式一定可靠。它同时改变思考配置、预算和temperature处理，不能把差异只归因于开关。真实结果尚无；即使8项改善，也需再考虑完整校准与成本/延迟，不自动接日常聊天。

已提供[8次具体批准方案](../../plans/review-thinking-diagnostic.md)。S84原24次已全部消费且只含非思考600配置，不能用来开启本次8次high/4096。等待用户决定后才执行。
