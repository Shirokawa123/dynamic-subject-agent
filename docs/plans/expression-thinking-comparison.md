# 六份相同表达输入的high配置对照

2026-09-26，Slice-94准备。**待批准，新增真实调用0。** S93的12次许可已消费完；此次只申请新的6次表达，不重新规划，不改提示或资料。

## 为什么只检查这一处

S93合法规划之后，表达仍在3题补出无据近期心理活动、惯常频率或更具体的年限。当前配置把high用于选动作/引用，最终自由表达却是非思考。要检验更高表达预算能否改善，应固定已发生的规划选择和实际表达输入，而不是同时加规则、换资料或再次生成计划。

这不能修复cal-19漏选F30的问题，也不能证明更高思考一定有效。S90审核配置曾改善是动机，不是生成任务的结论。无明显改善时停止本方向的相同试验，转向明确的产品取舍，不默认提高额度或重复prompt迭代。

## 精确范围

- 复用S93源parent plan `47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0` 的六份**实际**expression request：cal-06、20、08、18、19、15。
- 先以当前源资料和原接口重建父计划，再联查全部planning/result/derived request/expression结果。缺失、损坏或不匹配不接受；不能手填projection、重新挑F标签或把F30补回。
- 发送的selected_facts、action、stage_description、encounter、disclosure、current_message、EXPRESSION_POLICY与S93逐项相同。旧答案只用于本地对照和审计完整性，不送模型；parent/数据库/账本ID及hash不送模型。
- 唯一变化是表达生成配置：从非思考/600/temp0.3，改为thinking enabled/high、4096总completion、无temperature；JSON、非流式、无工具、30秒不变。是配置组合比较，不能把差异单独归因于某一个参数。
- 同一DeepSeek官方端点和deepseek-flash，原Windows Credential Manager同槽仅HTTPS鉴权；不打印/复制key，不做余额或凭据验证附加请求。
- 最多6次，一题一次表达，规划0次，无自动审核、修订、重试或补额；任一来源/凭据/传输/格式/审计故障停止全部。投递不确定保留unknown，重启不重发。
- 结果仍为required/persisted=false候选，不写正式聊天、生活、关系或心理状态。仅在本地Git忽略实验目录保留受限请求/结果/审计，不保存reasoning、raw response、headers、异常正文或凭据。

上限6×4096总completion以及对应输入费用，含思考与最终输出；不是实际消费预测。没有新原文、私人历史、Provider或真实生活用途。

## 待核对产物与决定

新计划`3f2cf4f198aa26825639e96d45e9737285fc777f129aa05726b1e39573808de5`已绑定父计划文件、31份相关审计文件指纹、当前资料、六份原样表达投影、生成参数与6次上限。[完整本地计划](../../.artifacts/character-expression-thinking-trials/3f2cf4f198aa26825639e96d45e9737285fc777f129aa05726b1e39573808de5.plan.json)。

实际prepare和逐题预检确认：6份projection及HTTP messages/policy与S93相同，整个HTTP body仅max_tokens/thinking/reasoning_effort/temperature四项配置变化。新body5139–5889字节，合计33856字节；planning_calls=0，新run目录不存在。42项相关检查和独立复核完成，无遗留实质问题。预检在`.local_indexes/eromanga-sensei/s94/preflight.json`，不是实际生成结果；见[准备报告](../reports/2026-09-26-slice-94/REPORT.md)。

默认准备命令不读取凭据或调用Provider：

```powershell
.\.venv\bin\python.exe app/desktop/character_expression_thinking_trial.py --draft .local_indexes/eromanga-sensei/s78/character-evidence-draft-v9.json --source-root .local_sources/eromanga-sensei --parent-plan 47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0
```

新批准后才可追加`--approve-plan 3f2cf4f198aa26825639e96d45e9737285fc777f129aa05726b1e39573808de5`。旧两阶段批准不能开启本计划；CLI没有手写投影、追加资料、重新规划或另根重试入口。

沿用S91预先的六题本地标准，按实际已选来源复核三个已见错误、正常回应、话题推进与自然度；保留S93原答案，不挑选重试最好答案。原计划选择缺口单列，不让表达阶段获得未发送资料的信用。

即使改善，也只证明这6份已见输入的配置表现；不证明一般单阶段生成、日常连续聊天或完整MVP已可靠。
