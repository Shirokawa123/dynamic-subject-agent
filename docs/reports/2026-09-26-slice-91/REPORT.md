# Slice-91：本地交流计划原型

2026-09-26，基线dcf9b61。已完成无Provider的两阶段原型，不再追加同题审核；真实模型效果尚未验证。

## 实际变化

CharacterCommunicationPlanLab沿用现有Facade/Producer，由local_product显式装配。规划输入包含本次局部F标签、完整原条目与当前交际前景，输出仅action/fact_refs；Python重建最多4个完整条目及全部限定后进入表达。合法动作限回答、提话题、条件取舍、保留、澄清；未知/重复/超量引用、额外事实正文和新经历动作不被接纳。

两个任务都经ModelGateway且本入口只接受local=True的Gateway；当前request_digest仅作本地绑定，不放入模型输入。未选资料不进入表达输入，但不等于角色不知道。原直接生成、已存在Provider调用默认不变，没有新公共Facade业务方法。

最重要的限制是：程序只确认本轮内容选择/流程，表达器仍可能夹带无依据台词。因此所有最终候选保持semantic_review=required、persisted=false；没有记忆、生活或持续心理状态写入，也没有启用日常审核。

## 行为与独立复核

101个唯一用例通过：新行为32＋Gateway2共34项（37.49秒）；旧EvidenceModel67项及3项加强补跑共70项（46.95秒），重复3项不另计数。覆盖Facade真实路径、非法计划表达0、完整限制保留、未选资料隔离、远程Adapter拒绝且装配前0调用、失败关闭、越界台词仍required及canonical文件快照无变化。

新上下文Sol high按code-review独立复核稳定源码，未发现可复现实质问题；未重复运行测试或接触本地私人资料/凭据。静态差异检查通过。

主窗口还用真实v9资料运行明确标注的本地替身演示：

| 替身场景 | 规划/表达调用 | 可见结果 |
| --- | --- | --- |
| 本轮提话题 | 1/1 | 固定示例回复，required |
| 新历史活动动作recent_activity | 1/0 | FailedClosed，无回复 |
| 合法计划但表达故意声称近期一直思考 | 1/1 | 仍required，没有伪标为事实已核实 |

这证明流程约束，也直接展示语义局限；不是模型已经改善的证据。记录仅本地`.local_indexes/eromanga-sensei/s91/local-demo.jsonl`，CLI为`app/desktop/character_communication_plan_demo.py`。

## 下一步的可审准备

六题使用原合成问题和资料，去除旧candidate_text；Facade导出stage-one精确投影，只有self_knowledge/stage_description/encounter/disclosure/current_message/policy六字段。文件`.local_indexes/eromanga-sensei/s91/planning-projections.json` SHA256 `1c0969bbba68b1f02abc373f19572e3f2ee3bf7cea9b416a283fa7b4350614d8`。

下一片只把[六题两阶段试验](../../plans/communication-plan-generation-trial.md)的远程装配、预算和恢复准备完整，默认不调用。该新用途和最多12次尚未批准，既有16次审核许可不能代替。
