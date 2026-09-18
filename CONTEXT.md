# Dynamic Subject Agent

本上下文描述一个有来源、可封存并沿单一时间线持续发展的主体身份。

## Language

**Subject Task**:
主体对用户显式交付的文字工作作出的、可查询进展与结果的任务承担；接受、暂缓、取消和完成是有依据的不同事实。
_Avoid_: Participant goal, conversational promise, autonomous background activity

**Artifact Approval**:
用户对一项确定文本成品及其保存操作的逐次批准；内容或操作变化使该批准不再适用。
_Avoid_: General conversation consent, unlimited filesystem permission

**Logical Forgetting**:
用户撤回某条既有记忆的活跃使用，使其不再参与通常召回与后续外发；原有本地聊天及审计历史仍保留。
_Avoid_: Physical deletion, rewritten fact, temporary dialogue cutoff

**Source Candidate**:
模型从一份获授权来源中提议、并带有逐字证据的 Genesis 或 Knowledge 片段；候选本身不是身份事实。
_Avoid_: Character fact, imported memory

**Source Draft**:
用户对同一来源候选集合所做的本地、可修订、未封存选择；它不是 Profile、Genesis 或运行时状态。
_Avoid_: Character, identity, snapshot

**Freeze Mapping**:
从一个 exact Source Draft revision 确定性形成的 Profile、GenesisPremise 和 Knowledge member 完整预览。
_Avoid_: Draft, generated character, published identity

**Freeze Basis**:
绑定 Source Draft revision、来源摘要、映射策略和全部 Freeze Mapping 内容的不可含糊摘要。
_Avoid_: Draft digest, source digest

**Sealed Identity**:
经用户明确确认 Freeze Basis 后形成的不可变 Profile、Genesis 与 Knowledge 快照集合；只有封存后才可成为新 runtime 身份。
_Avoid_: Preview, draft, candidate character

**Runtime Identity Projection**:
从当前 Sealed Identity 确定性读取、供本轮回复形成使用的最小不可变身份视图；它不增加身份内容，也不是可发展的性格状态。
_Avoid_: Personality state, identity prompt, generated persona

**Civil Time**:
现实世界的日期与时区坐标；它说明一条陈述发生在什么时候，但不证明离线期间发生过任何主体经历。
_Avoid_: Timeline, lived time

**Temporal Anchor**:
把一条来源明确的相对时间表达绑定到其陈述时的 Civil Time 与一个绝对目标日期；原始表达仍是证据，当前相对说法只是投影。
_Avoid_: Reminder, schedule, rewritten memory

**Subject Time**:
主体在单一 RuntimeTimeline 中实际提交的 Experience 次序；只有 committed Experience 才属于主体经历。
_Avoid_: Wall clock, elapsed offline time

**Interaction Recency**:
当前 canonical Admission 与同一身份最近一个 committed conversation turn 之间的 Civil Time 关系；它描述多久没有已提交互动，不代表期间发生了主体经历。
_Avoid_: Absence experience, offline life, last app open

**Lifeworld**:
主体从封存前提、已提交经历和获授权现实观察中形成的有意义环境；Civil Time 只是其未来坐标之一，不能单独生成世界事件。
_Avoid_: World clock, invented offline life, omniscient world state
