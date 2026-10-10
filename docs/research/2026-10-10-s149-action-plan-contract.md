# S149开工证据：动作资格与plan分支

用户结果/必要缺口/先定验收见[S149](../slices/slice-149-rework-contract-continuity.md)。本轮有界只读研究0产品模型/credential/私人源正文/代码依赖，主窗口写入接纳。Context7当前无可调用能力，依context7-mcp技能官方资料回退；没有把未执行查询写成成功。此处是动作合同纯工程，心理/哲学知识不能定位字段/阶段原因，不以理论解释AI心理；人物关注/纠正效果沿S148研究另验。

仓库机制已核：shared_choice_policy只把start/revise与其他action概括区分；`revised`只允许keep/rework/defer、合法rework后才允许revise/defer；来源替换过滤current_plan而不重置真实phase。Python拒绝rework非null，rework不增版本、不写新方案，revise必须有实际差异；旧依赖不会因非新版本动作被洗成有效。S148原final在该规则只读重放确定拒绝，新提示不能当作已修。

| 一手来源 | 机制与本次接入/限制 |
| --- | --- |
| [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)及[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) | 官方建议明确JSON格式及期望示例；有效JSON不保证业务字段关系。保现json_object/text协议，只补无本题答案的null动作示例，不假定任意json_schema可直接接入。 |
| [JSON Schema conditional](https://json-schema.org/understanding-json-schema/reference/conditionals) | 依标记字段施加分支约束，if需含required防缺项误满足。借action决定plan类型的表达，现Python已实施，不新增schema库。 |
| [W3C SCXML转移选择](https://www.w3.org/TR/scxml/#SelectingTransitions) | 源状态/事件/条件共同给转移资格，请求本身不授权跳转。继续由Python实际allowed_actions与提议后裁决；示例不能授权未列动作。 |
| [DeepSeek strict工具调用](https://api-docs.deepseek.com/guides/tool_calls/#strict-mode-beta) | Beta工具协议/endpoint与schema子集不同。此次不采用，以免换协议扩大验证面；也不声称其支持任意条件schema。 |

采用：独立action-contract候选替换现有动作段，明确start/revise新完整plan、keep/rework/defer为JSON null；rework先进入阶段，下一明确推进才可revise；示例为格式而非事实/本题答案/当前理由，继续合法defer。share/reply/字段/协议/slot同S144；同schema6/业务能力Manifest，但新合同与policy/grant/audit/publication key精确隔离，原对象不升级。只有真实新场景才可判断效果。

未采用：把rework非null丢弃plan、改写成revise、合并返工与新版本业务语义，或为躲失败重置phase。那会改变版本数、差异、事件/share资格、依赖和恢复，不能当兼容格式修复。也不引入第三方模型框架、依赖、critic或Reflection；无需新增数据出站。研究事实支持分支表达方法，提示是否改善本模型是待验假设，不由论文/字段/测试数量证明。

验收复用Facade/三用途fresh票据/单写者Publication/nonce/重开：Fake核rework/null不增版本、下一revise新方案、坏组合仍拒、新旧grant/pins/wire隔离、来源更正使旧链失效；真实新色温场景先定至多9首次/0retry，首次失败或无新plan结束，人物/场景/工程分列。未将本次可选W1取舍变永久边界。
