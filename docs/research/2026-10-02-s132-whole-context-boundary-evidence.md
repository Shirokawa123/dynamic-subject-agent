# S132前置证据：同一人物从新一段交流继续

2026-10-02。当前唯一执行仍是S131；本文件只准备下一完整用户结果，待current承接后实施。只读仓库代码/既有合同，未读用户运行root、未调用模型、未改src；不规划余下十片。

## 用户结果、缺口与语义

用户明确选择“从新一段交流继续”后，后续只参考该边界之后的新聊天；人物、原聊天和回执保留，重开仍是同一个人。查询旧记录仍能看到之前发生过的交流，不能把新段开始说成失忆或删除。

whole现在只有history-off/on：关闭阻止近期原话外发，重新开启可再次选择既有两轮；没有持久上下文cutoff。S131原请求纯查询解决的是恢复操作结果，不改变资料选择边界，也不能用取回回执代替开始新交流。新结果需要一个显式、本地、零模型的持久控制操作。

至少区分三件事：history关闭/开启是外发开关；新交流边界是旧轮不再参与此后上下文的持久选择；物理删除是另一个未授权行为。此片不以reset、forget或“重新开始”含糊地合并三者。

## 必须保留的现状与可复用接缝

| 实际代码/合同 | 可复用的行为 | 本次不可直接借用的部分 |
| --- | --- | --- |
| [OriginalWholeAuthorization与合同](../../src/dynamic_subject_agent/original_whole_chat.py)、[Authority guard](../../src/dynamic_subject_agent/local_identity_authority.py) | 当前身份、准确contract digest、history值及history/identity revision；生成前和最终Publication核验 | 现token没有独立上下文边界。不能只改布尔值或让前后相同的True掩盖边界已变化 |
| [Timeline verified prefix](../../src/dynamic_subject_agent/timeline.py) | 冻结attempt、head、published outcome digest、verified prefix digest、revision head digest；完整两轮及未决操作校验 | whole没有reset_cutoff。当前非LIFE路径要求最后ConversationTurnRecord的head等于frozen head，新增系统边界会打破这个假设，须精确解释合法非聊天Publication |
| [S110合同](../slices/slice-110-continuous-chat-recovery.md)、[FirstLife reset](../../src/dynamic_subject_agent/first_life.py)、[Facade入口](../../src/dynamic_subject_agent/application.py) | 明确确认、幂等请求、同canonical持久边界、零模型本地回执；旧失败不改成功、原文保留 | FirstLifeInput、LIFE_SYSTEM_INTENT、schema3 life_record/S1、活动/分享权限不属于whole。不能因为功能名字相似就改whole的life权限或装配生活系统 |
| `_verify_failed_context_prefix` | 只在旧失败确为终态且完整冻结依据被随后Publication证明时越过，不能只相信head数字 | 现实现用`prepared_plan`验证schema3计划；whole schema1没有该prepared合同，不能原样调用或缺失时放行 |
| 当前whole schema1恢复/原请求查询 | 已提交回执与记录可核；冷pending不自动重新调用模型；重取不admit/execute | 新边界必须有自己的零模型持久/重放语义，不能补造旧回复或将没有可核终态的unknown/pending当已经结束 |

whole的`_verified_dialogue_prefix`对history关闭也校验完整性。新增边界不能使关闭历史成为绕过未决来源、损坏前缀或权限撤回的入口。

## 两处一手工程依据

