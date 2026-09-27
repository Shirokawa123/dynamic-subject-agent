# S105开工研究：一项可接续的创作活动

用户结果与验收见[S105](../slices/slice-105-first-life-loop.md)。已证实缺口：S104仅提交用户对话，生活事件为空；有历史文本不等于发生了活动。此次继续指令批准了[first-life-loop-review](../plans/first-life-loop-review.md)的有限新用途，原200额度仍是总上限，实际读取67已用/133余。

## 本次定向核查与适用机制

复用[此前生活研究](2026-09-24-life-mechanisms-review.md)，本次重新搜索并打开以下一手来源以补工程接入缺口，没有照搬此前项目名单：

| 来源 | 具体机制与本项目进入方式 | 未采用部分/验证 |
| --- | --- | --- |
| [Concordia原论文](https://arxiv.org/html/2312.03664v2)，尤其2.2及实现附录 | 人物提出尝试，环境判断结果。适配为模型提议有限创作动作，Python验证项目阶段/版本/允许改动后才提交事件 | 不增加另一个模型GM来宣布事实；检查过期版本、非法阶段和外部人物互动不可能进入事件 |
| [ink官方写作手册](https://github.com/inkle/ink/blob/master/Documentation/WritingWithInk.md)，条件变量、一次性选择与分支汇合 | 选择的后果要保留，回到相似阶段不能抹掉前次版本。本项目保留文字方案v1/v2及保留/重做/暂缓选择 | 不引入ink运行时、故事选项菜单或第二存档；重启、重复唤醒和重新修改保持同项目与差异 |
| [EMA作者原文](https://stacymarsella.org/publications/pdf/EMA_Dynamics.pdf) | 应对随当前目标与可控条件的解释变化。适配为有条件的修改/保留/暂缓意图，避免所有未完成都写成心情变差 | 不新增情绪数值或长期人格推断；网络失败不得成为人物挫折，短期意图也不升级为永久性格 |

前两项是工程设计类比，EMA是心理学解释框架，不证明AI有情感或意识。闭集意图能否让人物行为有理由、一个项目是否有趣，是待实测假设。内容变化、后续接话和用户体验才是结果，字段/测试数量不是人物感证据。

没有引入外部代码或依赖。此前已核Concordia Apache-2.0、ink MIT；本次只读机制，不据此前版本猜最新SDK语法或生产支持。采用现有Python/SQLite/Gateway，避免其状态存档和额外服务的集成成本；如后续实际集成须另核版本、维护、许可证与数据边界。

## 初步源码比较与不可省的约束

已有RuntimeTimeline可复用唯一writer、请求幂等、版本冻结和原子提交。但目前ConversationTurn投影默认timeline_outcome均为user/assistant轮，最近历史还将global head视为最新chat head。新生活/主动消息必须用typed系统输入，并调整投影以验证全链、仅选真正用户对话；不能填虚构user_text或用life head冒称已有交流。

活动事实、文字产物版本、事件与分享关联必须处于同一canonical store、同一写入职责。仅把新SQLite放在相同目录，或给Facade加个绕过Host的writer，都不满足此约束。新schema/contract只用于独立试验身份，旧S104保持原有精确合同与policy SHA，不就地升级。

当前共享账本被仍在运行的S104读取，stage闭集是planning/expression。生活决策与分享可分别按这两个阶段计总数，以操作指纹区分请求；生活类型/日期/日6+2及开发24的约束须有本分支canonical尝试依据，不能为了新阶段破坏旧reader或建立一份新200额度。

## 内容与分享的实施取舍

先做start→revise→keep/rework/defer。版本中保存少量实际文字构图内容，修订必须有实质差异；生成的是文字方案，不声称画出图片、技巧提高或他人赞赏。模型选择有边界的创作意图，事件摘要由Python根据动作/版本/修改字段形成。自由理由不能夹带“哥哥夸我”等外部事实成为权威。

主动消息是assistant-origin记录；不挤入原已批准的2完整用户/助手轮历史。分享绑定具体事件/版本，未回marker仅由后续committed用户交流解除；重启、GET、tick、跨日都不算回复。生成后提交前重核分享开关、前置版本、日限及披露状况。普通聊天可能已使用该事件时，在同一Publication保守登记披露状态，抑制重复联系；不加第三次模型调用来阅读真实聊天。

## 已接纳的工程方案

主窗口接纳Sol源码核查方案：仅新生活身份创建Timeline schema3，复用既有operation/idempotency/attempt/global head及commit-plan claim，增加typed system_input与life_record。活动版本、事件、披露、assistant-origin消息、receipt及全局head在同一Publication事务成立。生活系统输入不经过ContributeUtterance文本伪装；Host单写者与Runtime分派继续控制写入，Facade只暴露小型生活Interface。

新manifest/authority/runtime contract及ProfileID由完整definition＋生活scope派生，准确封存资产复用且不改内容；旧schema1/2、S104身份和policy SHA不迁移。普通聊天通过同全局链验证，只投影真实用户对话；生活/主动消息作为不同类型记录，不能令旧两轮窗口错读或丢失合法历史。

共享budget DB可增加metadata-only life_limit_claim与独立累计head，用同事务stage ordinal关联用途、现实日、试验scope；日6/2与开发24跨root/重启，原planning/expression与旧config/head保持兼容。它记录使用额度，不是第二生活事实库。既有初始化与缺失/损坏拒绝规则适用，不能从新身份重新取得24/200。

时间入口采用服务端monotonic短租：已认证heartbeat续租并累积短在线区间，GET仅查询；页关/重启不补离线，暂停不积压。显式模拟一步只改变本分支逻辑推进，并标明模拟，不改现实日额度。无下一决策边界时零模型调用，新的边界只执行有限一步。

不采用把life塞入旧Domain自由文本、Facade旁路SQLite、另一运行器自己的存档、每次GET生成近况或把时间流逝当成功证据。研究完成并进入该方案实施；开工Provider调用0，实际额度67/200。

## Astra独立核查后的恢复补充

用户2026-09-27另授权困难任务可用Astra子代理；主窗口将全局原子性/恢复风险交给新上下文Astra high只读核查。它检查稳定911092f而非移动差异，确认Host单writer与global basis可复用，但原“复用已有原子Publication即可恢复”的说法不完整。

稳定基线_claim_commit_plan独立持久摘要及lineage而未保存完整plan；resume重走propose/express，且已有claim后不能转cycle failure。故AFTER_PLAN_CLAIM/Publication回滚后，模型原结果丢失可能导致摘要冲突或pending卡住。原子事务本身成立不等于这一完整恢复链成立。

接纳修正：仅新schema3将完整已裁决typed plan与claim同事务保存，纳入活动/版本/披露/未回marker/控制依据；resume优先校验并原样重放，零新增Provider。claim前无持久结果的中断明确终止，不默认重生成。验收覆盖分享claim后中断、重启唯一完成、重复请求，以及后续暂停/关闭仍可执行。

这是已证实的基线恢复缺口，也影响旧路径的相应中断窗口。本片不迁移已有schema1/2；旧路径修复列为任务外后续，不能继续把旧验收概括成所有崩溃点均安全可恢复。源码与测试位置以911092f及新片报告为准。

控制与已准备结果并发时，主窗口接纳仅schema3的确定性取消：同writer同事务复核完整prepared/claim、当前basis/control已变化且无receipt/outcome/任何终态，再保存闭集原因的failure transition，保留原claim/plan和已耗额度。完整性未知不得假装stale；已发表结果不能取消。Publication事务增加终态fence，取消后的缓存plan不能复活；新通道在旧stale handler前分派，避免interrupted与operation_failure双终态。

实施分工调整：按用户新授权，Astra high独占Timeline/Runtime及publication测试，Sol high独占其余后端与端到端测试，主窗口仍持有docs/app/真实验收。此调整针对复杂度集中点，不再让两个模型重复完整实现；稳定差异由独立Sol复核。
