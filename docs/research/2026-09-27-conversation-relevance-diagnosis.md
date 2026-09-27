# S106：人物资料过度表达与分享脱离交流的诊断

2026-09-27。用户提供两张8767截图并否定当前交流/分享体验。本轮仅诊断和准备，不修改生产策略、身份、开关，不读取额外用户历史、不重放私人截图到Provider。下列反馈为现象摘要，原截图和完整聊天不复制到Git。

## 用户结果及实际证据

期待人物回应当前话语，已知知识可以在背景约束选择；明确相关时才说。知道笔名又不愿公开关联，不应退化为无个人反应。兴趣推荐渠道应能解释。分享需要人物自身关注、一个有意义的新变化和此刻向对方开口的理由。

截图证实：聊可爱角色与普通工作内容时重复具体画法限制；称赞笔名后回到泛泛构图/颜色问卷；主动消息包含版本与布局清单；随后把创作方案里的布置说成平时生活环境。加好友原因解释失败来自用户文字报告，截图未给该具体回合，不编造失败台词。S105只证明有限工程闭环，其自然分享和人物交流未通过这次用户体验。

## 源码诊断：事实与推断分开

| 观察 | 代码证据 | 判断 |
| --- | --- | --- |
| 被激活的信息频繁说出 | character_chat_context.py:187常驻全部core，:194起按词片段/线索选资料；character_communication_plan.py:115只核引用合法；first_life_projection.py:119即使fact_refs为空也传core/personality | 没有“激活必说”的硬编码，但缺少理解材料与本轮表达重点的区分。不能在未读实际计划时断言枪械条目一定被选中；可能来自core、selected_facts或近期回复复述 |
| 边界抢走回复 | character_communication_plan.py:25要求保留完整限定；first_life.py:56要求表达完整selected_facts | 将保真误解为完整复述是有证据的设计诱因，非已证明的模型内部因果；不能通过删除事实限定来修复 |
| 笔名反应平淡 | first_life.py:48计划只有action/fact_refs/use_life；first_life_provider.py:32确实带人格和历史策略 | 排除人格规则完全未接入；计划不能明确传递“回应作品称赞且暂不公开身份关联”的交流重点。原作对陌生人的具体反应仍需依据，不写死羞涩/愤怒或一句标志台词 |
| 相识解释不自然 | reviewed_character_chat.py:94已给系统推荐和用户主动发消息；character_chat_context.py:68动机仍标助手提案；character_reply_candidate.py:83把两者一起传入 | 不是禁止解释渠道。已有渠道事实与个人动机提案并置；用户理解的主动加好友行为未被提供，不能补写。不应以资料未定否认系统推荐，也不应虚构她主动筛选过用户 |
| 分享不知道为什么对你说 | first_life_projection.py:78–89只有人物、活动、方案、事件和两个bool；没有encounter/disclosure/对话；first_life_cognition.py:122仍可share=false | 资格不是强制发消息。但没有近期交流依据，就无法可靠承接刚聊的兴趣；已有交流不等于值得分享此事 |
| 版本/清单进入台词 | first_life.py:255生成含v序号的摘要，projection.py:70/88将summary/revision/完整方案传给分享；SHARE_POLICY未分系统回执与人物消息 | 内部表述提供了直接材料，截图表现与之吻合；确定事件有效不等于确定消息有交流价值 |
| 方案物件变成房间事实 | event_projection已标创作文字；cognition.py:150–156最终只检查JSON/语言/长度 | 提示存在但语义边界没守住；不能把方案里有桌灯推成她房间实际有桌灯，更不能依据模型旧回复自证 |

另查到：life聊天system使用专门策略，inner conversation.policy却仍是通用表达策略；不是专门策略完全未用。分享带personality数据，却没有普通聊天同等的when/choice/limits使用说明。统一用途明确的规则应进入修复，不能简单删掉所有保真/披露规则。

## 本轮定向研究与项目取舍

