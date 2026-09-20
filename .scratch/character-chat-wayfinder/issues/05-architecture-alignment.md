# 旧架构如何支撑新的角色聊天体验

Type: research
Labels: wayfinder:research
Status: resolved
Assignee: root
Parent: ../map.md
Blocked by: none

## Question

在制作五情景原型前，核实旧产品定义、聊天编排、身份与知识、时间/经历、关系状态和执行路径与C1–C18的差距；给出有代码依据的保留/改造/新增建议、需改变的旧假设、渐进顺序及尚未确定的授权。比较相关成熟设计能减少什么自建工作，不直接重构运行代码、不迁移旧身份、不外发小说。

## Comments

2026-09-20：用户追问是否应先做方向重构，助手承认原地图缺少显式差距评估。此次先认领评估票，补为原型前置项，避免从素材检查直接跳进旧软件加功能。研究结论只作为建议，不能替代用户体验判断。

## Answer

2026-09-20：完成[方向与架构对齐评估](../../../docs/plans/character-chat-architecture-alignment.md)，基于本地代码/产品契约与三组官方设计。建议保留身份、唯一Facade、单写者Publication和模型/凭据接入，重组角色聊天编排，新增按起点筛选的人物上下文、虚构生活推进及独立分享/投递策略。差距不是仅换界面，也不支持直接引入另一套Agent持久化框架。

报告给出旧假设、代码证据、渐进顺序和未决授权；只作为可审阅建议，未改正式PRODUCT/ARCHITECTURE或生产代码，未读取小说正文/正式身份或调用Provider。研究留存分支为`codex/research/character-chat-architecture-20260920`。此票以评估明确收口，不代表产品重构或原型体验已通过。