1. [SQLite Atomic Commit](https://www.sqlite.org/atomiccommit.html)说明单事务全部发生或全部不发生，rollback journal负责中断后的恢复；其保证依赖正常锁/同步等条件。本仓Timeline已使用DELETE journal与EXTRA同步。**接入判断**：边界事实、幂等receipt与完整基线在同一canonical事务成立，不能先写一个“已重置”文件再写Timeline。数据库原子性也不自动保证产品来源语义正确。
2. [SQLite Isolation](https://www.sqlite.org/isolation.html)说明写者串行，事务读写有隔离；rollback模式的读取与写入锁会影响提交，WAL有另一种快照行为。**接入判断**：沿现有单写者和短本地事务，不为此功能切换journal模式；不要持有另一个读事务或registry锁等待这个writer。SQL隔离不解决Python层的循环等锁。

已按context7-mcp resolve/query SQLite官方文档；返回原子提交概述与WAL示例，准确的rollback锁/上下文接缝覆盖不足，因此直接核上述两个官方页面。本片不复制新代码、引入依赖或改变SQLite配置。纯工程和用户控制语义足够解释这个问题，不需要新增心理或意识假设。

## 推荐最小合同（尚未实现）

新建准确的whole本地操作，经ApplicationFacade进入，UI仅提交显式确认及请求标识。新操作不是普通聊天台词、模型提议或LIFE reset的别名。

确认文案应直接说明：此前聊天不再作为后续上下文，旧记录仍可查询；已审人物资料继续可用；之后主动发送的普通文字仍按既有DeepSeek用途和本地canonical保存处理；history开关保持当前值。取消、查询或预览零写入、零模型，不发送/覆盖草稿。

确认成功后由同一Timeline写者在canonical存储追加可核的本地边界和receipt。实现前须据现有表/Publication合同选择表示方式，不能为了沿用schema3引入life_record。若需要新schema或能力资格，应在新合同/独立数据路径中明确旧reader如何拒读/只读，不能静默升级正在运行的旧root或执行不可逆迁移。

必要的局部合同不取决于字段叫什么：

- 边界绑定同一profile/timeline、准确操作/请求、此前完整已验证前缀和可重放receipt；不能仅存时间戳、最后一条文本或一个无依据head。
- 控制事实与成功回执同时提交。用同一请求重取只能返回同一结果，不能再推进cutoff；相同ID不同参数应冲突。中断状态先核已提交事实，不重建或覆盖原记录。
- 后续取材同时限制exchange和S128用户话题回取。即使某轮不发送原话，也不能偷偷借边界前用户原话取sealed相关材料；边界本身、内部revision和receipt不进入Provider消息。
- 保留`has_prior_committed_exchange`的事实意义：这个人已经交流过，不因为新段的exchange为空改成第一次相识。history-off不被reset自动打开；再开启仍不能越过新边界。
- 当前请求在发送前取得“身份/历史授权＋边界”的一致本地快照，候选最终COMMIT核同一版本/冻结前缀。不能在准备时读一个cutoff、提交时只核旧history bool。

这里改变的是本地历史选择范围，Provider仍接收同一已批人物、同一主动文字及至多两完整轮/4000，字段和用途不增加，凭据仍仅同slot HTTPS Bearer。边界后的数据是原范围的子集，**不是新Provider用途**。但真正的资料/Provider使用撤回不能被后台自动reset解除；确认必须把继续使用既有固定人物资料及之后新输入的含义说清，不能把普通转题猜成授权更新。

## 锁序与最终提交：两个易漏风险

**不要让Authority持registry/history锁等待Host worker。** 当前生成和Publication会核`original_whole_guard`，worker需要registry锁。如果确认端先持该锁再同步调用worker并等待，就可能形成“确认线程等worker、worker等registry”的循环。建议先在Authority短锁内核身份/权限并取得局部token，释放后提交本地控制；writer在准确提交点重新核token。UI/HTTP的等待、确认对话和网络生成都不能夹在持锁本地事务里。

**系统边界不能被当聊天，也不能放宽所有head缺口。** 当前whole验证假设每个Publication都对应ConversationTurnRecord。若边界推进head，首轮新消息的最新聊天head可能小于冻结head；需要按同一前缀精确核认可的系统边界，不能直接像LIFE一样忽略任意head差异。历史查询仍应显示旧用户/本人轮，本地控制可另显示准确回执，不把系统文字伪装成user/assistant完整轮。

首个小结果建议在确无inflight/pending未决操作时串行确认：有未决轮明确返回暂不可用或提示先取回/结束该轮，0模型，不隐式等待长网络调用，不取消未提交草稿。后续若需要在生成中立即建立边界，须单独完成可审的取消/版本门槛；不能一边确认成功，一边让旧候选在新边界后提交并复活旧上下文。这个限制是首份实现取舍，不是永远取消边界并发能力。

对旧终态失败/控制的处理必须有来源证明：schema1可研究复用已经持久的commit receipt/完整expected basis与随后边界Publication关系，不必借schema3 prepared_plan。只有终态、冻结依据完整且确在边界前的旧操作才可被排除；pending、没有可核终态的unknown、无冻结依据、损坏或边界后的新控制仍关闭。已有canonical终态失败只是交付结果未知时，不能改称成功或未发送；是否允许明确边界排除其旧输入，应按同一终态/完整前缀规则裁决，而非仅凭UI显示unknown永久阻断。用户开始新段也不能修复凭据故障、资产权威损坏或解释未知投递结果。

## 可观察验收

1. 同一人物两轮交流→明确确认边界→新输入：0模型边界回执，原两轮原文/摘要不变；新轮exchange不含旧轮，人物core/persona不变，不伪称初识。
2. 新段再聊两轮并重开：边界、原记录及新段接续一致；窗口最多两完整轮/4000，S128回取不跨边界；history关闭/再开启均不复活旧轮。
3. 重取相同确认、取消确认、只查边界/原请求：分别幂等或零写入，均0模型。不同身份、旧token、同ID异参数拒绝；草稿保持。
4. 边界提交前/提交后响应丢失及重开：要么无边界，要么同一边界/receipt，不出现只改cutoff没有回执；不重传模型，不重写旧失败。
5. 已知终态旧控制与当前安全新消息分别观察；没有完整冻结证明、未结算pending/unknown或损坏时仍不可用。已有终态但交付未知的旧结果保持unknown，不伪造成功/未发送。边界之后新控制继续阻断，不能靠上次reset覆盖未来权限。
6. 两线程/故障钩子检查锁序及最终token：确认线程不持registry锁等worker；旧候选不能在已生效边界之后按旧授权提交。首版拒绝inflight时应及时返回，不能读写双方互等。
7. 新系统head之后第一条新聊天能通过完整prefix核验；任意伪造/缺失的非聊天head不能因此通过。Interface行为检验，不能只测数据库新行存在。

不采用：history-off当永久遗忘；清空/删除/复制旧聊天；换人物/root冒充同段恢复；给UI直接写registry或SQLite；独立cutoff JSON作为第二事实权威；按墙钟或文本匹配推断边界；沿LIFE/schema3借活动/S1权限；每次HTTP重试建立新段；解除所有旧失败/控制；切WAL或引队列框架解决局部锁序。

独立旧记录保护与新交流效果都需验收。旧记录不改只证明数据保留，新轮不外发边界前来源、重开仍成立才证明该用户结果；两者不能互相替代。当前仅完成准备，未改变S131或任一运行分支。
