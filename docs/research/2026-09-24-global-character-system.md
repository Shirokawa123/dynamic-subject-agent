# 全局角色系统：研究依据与采用判断

2026-09-24，Slice-75。研究先由产品缺口提出问题，再对照一手论文/官方实现；独立助手分别调查心理学、人物项目及仓库，主助手整合。以下“用于本项目”均为设计推论，不表示复现论文效果或已经实施。

## 角色形成、知识与表达

| 来源 | 已核对机制 | 采用判断与可检验结果 |
| --- | --- | --- |
| [ReverieMem，2026预印本 §3](https://arxiv.org/html/2606.25632v1) | 小说角色的场景经历、可见性事实、情境化表达模式分层 | 用于分开证据、人物理解与表达材料；先过滤所知再选择相关。测试相同事实在不同起点/不同关系下是否正确使用。未核实可直接集成实现；不宣称论文结果会在纱雾复现 |
| [MRPrompt/MREval，2026预印本 §3](https://arxiv.org/html/2603.19313v1) | 人物锚定、相关内容选择、时序/知情限制、自然表达分别评价 | 用于识别错在资料/选择/边界/表达哪一步；不以回答名字或JSON成功验收。提示框架本身不承担持久记忆 |
| [RoleLLM论文](https://arxiv.org/html/2310.00746v3)、[作者仓库](https://github.com/InteractiveNLP-Team/RoleLLM-public) | 角色描述、知识与风格材料分开；检索提示路线与微调路线分开 | 借鉴相关场景/对话示例，不把训练结果冒称API模型效果；不直接决定训练专用模型 |

更细的知识组织对比及现状依据见[Slice-74研究](2026-09-24-character-knowledge-hierarchy.md)。本轮复核其与全局目标适配性；不把资料层方案扩成全脑模拟。

## 从小说到生活和验证

**BookWorld**：[原论文](https://arxiv.org/html/2504.14538v1)、[作者仓库](https://github.com/alienet1109/BookWorld)。将人物稳定描述、动态状态/目标/记忆和世界/地点分开，以场景交互及结算推进。可借鉴人物提议行动与世界确认结果分责、原作初始化与后续分支分责。仓库提示自动提取仍不稳定；不能把它当现成可靠小说建角器。论文较短场景故事实验不能证明长期聊天。代码Apache-2.0，地图素材另有非商业约束；整仓自带代理、ChromaDB及保存结构，集成成本高，现阶段借机制不引入。用一个活动的提议→结果→观察→分享验证，而非移植完整模拟器。

**Generative Agents**：[原论文](https://arxiv.org/html/2304.03442v2)、[作者仓库](https://github.com/joonspk-research/generative_agents)。记忆检索结合重要性/相关性/近期性，计划与事件后的反应互相影响。借鉴关注→活动→结果→回忆的闭环，选择有界事件推进，而非照搬高频tick。原研究仍报告记忆润饰与过度合作，成本也不能忽略。代码Apache-2.0，但研究运行方式及明文key示例不适配本仓库；不接其保存/凭据方式，不启用未授权自动Reflection。验收应区分计划与完成、活动与分享、等待与已投递。

**InCharacter**：[原论文](https://arxiv.org/html/2310.17976v4)、[作者仓库](https://github.com/Neph0s/InCharacter)。把心理量表问题改为开放访谈，并对评判匿名化以降低角色名字先验影响。借鉴开放选择与匿名对比，检测人物行为倾向，不把MBTI当人格真值。论文单题独立上下文不能证明长期关系/共同记忆；需补多轮/重启/生活场景。代码MIT，方法借鉴成本低，量表与数据权利仍需分别核实，当前未引入。

## 心理学与哲学：只用能落到行为的部分

**自我记忆系统。** Conway与Pleydell-Pearce（2000）论述人生时期、一般事件和具体事件知识，以及目标与自传记忆的关系。[原论文](https://citeseerx.ist.psu.edu/document?doi=13241a844c714549c173e239714ae020386172e3&repid=rep1&type=pdf)、[作者机构书目](https://research-information.bris.ac.uk/en/publications/the-construction-of-autobiographical-memories-in-the-self-memory-/)。工程类比：建立核心认识→阶段/经历主题→场景的关联，让当前关注参与选择。验证能否联系学画经历和当前动机；不能让当前愿望改写历史，无依据的个人意义仍是候选。

**共同基础。** Clark与Brennan（1991）将交谈中的理解视为共同达成，并与交谈目的和媒介约束联系。[作者原文](https://web.stanford.edu/~clark/1990s/Clark%2C%20H.H.%20_%20Brennan%2C%20S.E.%20_Grounding%20in%20communication_%201991.pdf)。工程类比：私有知识、已披露、用户声称与共同确认分开；澄清能影响下一轮。不建立无限嵌套的“我知道你知道”，不要求每句确认。验证正确提及不会因本轮没介绍就被拒绝，用户声称熟悉也不自动形成信任。

**情绪评价与应对。** Marsella与Gratch的EMA（2009）把事件解释、评价、情绪与应对联系起来，新信息可触发重新评价。[作者论文](https://stacymarsella.org/publications/pdf/EMA_Dynamics.pdf)。工程类比：已提交事件＋相关目标→带原因和范围的短期反应，澄清可修正误会。不是随机心情值或精确生理仿真；原模型也有参数/验证限制。先有真实事件闭环再加短期情绪提议，不用情绪字段装饰空生活。

**行动、意向与解释。** [Stanford Encyclopedia of Philosophy：Action](https://plato.stanford.edu/entries/action/)、[Intention](https://plato.stanford.edu/entries/intention/)、[Folk Psychology](https://plato.stanford.edu/entries/folkpsych-theory/)。这些讨论支持审视信念、愿望、意图与行动解释的区别，并呈现争议而非唯一实现。工程采用是把希望、承诺计划、尝试、成功分别记录并可验证；不据此推断机器有真实信念、感受或道德主体性。

## 总体取舍

不安装整套Agent框架，不预先建多Agent委员会/知识图谱服务，不把“人格、情绪、记忆”各做一个独立聊天机器人。先使用已有可靠底座，让单人物的创作、认识、交流、提交、生活、投递形成闭环。研究项目给出机制与风险，不替代本地事实审核、数据授权或用户体验。

下一实验优先比较同样预算下的平铺与分层人物组织；再测试实际跨会话交流；再接一次有限生活事件。模型输出的结构正确、事实可追溯与人物自然度分别看，不把一种成功替另一种背书。
