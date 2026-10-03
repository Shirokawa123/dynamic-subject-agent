# S138承接的最小共同经历→活动闭环

2026-10-02用户明确要求本轮修复后开始实现，不再后移核心。以下是准备中的准确设计/待审用途，不冒充已获新外发授权；current138先修复并有限诊断，随后立即把实施升为唯一执行。

实施与验收由[S139任务书](../slices/slice-139-shared-experience-activity-loop.md)承接；在S138收口前该任务书仅作准备。先完成本地完整接缝及可审实际投影，再集中确认新用途。

## 最小用户结果

真实交流的一条有来源片段离开原两轮窗口后，重启仍可作为活动判断依据；下一步实际提交一个构图文字方案，下一轮能对应同一结果接话。活动可有自己的取舍，不能机械服从、临时造一段过去或把文字方案说成画好了图。

SharedActivity Module拥有来源有效性、纠错/撤回及派生依赖。三个内部类型：SharedExperience只证明某说话者在某已提交交流中这样说过；ActivityDecision是当次取舍，不是人格/习惯事实；ActivityResult是实际提交的文字方案/版本差异和事件，不证明实物创作或评价。局部E标签/引用/逐字来源由Python重核，判断和结果随同一canonical Publication成立。

Facade仅暴露当前可读视图、针对具体依据的本地取代/停用、明确推进一步；Adapter不读表或拼装Provider资料。复用CompositionPlan/adjudicate_life/LifeEvent及完整prepared/receipt机制，不能给schema4添加旧LIFE intent来偷权限；采用明确独立root/manifest/authority/schema，旧8788不升级/迁移。模型仅提议，Python裁决阶段/动作/真实变化/引用/head及撤回revision；claim后冷恢复0新增模型，已提交结果幂等。

记忆首版只1条≤400字、来自用户已提交交流的连续逐字片段；不拼接/总结/从助手台词抽事实。首次可通过明确本地选定一条依据形成有据记忆；活动模型形成当次判断，用实际因果选择检验作用，不声称自动长程人格认识。不生成永久人格摘要/Reflection或新向量库。每个判断、活动版本和其后的回复带本地source_dependencies；history-off、context cutoff、停用对共同经历、判断及派生产物同时生效，旧依赖完整轮也不能经两轮窗口绕回。旧实际结果保留历史，失效结果整项不投影，不清空refs假装独立；无失效依赖的重新选择形成新版本，不退回unstarted。

## 准备中的集中新出站用途

同已审Sagiri30事实/4作者解释、同DeepSeek/现有Windows slot，新独立分支；本轮手动一步，不后台生活、主动分享或通知。

- 新整体聊天/结果回聊：原最小人物投影＋主动文字≤1000＋历史开启最多2完整轮≤4000；新增1条active共同依据≤400字＋单个已提交`activity_result:{kind,plan}`，无其它活动/事件副本。
- 活动选择/推进：相同人物最小投影＋1条active共同依据≤400＋`current_activity:{phase,allowed_actions}`＋`current_plan`（首次null）；不附整段近期聊天，不发旧事件。每次明确推进最多1请求，0自动重试。
- 结果回聊只读同一已提交文字方案，不再生成已经发生的故事；判定理由只在本地依据视图查看，不把模型另编的理由假装为当次判断。

共同依据出站仅`shared_experience:{label:E1,quote≤400}|null`，固定用户逐字来源由policy说明。活动只phase/allowed_actions，方案只`subject≤160,composition≤800,focus≤400`；结果仅固定kind与该plan。删去revision/summary/differences/content_kind重复字段，但完整差异、原版本及依据仍本地canonical。没有本地ID、时间戳、head、来源定位、其他身份、原书全文、raw COT或key。判断输出`action/plan/reason_code/basis_refs/decision_note≤160`，只能引用本请求E1；decision_note为本地可见当次解释、不再入后续Provider输入，不是COT或人物事实。失败不成为角色挫折事件。

implementation与离线投影/恢复验收完成后冻结准确review digest再集中确认，不拿本设计当批准。保留原交流、依据、方案、必要恢复数据在同canonical；用量只metadata；用户私人文本不复制报告。不能依旧S105/S107批准扩大whole用途。

## 可观察验收

新分支真实交流一个留白取舍→真实逐字记忆来源→至少3个无关话题使其退出两轮窗口→重启→推进一步→核实际动作/方案及引用→下一轮对应结果接話。相同前态的相关交流/无关交流/停用或相反交流三支对照，保留首次结果、不挑好样本；没有明显影响如实判不成立。另核人物自主性，不要求逢用户就服从。停用/取代后重开，旧依据不能经计划/事件回流；query0模型，重复nonce唯一结果，prepared冷恢复无新调用、故障无活动事件，错误身份不读旧来源。

## 来源与取舍

[Generative Agents论文](https://arxiv.org/abs/2304.03442)及[作者记忆源码](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/reverie/backend_server/persona/memory_structures/associative_memory.py)区分event/chat/thought并把记忆接规划，借鉴有来源分型和因果消融，不采用Reflection/独立JSON存档/embedding。
[Concordia官方说明](https://raw.githubusercontent.com/google-deepmind/concordia/main/README.md)的意图/结算分责类比适配模型提议＋Python提交有限文字产物，不引入模型GM/社会模拟框架。
[EMA作者论文](https://stacymarsella.org/publications/pdf/EMA_Dynamics.pdf)的目标—环境评价仅为‘同一交流在不同活动下有不同作用’设计类比，不证明AI心理或意识。必须用实际选择差异而非情绪标签验证。

研究者已核上述两项目Apache-2.0；本轮不复制代码/加依赖/服务，许可证与维护增量仅来自自建模块。现有仓库机制可复用，但旧life projection不收用户原话，whole明确活动=None，prepared_plan绑定LIFE；这些是需要新精确合同的实际缺口，不以添加字段宣称闭环已成。
