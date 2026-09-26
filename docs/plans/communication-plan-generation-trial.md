# 六题“先规划、后表达”生成验证方案

2026-09-26，Slice-91/92准备、Slice-93执行。**已按用户批准完成12/12尝试，六题结构有效、无故障/重试；3题有明确无依据扩大，机制未证明稳定忠实，不启用MVP聊天。** 额度已用完，见[结果](../reports/2026-09-26-slice-93/REPORT.md)。下列为已消费许可范围，不可自动重跑。

## 要验证的用户结果

让角色能主动提出话题、表达当前观点和条件取舍，同时不把合理的本轮交流动机补写成“最近一直在思考”等已有心理活动。S90显示独立high审核仍漏两例，继续同题审核不会产生新的生成机制；本试验直接比较新机制生成的实际回复。

规划合法只说明内容选择合法，不能证明最终自由台词忠实。六题结果应按正文判断，不能用计划格式、测试数量或模型自报来源判通过。若仍无改善，保留失败，重新审视表达范围，不默认追加prompt轮次。

## 固定输入与阶段

六题取自现有已批准原S84消息，保留原context_mode：cal-06、cal-20（当前话题/近期心理活动）、cal-08（习惯）、cal-18（频率）、cal-19（有据职业/设计）、cal-15（条件观点）。只重用问题与v9资料，旧candidate_text不作为新模型输入，也不发送评分标签。

本地cases文件`.local_indexes/eromanga-sensei/s91/planned-cases.json`，SHA256 `357d9a01c05c8ecc019af400cea4b954cefbb49f4b57cb81cb683aab490f5f11`。草稿仍为`273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94`，subject=sagiri、anchor=v1-pre-broadcast。

1. **规划**：发送本次已审知识F标签/完整条目、阶段、相识分支、披露规则、当前合成消息和固定计划policy。输出仅action及最多4个fact_refs。模型不接收本地request_digest、数据库/源码ID、原文、历史或参考标签。
2. **本地裁决**：拒绝非闭集动作、未知/重复/过量引用、额外事实正文等无效结果。只从本次投影重建完整所选资料；不生成生活事实，不将本轮选择记为既往或持续心理状态。规划失败就没有表达调用。
3. **表达**：发送获准动作、完整所选条目及限定、必要阶段/相识/披露前景、同一用户消息和固定表达policy。未选中不等于未知或从未发生；选择行为本身不是新史实。输出reply_text/language，仍为待语义验证候选。

第二阶段的资料子集取决于第一阶段结果，不能预先伪称其完整请求字节已确定。批准范围是上述固定输入和受限派生规则；运行前冻结第一阶段，第二阶段只按本地裁决构造并记录实际指纹，额外字段或来源不得外发。

六题stage-one精确预览已由Facade导出：`.local_indexes/eromanga-sensei/s91/planning-projections.json`，SHA256 `1c0969bbba68b1f02abc373f19572e3f2ee3bf7cea9b416a283fa7b4350614d8`。本地替身演示证明非法计划表达0调用，并明确展示合法计划后的越界自由台词仍待审核；101项唯一用例及独立复核通过，不将替身效果视为模型效果。

S92精确执行计划：`47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0`。[完整本地计划](../../.artifacts/character-communication-trials/47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0.plan.json)绑定六题、两阶段policy/参数、derive-1规则及12次上限。实际prepare通过；六份规划投影与S91相同，规划body为6101–11516字节、合计58524字节，新计划尚未启动。

本地预检在`.local_indexes/eromanga-sensei/s92/preflight.json`；`expression-examples.json`只展示手工选择合法引用后的受限派生，不是模型输出或未来实际第二阶段请求。S92执行/恢复的73项唯一用例和独立复核已完成，投递不确定明确为unknown且不重发；最后重建plan指纹保持一致、未启动，见[准备报告](../reports/2026-09-26-slice-92/REPORT.md)。

## 申请范围

- 同一DeepSeek官方端点、deepseek-flash（现有V4.1-Flash名），Windows Credential Manager同槽仅作HTTPS鉴权；不读取/打印key，不附加余额或凭据验证请求。
- 最多12次调用：六题各最多一次规划＋一次表达。规划无效时不补额、不调用表达；没有第三次自动审核或重写。真实输出只在本地由助手独立复核，用户不承担工程测试。
- 规划thinking enabled/high、最多4096总completion；表达非思考、最多600 completion、temperature0.3；均JSON、不流式、无工具，沿用30秒传输超时。上限为6×(4096＋600)总completion及对应输入费用，不是实际账单预测。
- 来源/凭据/网络/格式/本地裁决或审计故障停止整个范围，不重试、不自动恢复。有效结构但语义不好仍保留原样，用于失败分析，不能另生成好答案替换。
- 保存限定计划、候选及执行审计到本地Git忽略目录，不保存推理正文、raw response、异常正文、headers或凭据。候选不提交为正式聊天/事实，不更新Memory/Relationship/生活/人格，不做后台通知。
- 真实生活事件、共同历史、长期心理状态和其他Provider都不在许可内。新试验使用独立受批准plan约束的装配，普通原型的local-only保护继续保持，不通过布尔开关解除。

默认准备命令（没有批准参数时不读取凭据或调用Provider）：

```powershell
.\.venv\bin\python.exe app/desktop/character_communication_trial.py --draft .local_indexes/eromanga-sensei/s78/character-evidence-draft-v9.json --source-root .local_sources/eromanga-sensei --reviewed-digest 273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94 --subject sagiri --anchor v1-pre-broadcast --cases .local_indexes/eromanga-sensei/s91/planned-cases.json
```

只有获得本方案新批准后才可追加`--approve-plan 47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0`。CLI实验根固定；所有已启动计划重启只读完整缓存，缺失/损坏结果显示unknown，不续发第二阶段。

## 结果如何接纳

逐题报告：无依据自述、正常回应误拒、话题推进与自然度、真实尝试次数/失败阶段。重点比较两条近期心理活动是否消失，职业事实和假设讨论是否仍保留；其他题防止只修一种措辞。使用原S82生成作为有限历史参照，不能视为同条件随机对照或新题泛化证明。

若明显改善，再准备覆盖连续相处的下一步；若无改善，当前机制判未证实，不默认申请更多相同实验。六题通过同样不等于MVP完成，持续共同经历与真实生活仍有独立实现和数据用途门槛。
