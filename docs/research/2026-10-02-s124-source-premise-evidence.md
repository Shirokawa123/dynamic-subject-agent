# S124开工证据：先核前提，再自然承接

S123已保留的来源前提失败是本片依据：用户现在提到一个具体细节，候选会错认成自己以前说过。现有source的speaker/text已经足够核对，不需要新字段、更多历史或第二模型。

复用[S123来源监控/FaithDial](2026-10-02-s123-proposal-source-evidence.md)。本轮定向核对[Anthropic原研究 Towards Understanding Sycophancy](https://www.anthropic.com/research/towards-understanding-sycophancy-in-language-models)与[论文](https://arxiv.org/abs/2310.13548)：研究模型可能迎合用户信念而非事实。它不证明本项目错误唯一原因，也不证明一段prompt可解决普遍迎合；只支持把用户当前前提与已给原话分开检验。共同理解不等于赞同，沿用S122已查一手人类研究的有限设计类比，不构造AI心理状态。

采用最小修订：新`conversation`独立variant在proposal-source上只换第4来源段和第7语气段；前者明确归属问题要核先前原话，用户当前细节不自动属于本人旧话，后者自然短消息、版本/来源按问题需要解释、未给图不推断本人完成状态。不是禁词、固定台词或逐问法规则。参数/schema/data_use/素材/两轮/审计/slot保持，旧已实测合同全部保留。

真实验收先复用同冻结五轮含细节前提的两场景；再看新话题、未见图/完成范围及history-off。记录实际source结构和完整失败，不重抽替换。模拟只检new wire通过原Facade与旧合同兼容。未采用sycophancy训练、critic或外部事实检索：当前需要核的是本次已给原话，新增依赖/用途成本无必要收益；标准库/已有模块复用，无新增许可或服务成本。自然度与来源纠错仍须据原文判断。
