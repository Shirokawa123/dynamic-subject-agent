# S98：人格如何影响选择与表达

2026-09-26。目标是让人物在不同情境下有可解释的取舍，而非只答对个人知识。新功能实施前完成本机制核查；原作场景核对另保存在本地s98研究包，未审核解释不提升为原作事实。本次不新增Provider用途。

## 仓库已有能力和缺口

已核代码：CharacterEvidenceModel筛选起点/知情/依赖，chat_organization.core常驻上下文；CharacterCommunicationPlanLab把上下文转换为F资料，再让规划选至多4项，表达仅得所选资料。没有独立的人格核心保留契约，资料未选可能连同关切/身份丢失。DISCLOSURE和短消息规则是通用产品约束；不能当作纱雾人格。S97身份映射有来源与内容完整性，但不解决这一行为问题。

复用：Facade、现有证据定位/原文校验、人物预览、交流Producer、本地Gateway及选择裁决。新增只读候选解释和贯穿规划/表达的有界视图；不引入人格分值、独立心理Agent、Reflection或新状态库。源事实和性格解释分开，后者不能由fact_refs选中就当作新经历。

## 本次实际查阅的资料

| 来源与已读范围 | 具体机制及可核结论 | 本项目适配及可观察验证 | 不采用的部分 |
| --- | --- | --- | --- |
| [Mischel与Shoda 1995原论文摘要](https://pubmed.ncbi.nlm.nih.gov/7740090/?dopt=Abstract)，DOI 10.1037/0033-295x.102.2.246；全文副本访问失败，不声称阅读全文 | 理论将情境间可预测的行为变化视为人格表现，涉及目标、预期、情感等相互作用 | 工程类比：人格条目写明情境、倾向和界限；固定核心对不同对象/请求应有合理差异，不能一律冷淡 | 不实现完整CAPS心理模拟，不把理论视为机器具有人类人格的证明 |
| [Fleeson 2001原研究摘要](https://pubmed.ncbi.nlm.nih.gov/11414368/)，只读摘要 | 三项经验取样研究报告个体内行为变化显著，同时行为分布的中心倾向较稳定 | 区分倾向、单次表现、当前状态；一种反应不自动确认为永久人格。验收允许多种合理台词 | 不凭小说片段估计Big Five数值、概率或临床结论 |
| [SillyTavern官方角色设计文档](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)与[官方发布记录](https://github.com/SillyTavern/SillyTavern/releases)，本次已读常驻/非常驻段落与发布页 | 角色描述、人格与场景作为常驻prompt内容，示例与历史竞争预算；常驻材料也有成本 | 借常驻核心思路，显式测表达阶段即使fact_refs为空仍保留人格；控制总长度，超限拒绝，不能静默截断 | 不整体移植聊天存储、Provider和扩展系统；项目需要起点/证据/提交契约 |
| [RoleLLM原论文§2.2、§4.3、Limitations](https://arxiv.org/html/2310.00746v3)，复查S76结论 | 描述与相关对话示例支持角色表达，但研究限定单轮；资料噪声影响取材，数据清洗排除拒答 | 借有情境的表达依据；相似场景仍须匹配对象与阶段。用成对情境评价选择和表达，拒绝可为合理结果 | 不照搬台词、catchphrase频率、训练数据或单轮分数；不把关系后期台词灌入初识 |

许可证/维护/成本：SillyTavern官方[LICENSE](https://raw.githubusercontent.com/SillyTavern/SillyTavern/release/LICENSE)为AGPL-3.0，本次只借机制，无代码复制、安装或依赖；官方发布页可见持续版本发布，但不据此保证适合本项目。RoleLLM只复用论文机制，不引入资源。无新增SDK，不需要服务配置或凭据。Web检索仅用公共研究关键词，没有发送本地小说、身份或聊天。

哲学/心理学适用性：有助于解释“同一人格为何不等于同一反应”；不用于给虚拟角色诊断、证明意识或从单个事件猜测创伤原因。来源事实、作者解释和设计假设必须在可审产物中分开。

## 实施决定（不是研究发现）

1. 原作底稿首先保留场景、对象、发生时间、实际选择、可确认理由和适用界限。后续成长、未确定时间、对亲密对象的表达只能作为局部依据或反例；不得自动变成起点倾向。
2. 首版人格用少量连贯、可质疑的解释条目。每项绑定已核的起点认识，写清适用情境、可能的选择、表达影响及禁止外推。依据不足仍留在作者说明，不为了填满字段制造性格。
3. 人格视图与self_knowledge分开，不把解释标成世界fact；常驻进入规划与表达，不能被最多4项资料选择丢弃。模型可根据情境做选择，不硬编码“遇见某关键词必怒/必害羞”。
4. 本轮仅允许本地预览与本地替身贯通。旧远程投影和默认行为保持原字节；新增人物解释、与之绑定的policy必须有独立具体用途批准才可出站。结构验证只能证明资料按设计进入流程，不能声称真实角色表现改善。
5. 准备少量成对情景：谈绘画/追问家事、具体建议/空泛评价、线上交流/强迫见面、理解作品取舍/要求全盘讨好。评判是否有理由地投入/保留/分歧、是否承接话题、是否越界；不要求固定答案。

本地候选提炼后再固定代码输入形状和运行资产，不由上述研究替代原作核验。人物证据没有覆盖的语气、恋爱/依恋、当前情绪和长期成长继续明确未知。

## 本地实现形状与取舍

初步原作核查已有四组可由v9起点认识支撑的候选：绘画与交流的意义、现实与线上渠道差异、外形设计的具体取舍、对参与设计角色的投入；普遍评价敏感性、后续自辩语气及陌生私信习惯尚不足。语义结论由主窗口读场景后接纳，不由代码自动证明。

选用与v9分离的本地personality draft（明确local-interpretation-candidates），绑定v9 digest、subject、anchor；条目含interpretation、when、choice、expression、limits和claim_ids。claim_ids只能来自同一已验证起点的eligible认识；解释和限制原样进入预览，证据ID、原文引文及排除项不进模型视图。摘要中仍可能有语义错误，必须保留作者解释身份，不能标作事实。

沿现有Facade.preview/propose_character_reply使用一个local-only Producer，在原规划/表达投影外加明确的新类型：conversation仍使用原裁决契约，character_core与personality在两个阶段都保留；标签与原文事实分开。core从已验证组织中的core生成，未组织样本至少保留identity；不从当轮fact_refs裁剪。旧默认Producer/DTO/远程Adapter不变，新类型不能传入旧远程wire。复用现有ModelGateway任务种类，但只接受capabilities.local=true的替身；本片不装配远程Adapter。

不选把人格解释塞入self_knowledge：现有knowledge允许fact/belief，且解释由CharacterEvidenceModel明确排除，混入会破坏认识语义。不选新人格状态机/分数或额外模型调用：尚无实际证据表明需要。新本地读取者只核验输入、组装候选，不写Studio/Timeline；无需新增Facade公开步骤或聊天store。

## S99冻结执行的适用性补核

S98本地实现完成后，需要让新增解释的用途确认针对可执行计划。此处纯工程，无新增心理假设；沿用上文人格依据与六项来源结论。已重新读仓库FrozenAttemptRun、CharacterCommunicationTrial、逐阶段request/result联查与Adapter惰性鉴权，旧实现可复用，不能另建一套恢复真值。

定向查持久执行的副作用/重试边界：Context7 resolve-library-id返回fetch failed，依技能转查官方文档：旧durable-execution地址已重定向、raw同名文件404，改读[LangGraph官方Graph API源码文档](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx)中的恢复与副作用说明。官方说明检查点在节点边界保存，恢复可能重新执行节点及其中副作用；已完成task结果可以复用，任务顺序与幂等仍需保证。适配为每个规划/表达阶段独立claim与结果记录；计划、派生表达与出站指纹互相绑定。模型服务投递不确定时没有可依赖的幂等回执，本项目保留unknown并停止，不照搬自动重试/补跑。

不安装LangGraph、不复制代码/引入依赖，仅核对机制；无需新增许可证或维护成本评估。正式流程继续既有单次DeepSeek transport和已测high/4096/30秒配置，不引入新SDK行为。验证应覆盖未批准零出站、错计划拒绝、发送前claim、故障后不再发、重启只读完整结果、审计缺失unknown及旧默认字节兼容。S99只准备，不调用真实Provider。
