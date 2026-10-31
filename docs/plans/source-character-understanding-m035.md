# M035：系统从情景材料提出人物理解并用于新交流

2026-10-31，承接用户明确的通用底座方向。目标是同一条流程可用于不同角色，人物理解由ModelGateway中的模型提出，Codex不预写风格结论。当前先做隔离、未发表的理解与回答对照，不改封存人物或RuntimeTimeline。

## 研究取舍

核读[RoleLLM §2.2–2.3](https://arxiv.org/html/2310.00746v3#S2.SS2)：区分角色知识和表达示例，按片段组织知识提取；其RoleGPT使用相关原对话，Context-Instruct生成候选再筛选。借鉴区别和材料组织，不引入其训练流程、口头禅标签或基于模型既有角色知识的档案生成。

核读[CoSER §3.2/4.1](https://arxiv.org/html/2502.09082v3#S3.SS2)及[作者数据构建源码](https://github.com/Neph0s/CoSER/blob/main/data_construction/main.py)：`extract_from_chunk`保持情景/对话，`assemble`按角色聚合情节与对话后生成profile。借鉴情景与说话者保留、聚合后解释；不移植自动重试/备用模型、近似引文匹配，也不将推断出的思想当已发生状态。仅参考机制，自行实现，无新增外部依赖、代码或权重。

## 最小实现

`character_understanding.py`接收target、starting_point和有序source_scenes；角色数据不在通用代码中硬编码。一个模型请求同时提出最多4条观察和3条条件性解释。观察复用EvidenceProjection与既有抽取decoder核逐字引用；解释复用PersonalityInterpretation数据形状，明确标为model-proposed-interpretation，绑定实际观察引用、when/choice/expression/limits。

结构、引用和说话者检查只能证明来源连接，不能证明解释正确。观察的知情/时间仍unknown，结果保持unreviewed-model-proposal；不自动转成已审人物定义。对方台词不能单独证明目标行为，候选必须关联目标；坏来源或跨角色候选拒绝。

同一资料与当前问题可构建两路回复：source-only、with-understanding。两路原文、模型和回复政策相同，差别只有实际模型生成的理解候选。问题不进入理解生成请求；新回复不抄原台词。此对照检验解释步骤，不直接宣称优于旧M034，也不以单次采样证明统计泛化。

正式Facade保留LOCAL入口，并有单独准确获批的LIVE试验入口；不能通过LOCAL入口接远程。复用FrozenAttemptRun、现有transport/Windows slot、精确出站复核和一次性账本。结果只入实验文件，不建身份、人物store或Timeline。

## 当前验证与下一步

13项LOCAL/模拟传输检查通过：实际模型提议传入后续回复、两路材料一致、跨角色绑定、无原文引用/他人台词/假引用拒绝、未批准原文用途零发送、传输前撤销、结构失败停止、换根不能重试、原材料不变与零canonical写入；没有形成解释时返回NoOp，不拿空理解继续宣称对照完成。测试提议均为合成，不代表材料理解的真实效果。

单独生成解释是否有增益是可证伪的假设；若直接材料更有效，不以增加人格卡片或更多生成层维持本实现。机制选取继续由实际对照结果决定。

产品准备梅莫莉6段静态材料和一个原创对照角色，同一流程各1次理解＋2问题×2条件，共10次首次请求。新用途包含原文节选，旧S160/M034/M033不覆盖。有效审阅0e5dc916b57883205acd918629355202fe6279fc9b37f000ccf84b28719c7a6f（002）；001因强化目标主体约束被替代且仍未批准。当前零新增真实请求，待准确范围确认。