本次针对persona overuse、grounding时机、交流共同基础及成熟conversation实现检索，未把本地小说/截图作为搜索内容。复用S76人物机制和S98人格条件性研究，并核对以下遗漏。

1. [Kwon等，ACL 2023：What, When, and How to Ground](https://aclanthology.org/2023.acl-industry.68/)（已读论文首页机制与摘要）。研究把选出资料、决定何时使用和自然表达分开；检索到资料不保证此刻应使用。适配到现有两阶段：保留已知背景，但允许本轮无事实复述，用当前交流目的选择发言重点。研究针对用户persona而非本项目虚构人物，属于机制类比；不移植训练数据或声称其成绩可直接迁移。验证用相关/不相关的成对情景，兼顾过度使用与必要信息漏答。
2. [Shin等，2026预印本：Appropriate Persona Use](https://arxiv.org/html/2609.04676v1)（已读§2–4）。其样本中，无关persona增加会加重过度表达，单纯persona一致性指标可能奖励这种现象；同时需要检查过度和不足。其内部激活干预依赖权重/隐藏状态，不适用于当前托管DeepSeek调用，且不保证本角色改善。本项目只借反例设计，不引入其代码/数据/PAS裁判服务，不加多轮自评调用。
3. [Clark与Brennan，Grounding in Communication](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf)。复用S76已读结论；本轮作者站PDF初次打开可识别12页，后续定位失败，共同作者副本亦不可用，不声称重新阅读全文。人类交流共同基础解释了为什么应回应对方刚表达的赞赏/兴趣，相关下一轮本身可以表示理解，而非每次解释边界。这里是设计类比，不证明AI具有情绪或意识；共同提及也不证明事实、亲密或同意。
4. [Concordia官方conversational.py](https://raw.githubusercontent.com/google-deepmind/concordia/main/concordia/prefabs/entity/conversational.py)（已读源码）显式关注最近一句可回应什么、当前微话题是否重复以及继续/转换的取舍。借这一有界交流判断，放进现有planning，避免增加多Agent/多轮自问。源码Apache-2.0；[官方变更记录](https://raw.githubusercontent.com/google-deepmind/concordia/main/CHANGELOG.md)可见2.4.0（2026-03-06）及移除部分易混淆记忆组件的说明，不据此保证适合本项目。直接引入会增加记忆系统、组件调用和100条观察范围，违反当前最小边界，因此不安装/复制代码、无新增依赖或数据用途。

未采用：只加“自然一点”的提示；把全部core删掉以减少重复；把相似词去重当语义去重；见到笔名必套固定反应；为了分享强造挫折/成绩/家人评价；仅扩大长期记忆。它们不能同时解决相关性、人物反应和事件归属。

## 零远程机制探针

用现有Facade及合成人物fixture，经FakeTransport执行一轮聊天、一次模拟创作、一次分享；临时诊断脚本`.artifacts/s106_mechanism_probe.py`明确不进入生产或验收测试集合。命令：`.venv/bin/python.exe -m pytest .artifacts/s106_mechanism_probe.py -q -s --basetemp <本轮新临时目录>`。

结果1 passed（7.67s），观察到运行请求仍含提案动机；空fact_refs仍带core；聊天人格规则存在；分享缺对话/相识与人格使用策略、包含revision/summary。真实Provider调用0，未接触用户分支。这个通过只证明诊断机制，**不证明复现了真实模型用词或修好了自然度**；逐词因果尚未进行控制变量远程实验。

## 结论与停止边界

先修P1/P2/P3交界的交流选择与分享理由，不继续优先扩建长期记忆。具体执行/新用途差异见[修复方案](../plans/conversation-relevance-repair.md)。first_life.py:187–197把策略SHA绑定冻结scope；不能直接改全局常量让现有身份失效。用户私人截图不作为远程验收输入，下一轮用新写合成情景；原对话保留，错误台词不回写。
