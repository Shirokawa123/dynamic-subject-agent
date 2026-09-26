# 同模型思考配置：8项固定诊断方案

2026-09-26，Slice-85准备、Slice-86执行。**用户已明确同意本次8次thinking-high诊断。** S84的24次非思考审核已全部执行，误放8/11明确反例；本次只比较推理配置组合，避免继续混合改规则、改资料和换问法。

执行结果：首项未形成可用审核，按故障停止约定终止，1项尝试、7项未发送、无重试。通用错误码不足以确定原因，见[S86报告](../reports/2026-09-26-slice-86/REPORT.md)。以下为已停止计划，不自动重试/恢复。

## 申请范围

- 仍使用现有DeepSeek官方服务、deepseek-flash和Windows Credential Manager同槽，用途仍是独立依据审核。
- 只复用S84的8个原样请求内容：cal-02、06、07、09、10、14、15、19；4条正向、4条明确反例。它们包含原误放、原误拒及已通过控制，是诊断集，不是新的未见评测。
- 本人摘要、阶段/相识分支、用户合成消息、候选及REVIEW_POLICY完全相同。参考标签仍不外发，不增加原书或私人历史，不调用生成器。
- 与原配置的区别：thinking enabled、reasoning_effort=high，每次max_tokens=4096，JSON、不流式；不发送在该模式下无效的temperature参数。
- 最多8次，一项一次，无重试；任何来源/凭据/网络/格式/引用/审计失败停止。截断不加token重跑，不能用新计划绕过失败。
- 单项沿用现有30秒传输超时；超时说明本次等待预算未取得结果，不能当作语义判错或静默拉长后重试。
- Provider返回的reasoning_content仅在内存解析时检查类型并丢弃，不记录、显示、引用或回传；仅保留最终verdict/有限issues。旧默认非思考路径继续拒绝非空reasoning，不改变旧调用。
- 输出总上限32,768 token（思考及最终completion），比原单项600更高；这可能增加等待与费用。按[官方计费](https://api-docs.deepseek.com/quick_start/pricing/)结算，不虚报实测usage或承诺一定改善。

## 依据与决定规则

已实际读取[官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)和[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：模式与effort可指定，reasoning_content与最终content分开，无tools的请求不需回传推理。本次都是独立单轮且无tools，不建立推理历史。

若同题仍明显误放/误拒，停止把当前模型配置当可靠自动审核，重新设计表达范围或评估模型；若改善，再决定是否值得完整校准。8个挑选病例不能直接宣布生产可靠，也不自动启用日常审核或改变MVP质量门槛。

这是两种配置组合的同题诊断：思考开关/effort、可用生成预算和temperature处理一起变化，不能将差异单独归因于某一个参数。

## 精确产物

候选保持v9草稿`273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94`。8项cases文件SHA-256为`3cd9a0cd36fc97ef1a76addfd7619ad9a4aa2b44ca3e700cdcab4179a8158dbf`，与原24项逐条相同，仅取子集；8份review projection及request_digest与S84完全相同。

新计划：`ff02e220deeec77e3249cd8ae2e1ee6bb8ce7aab2c3d8f65fdeded2ed300afec`。[完整计划](../../.artifacts/character-reply-review-trials/ff02e220deeec77e3249cd8ae2e1ee6bb8ce7aab2c3d8f65fdeded2ed300afec.plan.json)、[候选预览](../../.local_indexes/eromanga-sensei/s85/诊断候选预览.md)均本地保存；已核对出站thinking/high/4096、无temperature/工具/历史，未创建启动目录。

默认准备：

```powershell
.\.venv\bin\python.exe app/desktop/character_reply_review_trial.py --draft .local_indexes/eromanga-sensei/s78/character-evidence-draft-v9.json --source-root .local_sources/eromanga-sensei --reviewed-digest 273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94 --subject sagiri --anchor v1-pre-broadcast --cases .local_indexes/eromanga-sensei/s85/cases.json --review-profile thinking-high
```

获批后才追加`--approve-plan ff02e220deeec77e3249cd8ae2e1ee6bb8ce7aab2c3d8f65fdeded2ed300afec`。原24项批准不含此配置或追加次数，当前仅prepare。
