# S150 开工证据：绑定有效方案的局部修订

用户结果、缺口和先定标准见[S150](../slices/slice-150-natural-feedback-continuity.md)。仓库已有版本化CompositionPlan、精确basis、来源失效与Publication恢复，复用这些；未有自然反馈修改活动的通道。

| 已核一手来源 | 具体机制与本次适用性 |
| --- | --- |
| [Clark & Brennan 1991作者PDF](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf) | 表达与获得足够理解证据分开；以当前目的判断。设计类比：收到反馈不代表修订完成，需核实际差异，减少用户重说整份方案的成本。 |
| [Dingemanse等2015原文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0136100) | 对话修复尽量具体、局部；设计类比：歧义仅澄清缺失目标，不改整份构图。人类研究不能证明AI理解、心理或意识。 |
| [RFC6902](https://www.rfc-editor.org/rfc/rfc6902.html) §§4.3/4.6/5 | test基准、replace已有目标、任何失败不当整体成功。适配为当前版本＋逐字唯一片段条件替换，再原子Publication；字符串片段算法是本仓设计，不是RFC的直接条文。 |
| [Kubernetes官方更新机制](https://kubernetes.io/docs/reference/using-api/api-concepts/#choosing-an-update-mechanism) | 条件Patch/resourceVersion避免丢失更新；只借基准和局部修改思想，不引入云、库、重试或依赖。Context7无可调用工具时按skill官方回退核实。 |

选择：一个feedback ModelTask返回自然正文和chat/clarify/revise提议；Python处理结构、唯一原文、编辑范围、版本/权限/来源和最终状态。来源保持精确原话，只当前有效方案可修，不从before存档或助手旧话造原貌。模型仍决定语义与是否采纳，真实语义另验。

未采用：替换E1并解封失效旧方案（破坏权限）；全量重写composition仅锁subject/focus（同字段内其他细节仍可改）；扩大近期窗（不是持久接续）；新增W1/Reflection/第二store/外部Agent框架（当前证据不支持必要性）。零外部代码/依赖引入，无许可/维护集成负担。

验证：独立LOCAL资格先完成Facade正常发送→精确局部修订→3无关轮→真关闭重开→实际choice→当前结果回聊，附歧义/NoOp/权限/冷恢复反例。真实批准后保全部首次最终输出、实际wire metadata与canonical，按预定语义标准检查。LOCAL测试不证明人物效果；有界来源/编辑上限只属于当前实验合同。
