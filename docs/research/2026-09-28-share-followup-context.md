# S108：主动消息应成为可接续的话语

2026-09-28。仅研究与方案准备，未新增Provider用途或执行真实调用。

## 用户结果、证据与解释

用户应能在她主动分享后说“你刚才那句是什么意思”，而不必完整复制分享。S107成功的澄清输入完整复述了线稿、笔尖、留白等内容，不能证明简短指代成立。

本轮源码确认：`first_life_grounded.life_chat_planning`只从`base.recent_dialogue`生成成对U/A来源；`_validate_sources`只接受完整轮标签，`FirstLifeBasis.shares`虽已存原文却未接入这个投影。ARCHITECTURE S105也明确主动消息不进入两完整轮窗口。零Provider合成探针已确认share内唯一短语未进入v3规划、表达及两阶段请求。事件、方案可说明发生了什么，但不能代替她具体说过什么。更详细调用链及探针见[源码核查](2026-09-28-share-followup-code-audit.md)。这是数据通路缺口，不等于已证明每种简短追问都会答错。

## 定向一手资料与取舍

1. **交流研究。** 重新打开作者站的[Clark与Brennan，1991，Grounding in Communication](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf)，核对正文pp.129–131：说出话与对方充分理解有区别，澄清可以嵌在后续交流中。设计类比是保留可供追问的话语对象；不能把“用户后来发过消息”直接解释成已理解/同意，更不能据此推定亲密。本文不证明AI有共同心智或感受。本片不引入理解程度评分或新心理状态。
2. **独立的机器人话语事件。** Context7实际resolve Rasa并query BotUttered，返回3.6.x官方源码文档；同时打开[当前官方Dispatcher文档](https://rasa.com/docs/reference/integrations/action-server/sdk-dispatcher/)和[events.py源码](https://github.com/RasaHQ/rasa/blob/main/rasa/shared/core/events.py)。BotUttered记录机器人说的话，apply_to更新latest_bot_utterance，不需要伪造一个用户句子。借这一角色/事件区分；本仓库已有LifeShare和同一Timeline，因此复用现有canonical记录，不引入Rasa Tracker作为第二存储。已查看[Apache-2.0许可](https://github.com/RasaHQ/rasa/blob/main/LICENSE.txt)，但不复制代码或安装依赖；官方文档仍可访问并含版本更新说明，不据此判断整套旧OSS支持周期。
3. **消息身份与顺序。** 定向搜索并打开[LangGraph官方message.py](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/graph/message.py)，其消息合并保留ID，并可按相同ID更新。借用“话语身份与顺序应明确”的设计对照，不采用其覆盖更新语义：本项目历史Publication不可改写，纠错必须是新话语。已查看[MIT许可](https://github.com/langchain-ai/langgraph/blob/main/LICENSE)。本片没有集成需求，不作框架维护/性能选型，不引入依赖、检查点或额外存储。

复用已有S106共同基础与S107说话者研究，不重复检索人格模型。当前问题不需要哲学上的意识论证；人类交流研究有解释力，具体400字/两次接话是待验证工程取舍，并非论文给出的阈值。

## 最小适配与不采用项

- 适配现有Timeline冻结前缀、LifeShare原文、v3的来源选择和可逆版本授权。新增有界只读分享来源，仍把“说过”与“真实发生”分开；生活/世界事实继续取已裁决事件。
- 不把分享拼成空user的假轮次；不把分享塞入人物事实库；不从UI复制聊天；不读取全历史或加通用检索；不新增长记忆/摘要模型调用。
- 不仅靠`answered=false`选来源：该标志服务于不催促的投递控制，后续追问仍可能需要刚刚分享的原文。
- 不为了让旧问题通过而重发分享、删除失败、修改历史或重置预算。

验证必须分别观察：原文确实到达有权限的规划/被选中的表达；短追问是否自然接上；来源错误是否能被承认；关历史/损坏/截止时是否确实不外发。离线投影通过不能代替真实交流效果。[具体方案与授权增量](../plans/share-followup-context.md)给出上限及停点。
