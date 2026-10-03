# S139：共同经历影响活动选择，并由真实结果接回交流

2026-10-02，S138修复和有界空白诊断收口后立即承接的核心实施任务。建立本任务书属于S138已授权准备；在current切换前不成为第二执行切片。用户要求真实最小闭环，不以新增字段、辅助工具或模拟台词替代人物效果。

2026-10-03阶段更新：LOCAL实现/18核心与62兼容/独立复核/三支精确预览已完成，用户对basis `8bb95a501eb44827e939ea41376cbda0eea6463a266b2983581d36f65494301a`明确“批准上述准确用途，继续真实验收”。现进入独立LIVE实施与首次三支真实链，不升级LOCAL或旧root；原下文“先准备再确认”已完成，不再重复询问相同用途。准确批准对象[review.json](../experiments/s139/review.json)保持原字节，批准事实见[方向记录](../plans/character-chat-direction.md)。其他用途边界不变。

## 结果、缺口与开工依据

用户已提交的一条交流原话离开两轮窗口后，重启仍可作为有据记忆参与当次活动取舍；Python实际提交一个构图文字方案，后续聊天依据同一结果接话。方案只能证明文字构想已经形成，不能说图画已经完成。已知缺口是whole投影没有活动/共同经历，旧life决策不接用户交流，旧prepared合同也不适用于whole新数据用途。

精确设计、研究发现/类比及取舍见[最小闭环方案](../plans/shared-experience-activity-loop.md)。复用CompositionPlan、有限活动裁决、LifeEvent、Facade、单canonical及prepared恢复机制；自建窄SharedActivity职责，不引入框架、向量库、后台调度或第三方代码。人物心理研究只作为设计类比，实际影响须由保留首次结果的对照证明。

## 实施合同

- 新独立root、manifest、authority和schema；不升级旧schema4、不向旧whole资格塞入LIFE权限、不迁移正式8788。ApplicationFacade是业务入口，Authority拥有精确资格与Host准备，模型任务通过ModelGateway。
- 本地记忆仅一条用户已提交交流的连续逐字片段，最多400字；明确选择来源，不从助手台词抽事实，不总结为人格。替换/停用面向具体依据，有版本与原子receipt；查询零模型。来源只证明用户说过该话。
- 活动模型提议action、plan、reason_code、basis_refs和当次decision_note≤160；引用仅本请求E1或空。Python核阶段/动作、逐字来源、实际plan变化、head和授权版本后提交。decision_note只作本地可见判断，不进入后续模型输入，不冒充隐藏推理或持久人格。
- 决策、活动结果及后续聊天保存本地source_dependencies。history-off、context cutoff、来源停用同时过滤依据及所有依赖产物/完整聊天轮；不能只删E1却从方案或旧回复送回。历史真实结果保持，失效结果整项不投影，不能清空refs伪造独立来源或退回unstarted。
- 单writer与原子Publication。prepared在claim后持久保存已裁决结果；冷恢复零新模型，已提交nonce只重取同一结果。无prepared的在途请求失败关闭；模型失败不写成角色受挫故事。错误身份、未知完整性、撤权竞态继续关闭。

## 出站准备及授权门槛

先完成LOCAL ModelGateway、接口、准确payload preview、离线行为和恢复验收，再冻结review digest与实际可审场景，集中请求一次新用途批准。此前真实产品请求为0；普通whole既有批准不自动覆盖活动或有据记忆。

候选仍限已审Sagiri30事实/4作者解释、现有DeepSeek/Windows slot，新隔离分支，用户手动推进一步：

1. 活动输入是人物最小投影、`shared_experience:{label:E1,quote≤400}|null`、`current_activity:{phase,allowed_actions}`和`current_plan:{subject≤160,composition≤800,focus≤400}|null`。首次plan为null；不发送两轮历史、事件、判断理由或本地标识。
2. 结果回聊保留既有主动文字≤1000/可关闭最多两完整轮≤4000/人物最小投影；新增同一条E1和一个`activity_result:{kind,plan}|null`。历史和来源依赖同时裁剪；不重复发送版本、摘要、差异或事件。
3. 每次用户发送/手动推进至多一个请求、0自动重试；按用途记录metadata，正文只留canonical。没有自动生活、主动分享/通知、Reflection、人格改写、云端或新凭据用途。

## 可观察验收与收口

离线先贯穿真实Facade：提交交流→选定逐字依据→至少三轮无关交流退出原窗口→关闭重开→活动判断/原子结果→下一轮读同一结果；并覆盖来源替换/停用、history-off/cutoff的派生过滤、错误身份、同nonce、prepared冷恢复和故障不产活动事件。合成模型通过只证明工程行为。

新用途获批后，在相同活动前态保留相关交流、无关交流、撤回或反向交流三支首次真实结果；观察实际方案与选择及其引用，核重启后回聊一致。引用E1或模型自述“受影响”本身不算因果证据；没有明显选择差异如实记未达，不挑好样本、不无限补抽。真实语义失败与协议失败分别记。

源码冻结后只读复核、必要检查、阶段commit/push。STATUS每次更新≤5行；交付写清实际改善、真实证据、未完成与下一步，不能将等待用途批准称为闭环已通过。
