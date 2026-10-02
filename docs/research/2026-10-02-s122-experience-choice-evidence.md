# S122开工证据：共同理解与当前选择

用户结果、已证实缺口和验收见[S122](../slices/slice-122-experience-and-current-choice.md)。S120复述现有v2，S121能澄清并接话，但尚无同问题/不同经历对照。先验证现有current-topic，不先新增状态或提示。

| 一手来源 | 研究事实与本次机制 |
| --- | --- |
| [Brennan & Clark 1996作者PDF](https://web.stanford.edu/~clark/1990s/Brennan%2C%20S.E.%20_%20Clark%2C%20H.H.%20_Conceptual%20pacts%20and%20lexical%20choice%20in%20conversation_%201996.pdf) | 三项人类实验支持交谈历史与双方临时概念协调影响后续指称。类比：相同“对话/等待”词应随双方刚澄清的含义而使用，不把暂时理解写成人格 |
| [Reason-based choice 1993出版社摘要](https://www.sciencedirect.com/science/article/pii/001002779390034S) | 提出理由帮助处理选择冲突及解释选择，讨论语境影响；正文403未读。类比：检查具体选择与此前理由的联系，不能只看“记得”或同意用户 |
| [Clark作者研究说明](https://web.stanford.edu/~clark/research.html)、S109已有Grounding研究 | 理解达到当前交流目的所需程度。1991作者PDF本轮超时，不称重新全文阅读；类比：先接住对方在意之处，再看自己的取舍 |
| [LangChain官方trim_messages源码](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/messages/utils.py)、[短期记忆文档](https://docs.langchain.com/oss/python/langchain/short-term-memory) | Context7/官方核对最近消息、角色边界及不截半条的处理。它不替代本仓完整canonical U/A轮、来源权限和Publication；本次复用现有两轮/4000，不引入该MIT依赖 |

研究限人类交流/选择与工程消息裁剪；不证明LLM心理、关系理解或人格成长。当前模型是否使用刚说清的理由，是本轮真实验证假设。

仓库已允许当前意见/理由/设想，exact背景/方案/事件保持。用两个场景、各两种对同一词的不同理解、同第三轮问题与同重开第四轮追问；每链续自己的canonical回复，首轮初态等价，旧失败保留。选择可以相同，但须有针对各自理由的具体可区分取舍；不规定一个分支必须选某动作。第四轮第一轮已退出窗口，不冒称长期记住三轮。

接入复用prepare_branch/SeedAdapter/open_first_life_free_input_trial及Facade。新增可复用owned分支验收工具减少逐片专用装配；仅新UUID、自写文字、metadata和实际wire的无正文结构摘要，默认私聊观察器不变。不引入源码依赖或新增凭据接入。未知失败停该链、0自动重试；不把程序seed/模拟输出当人物体验。

不采用摘要/画像/Reflection/持久关系状态/论证图或心理Agent：当前两轮足以，新增解释与状态裁决没有本片必要性。若实证缺口是exchange权限语句被读成不可使用交流理由，再只澄清此作用域，材料/schema/参数不变；未先假定必须改提示。
