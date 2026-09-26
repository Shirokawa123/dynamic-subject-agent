# 产品架构

2026-09-24 Slice-76进一步重推[目标方案](plans/global-product-architecture.md)：具体定义角色创作、持续相处、生活分享的权威、运行流程、有限活动与验收。整体方案尚未完成；S78–79已落实的组织/对照准备见下述契约，不能据此宣称持续相处与生活已实现。

## 契约适用范围（2026-09-20）

Slice-79新增独立冻结对照Producer和composition准备/开启入口，复用Facade回复方法；默认prepare只在本地生成24个精确请求与plan digest，原local-only Lab保持。当前无新外发批准、真实调用0；一次性启动、失败停止、恢复不重发及数据范围见[对照契约](plans/character-evidence-model-contract.md#slice-79冻结对照的独立执行门槛)和[待批准方案](plans/character-context-comparison-trial.md)。

Slice-78将审核草稿内的连贯核心/经历/细节接入现有Facade回复预览，支持auto/flat/organized、可追溯的本地选择与实际JSON字符预算；先按起点知情筛选再核组织依据，坏组织不静默降级。平铺兼容与local-only候选保持，未开放新远程用途。字段及有限词法选择见[人物组织契约](plans/character-evidence-model-contract.md#slice-78人物组织与按需装配)；组织接线不证明模型内容质量。

Slice-68实测后将语义候选提取限定为来源命题：模型不再输出知情者/成立阶段/获知阶段裁决，返回DTO中的这些字段由Python固定unknown，表示待审而非角色不知。按维度的固定策略与来源数据分开；本地审核后才能形成起点模型。响应诊断只可收集内容/结束状态/用量，不含鉴权、reasoning或tools。用户取消原3次跨轮上限仅覆盖同一组已授权原文，不扩大来源或自动重试；自动提取质量尚未通过。

Slice-67新增显式资料候选提取：Facade.extract_character_evidence→ModelGateway独立任务，只接受已审样本包、权利/用途确认和一次尝试；结构/逐字引用通过也固定为candidate，不能自动封存或进入起点认识。默认离线；新DeepSeek用途单独2048输出上限，旧identity路径保持400。实际原文外发仍待[具体试点方案](plans/character-evidence-extraction-trial.md)批准。

Slice-66新增只读作者预览`ApplicationFacade.preview_character_model`：从显式审阅digest的本地证据草稿核验来源与结构，按已审主体、成立/获知时间和依赖生成提议起点视图及覆盖缺口；不作语义真伪判断、不封存、不接Provider。与运行人物状态严格分开，详细格式见[证据模型契约](plans/character-evidence-model-contract.md)。

后续规划指引：用户在真实体验后明确要求连贯自我知识及根因修复，当前改造优先级见[第一性原则待办](plans/character-first-principles-backlog.md)。其F0–F8是待验证/待实施能力，不是新运行契约已生效；既有身份隔离、模型提议/Python裁决、Facade/Gateway及唯一Timeline继续成立，不由规划文档隐式扩大外发、持久化或迁移权限。

PRODUCT已转向角色聊天。本文顶部的“目标结构”和“原型隔离”描述后续设计约束，不表示新增生产能力；其后从“外部seam”开始保留dogfood-s51的已实现运行基线与历史切片契约。旧数据、binding、schema及Provider投影继续按旧契约运行，不能因文档目标更新自动升级。

### 新角色聊天的目标结构

- **来源与人物资料**：本地小说资产保留版本、卷章和出处，索引可重建。人物候选区分来源位置、事件时间、角色知情及适用阶段；原作资料不自动成为运行事实。
- **人物上下文选择**：区分起点背景、当前分支已发生的角色经历、实际共同聊天及用户自己的记录。先核对时间/知情/权限再检索，不能把完整Profile或多卷资料直接塞入现有三字段identity reply。
- **生活推进**：未来须使用与用户消息分开的明确输入，不能伪造用户发言触发旧Domain。只有通过相应裁决并提交的虚构事件才能作为此后生活分享的依据；真实时间流逝本身仍不是事件证据。
- **自然聊天编排**：将状态计算与表达形成分责，让回复围绕当前交流和可用人物经历组织。既有能力可复用，但不以多段能力台词拼接作为新的完整人物表达方案。
- **分享与投递**：区分事件成立、愿意/允许分享、允许开启话题及实际投递。日上限不驱动凑消息；投递要有身份隔离与去重。现有文本保存effect不授权消息通知。

ApplicationFacade仍为正式产品唯一业务Interface，open_local_product仍为production composition root。正式新路径保留Timeline唯一写权和原子Publication；新输入类型、生活事件/投递记录与投影的具体schema尚未定。不得另外建立可独立改写同一运行事实的store，也不借文档对齐就引入第二Agent框架的持久化。

### 独立原型的隔离

首份五情景原型是用于判断设计的临时演示，不是另一个生产composition root。它使用独立文件/工作区和内存中的模拟状态，不读取或写入正式registry/Timeline，不调用Credential或Provider，不发送系统通知。模拟时间、预设事件和台词显式标记；界面上的人物选择流程不得冒充自动小说分析。素材只可从用户明确提供的目录本地核对，小说全文与索引不进Git。

需要真正模型生成时，先完成具体用途、目的地、投影和预算方案并获授权，再建立相应任务书。原型代码留在独立原型分支，主线记录任务、证据与用户反馈；用户反馈之前不宣布原型体验通过。

### Slice-55：隔离角色对话的离线准备

`ApplicationFacade.character_dialogue_status/send`承载可选实验能力，普通产品默认unavailable。`local_product.open_character_dialogue_lab`仅在全新独立目录经`open_local_product`装配空白承载身份、Dormant cognition与独立会话；不读正式registry，不将承载身份信息传入人物摘要。实验会话是可丢弃的内存上下文，不是第二canonical store，也不提交ConversationTurn/Memory/关系/生活事件。关闭清空会话，不支持重启恢复。

`CharacterDialogueSession`在锁内裁决lab_id/revision/幂等、输入上限、历史控制和预算，再经新ModelTask类型调用Gateway；重复请求重放原结果，冲突与stale不外发；失败计尝试且不重试。最多20次尝试、2个完整成功轮/4000字符；控制/关闭历史会清空窗口，之后显式开启只积累新轮。输出必须是≤1200字符的typed中文reply，格式裁决不等于人物事实语义验证。凭据不可用返回unavailable，网络/输出故障返回failed-closed。

默认Adapter固定离线回声。真实Adapter复用既有单次DeepSeek Transport与JSON-envelope检查，但不复用旧用途授权；只有操作人显式传入当前计划digest才能装配，每进程最多一个真实实验，凭据延迟到发送时才读取。CLI真实路径目前只支持[待批准六条验收](plans/character-dialogue-live-trial.md)，失败即停；离线界面不开放真实发送。该参数不是用户批准的替代物。本片只完成离线验证，真实调用仍为0；旧12类请求保持原样。

### 旧假设如何过渡

Slice-62增加显式grounded角色实验，Session持有只读材料选择Module；在每次一次Gateway任务前核验并形成selected_character_material[{content}]（≤2项/400字符），路径/证据/ID不外发。匹配请求的来源缺失/不一致停止生成，未匹配仅用基础上下文。接受的失败尝试也计预算，幂等不重试。新策略/材料目录/规则/试聊范围形成独立digest，旧R2 None投影保持原字节。Facade的一次阶段切换要求精确8条固定消息全部成功，清空试验上下文、重新开启空白上下文、保留8次已用额度；之后最多12次，重复切换不再清空或补充预算。本片仅离线准备，真实用途与新增材料范围见[待批准方案](plans/grounded-character-chat-trial.md)。

Slice-61在同一材料预览Interface增加BasisMessageRequest，≤1000字符整句有限匹配，按具体问题缩小材料集合。未匹配no-op且不读来源，不代表没有相关经历；匹配后仍执行S60核验/排除规则。离线页面发送后自动请求预览，故障与聊天结果独立、旧响应不覆盖新结果；本片不增加模型字段或调用，不使用历史解决模糊指代。

Slice-60增加可选的只读`ApplicationFacade.preview_conversation_basis`。显式离线lab配置固定已审阅S59包与源目录，逐次核验pack/EPUB/文档/段落，再按六个显式话题最多选择2项/400字符并返回排除说明。默认unavailable；缺文件unavailable；来源不符failed-closed；无适用材料no-op。该Module没有模型、Timeline或事实写入Interface，不改变R2出站投影。话题映射为人工限定检查工具，非自然消息分类；预览可用也不表示角色已愿意分享或材料外发获准。

Slice-57离线修订：角色实验的character从单段字符串拆成固定背景、交流设定、表达建议、未知范围及固定空生活事件区，用户/模型原话不晋升事实；无事件写入入口。策略强调旧模型自述不能自证，允许当下观点但不补造既往习惯。此为来源区分与提示修订，非通用语义裁判，自由回复仍可能不实；R2尚未真实复核。新digest见[复核方案](plans/character-dialogue-r2-trial.md)，Slice-56旧批准的六次已消费，不能用于重跑。

旧路径的“离线时间不产生经历”仍有效；新路径拟将“明确推进后提交的虚构事件”作为新增经历来源，两者不混用。旧Situated/Medium要求用户消息证据的规则不自动扩成角色自己的心理模型；新来源和状态含义需明确设计。下文有限Knowledge/Memory语法与原有12类请求仍约束旧实现，新目标不隐式扩大其数据范围。

具体复用依据、未决项与渐进顺序见[架构对齐评估](plans/character-chat-architecture-alignment.md)。先验证隔离原型，再以独立切片接入最小真实生活闭环；旧身份迁移另议。

## 已实现的运行基线（dogfood-s51）

## 外部 seam

Presentation Adapter 只通过 `ApplicationFacade` 提交命令、等待结果和查询投影。`open_local_product(config, cognition=...)` 是唯一 production composition root，负责隐藏身份创建、Studio、QRI、RuntimeHost、provider Adapter、恢复和关闭顺序。

六项模型任务全部通过 `ModelGateway.execute(ModelTask)` 进入 provider-neutral seam。每个能力 Adapter 独立构造最小投影；`ProviderAdapter` 声明 provider/model identity、本地/远程与 strict-schema/tool-call/json-object/text 能力。DeepSeek 只是当前生产 Adapter，运行中不做隐式 provider fallback。

## 深 Module

- `SubjectRuntime`：一次 SubjectCommand 的唯一编排和写入授权者。
- `TimelineEngine`：Admission、幂等、Timeline head 与原子 Publication。
- `CognitionEngine`：有界输入、结构化候选与最终表达；没有持久写权。
- `Experience`：Observation、Claim、Evidence、Belief、Memory，以及现实参与者自己明确报告的目标/承诺；后者不是主体 Agency。
- `SubjectState`：Situated State 是一次 carry、30 分钟绝对过期的短时姿态；Medium State 是由最近 7 个已完成 Experience、双独立证据、2 轮冷却和闭集状态机裁决的中期基线。两层独立投影、独立持久化且不可自动晋升。
- `Agency`：Motive、Intention、Project、Commitment、ActionRequest。
- `Relationship`：Subject Stance、Interaction Norms、Mutual Commitment、Relationship Narrative。
- `SubjectStudio`：Genesis、Knowledge、封存和 QualifiedRuntimeInput。
- `LocalIdentityAuthority`：本地 identity registry、exact freeze/replay、active 选择、跨 Studio/QRI/Host/Timeline authority 校验与首次 Host/Timeline 准备。
- `PolicyKernel`：能力、访问、外发与反操纵政策。
- `TemporalGrounding`：以 canonical Admission 时间为唯一事实，将计划中的闭集相对日表达封存为 Civil Time anchor；canonical 原文不改写，当前 UI/Provider 只读投影按当天重渲染。
- `RuntimeIdentityProjection`：由 `LocalIdentityAuthority` 从当前 registry、QRI 与 sealed Genesis 校验后形成的三字段纯值；经 composition、RuntimeHost 与 SubjectRuntime 进入 CognitionRuntimeView，不建立第二个身份 store。
- `SubjectTimeContinuity`：单一 typed `evaluate()` Interface；仅命中四条闭集查询时惰性读取当前 identity 最近 committed publication，以本轮 canonical Admission 和固定上海日期返回 Answer/NoOp/FailedClosed。

## Experience Cycle

### Slice-49 主体任务协商

`ApplicationFacade.subject_task(SubjectTaskCommand, idempotency_key)` 是显式任务入口；普通聊天不推导任务。`SubjectTaskCognition` 只包装该intent，其他消息原样委托既有六能力。Agency Domain校验真实Admission与完整canonical任务快照；snapshot不符在Publication前FailedClosed。任务记录/闭集模型提议/最终回执进入同一Agency decision reason，重放再运行裁决比对，不建任务store。此阶段没有effect，accepted仅表示待处理，不代表成品生成或保存。

请求与修订消息≤1000字符，本地正文≤16000字符，整个JSON还受既有32768字符Admission上限约束；超限在提交前拒绝，正文不截断。非NFC字段在JSON内转义，以保留正文原字符与换行。每身份最多5项未结束任务，其中至多1项accepted；needs_input/deferred可重新提交，终态不能恢复。取消与stale操作不调用模型；失败/拒绝修订不覆盖原任务，accepted的降级修订也不覆盖。模型拒绝只在本地能核实不支持动作时成为declined，其余无依据拒绝为failed。闭集核实不等于通用意图识别。

新DeepSeek Agency提议经ModelGateway，每次有效显式请求/修订最多1次，只发送当前消息、固定目录/规则和≤5项未结束任务kind/summary/status（摘要各≤200字符）。修订排除自身旧摘要，避免把自己当竞争任务。本地正文、task_id、runtime identity、聊天历史与其他Domain数据不外发。任务轮在聊天投影中只显示“主体任务操作”和最终回执，不成为近期对话外发来源。

新身份binding持久化`subject-task-cycle-1.0`，闭集映射授权chat和subject-task-v1；旧`m0-a-cycle-1.0`只保留chat。读取/恢复/导出必须由binding版本派生权限，不信任任意gate内容；未知版本失败关闭。此处不迁移旧binding、不改旧Timeline schema/effect约束。桌面任务草稿仅在当前页面内按身份分别保留；提交绑定身份、目标revision和幂等key。完整执行和旧身份升级尚未实现。

### Slice-50 精确文本effect

后续新身份使用`subject-text-effect-cycle-1.0`，额外授权`confirmed-text-save-v1`并新建Timeline schema 2；control schema仍为1，旧Timeline及binding不迁移。v2允许真实Agency eligible及单个ready effect引用，仍沿用Publication原子提交；旧v1只允许空effect。`TextSaveApproval`绑定task revision与preview basis，basis包含policy、root/身份、正文原字节摘要、完整正文和精确目录/文件名。只接受当前accepted且正文非空的任务；stale、已取消、跨身份或旧contract批准不执行。

`ApplicationFacade.preview_text_artifact`纯读取；`approve_text_artifact`提交唯一intent，任务转executing，不能再修订/取消。确认无模型调用。本地目录固定canonical root/artifacts；目标名固定，冲突不偷偷换名。File Adapter先exclusive创建暂存、flush/fsync，再用同卷hardlink新建目标。已有目标只有与本次暂存samefile且exact bytes相同才认作恢复成功；独立同内容文件、部分暂存或链接路径失败且不覆盖/删除。暂存硬链接保留，不建立第二权威数据store。支持进程中断恢复，不声称对任意文件系统/硬件断电提供超出底层的保证。

同一Timeline SQLite追加终态effect_receipt，包含effect/outcome引用及digest、head sequence、结果、正文摘要与文件名；receipt chain与单独count/head摘要同事务提交，尾删、错序、孤立及引用不符FailedClosed。重放在对应intent之后应用completed/failed；缺receipt的intent只能是最后一个Outcome，否则拒绝后续历史。Domain模型不产生receipt。Runtime在有permit的worker上，于admit和resume/freeze前、Publication后恢复；文件成功而receipt未提交时不会重写目标。纯查询、预览、导出或治理冷启动不dispatch。已冻结attempt只在当时head继续，旧basis不会借新receipt继续生成。

导出读事务中核实完整任务/receipt链，并包括实际Timeline schema、receipt和head。`recover_text_artifacts`是显式恢复入口，旧contract返回unavailable；下次提交也先恢复。产品不开新后台调度，关闭程序后不承诺继续运行。历史completed与文件现在是否仍在/是否被外部改动分开；任务面板给出原保存位置。既有聊天创作可由用户明确选择后贴为本地正文，本切片不新增任务生成Provider用途。

`ApplicationFacade → Admission → bounded Cognition → Domain adjudication → grounded Expression → atomic TimelineOutcome → post-commit effect`

模型输出只能成为候选。Domain 独立返回 accepted、rejected、NoOp 或 FailedClosed；完整 Outcome 全可见或全不可见。effect 只消费已提交引用，失败不会重跑经历。

文本来源预览也只经 `ApplicationFacade`，但不伪装成 SubjectCommand：`ApplicationFacade → TextSourceCharacterAuthoring → ModelGateway → Python candidate adjudication → ephemeral preview`。该 Module 没有 Studio publish/freeze、Timeline 或 Runtime 写权；未确认权利/用途时 Provider 零调用，刷新页面即丢失预览。

用户确认本地保存后，候选进入 SubjectStudio root 内独立的 `source-character-draft` sidecar；现有 ProfileStore schema 不迁移。sidecar 只允许一个 active draft，原文与候选 basis 固定，选择变化 append-only revision，stale base 冲突；query 不回显原文或内部 ID。每条 HTTP 命令在当前请求线程按 StudioRootRef 打开/关闭 SubjectStudio，SQLite connection 不跨线程持有。显式删除级联清除 draft/revisions，保留空 schema manifest。

Freeze Mapping 是 Source Draft 的纯 Python、只读投影：identity→Profile identity core，identity+trait→Genesis subject identity，origin+voice+“尚无运行时经历”→canon start，初始关系固定为空白新关系，selected Knowledge 独立映射。Freeze Basis 绑定 source digest、draft revision、mapping policy 和全部映射内容；mapping preview 不调用 seal、不写 ProfileStore/snapshot/QRI/Timeline。

Source Identity Freeze 仍只经 `ApplicationFacade`：`LocalIdentityAuthority` 让 SubjectStudio 在写前重读 Source Draft 完整 revision 链并重算 exact basis，以 basis 派生稳定的新 Studio/Profile/draft/snapshot/QRI identity。ProfileStore schema v2 在 KnowledgeSnapshot 内封存最多 6 条有摘要的 member；v1 root migration-free 兼容读取，只有旧 `local-product-deepseek-qri-v1` 可使用代码内 fixture。identity registry 原子保存多个隔离 authority 与 active selector；首次选择才创建该身份自己的 Host/Timeline。切换重组 production composition 并清空 Presentation 会话 DOM，不复制或合并 Timeline。QRI 已发布但 registry 未写可幂等恢复；已封存 snapshot 可由同一 exact PolicyQuestion 的新 PolicyDecision 恢复 QRI 发布。`local_product` 不解析 registry 或编排 freeze/select，只消费 Module 返回的已验证 active authority 来装配 cognition 与 ApplicationFacade。

Runtime identity 只进入六类 capability-local reply request，proposal/classification outbound 不含身份。Living Memory、Knowledge、Relationship 保留原 proposal outbound 并新增各自 reply task。Slice-19 用户批准 Living Memory/Knowledge 的正常与基础回退表达接受同级校验，基础回复不合格时使用安全本地表达，不能反向取消合法候选、改变 Domain Outcome 或 Timeline 写入。Relationship 仍退回同一 proposal 已验证的 identity-free reply；目标、Situated、Medium 保持既有两阶段失败语义。表达检查不产生或改写状态。

Knowledge reply 返回 `reply_kind/source_quotes/reply_text/language`：source/unknown 的 quote 必须与本次已选条目的 title 和完整原句匹配；可见事实展开到所匹配条目的完整上下文，保留跨句否定/条件，不能用 citation accepted 证明自由改写。无效或失败的 refinement 回退到同一候选所选 sealed 原文；无来源时给自然的未知答复。creative 仅在本地明确请求检查通过时显示为当前创作，引用说明为创作背景。

Living Memory reply 返回 `reply_kind/reply_text/language`：conversation、creative、activity 与 Slice-30 的 memory 均不承载状态。自由回复的正常与 base fallback 经过同一 context-aware 检查；明确活动询问使用本地真实能力边界，不把 elapsed Civil Time 说成离线经历。memory 自由正文不显示，见下述 Slice-30 契约。模型标签不能豁免本地检查。`ExpressionCandidate.is_creative` 仅为 cognition 本地核准的临时表达元数据，不进 Provider 或 canonical Expression；只有已标明的创作文本才可保留为创作，不因同轮出现某个创作分句就放开事实文本。

Slice-30 在既有 LM reply 的三字段响应中增加 `reply_kind=memory`，只细化原用户记忆/安排回答用途，不增加请求数据、历史、调用或新 Provider。类型有效且 Memory action=none 时，Python 根据实际已传入 reply 的最多 5 条可披露选中记录形成完整原文引用；不自由推断日期或要求重新确认。空选择只说明暂时无法确定，披露失败/未决限制使用已有无法核实范围说明，不推断事件未发生、未安排或已经停用。该类型 reply_text 可为空，即使非空也忽略其自由正文；它不是来源证据或状态提议。

memory 误用于本轮 create/revise 时只确认收到说明，不假称保存成功或把旧记录当新状态；活动、提醒、无来源事实、创作/续写/编号修改及 exact 状态边界仍优先。`ExpressionCandidate.is_memory_answer` 是本地临时组合标记，不持久化、不外发：保留与完整 Knowledge 引用并列的记录/未知说明，相关目标附带回复只呈现 selected canonical terms；关系声称的早期表达替换及后续关系/Situated/Medium 合并均保留已标记的完整依据，不把引用内的否定条件当自由未知句删掉。关系/状态候选仍由原 Domain 裁决，标记不赋予状态写权。选择错误仍可能引用无关记录，不证明相关性。若模型误标为 conversation 或没有返回有效类型，仍走既有自由表达/fallback 契约；不宣称解决所有误分类或生成失败。其他 11 类请求保持原字节基线，详细失败与验收见 [Slice-30 报告](reports/2026-09-09-slice-30/REPORT.md)。

Slice-22 在既有 Living Memory reply 提示内区分提供题材、已明确讨论、事实询问与创作，字段/用途/历史窗口/调用预算不变。模型返回的 creative 被本地拒绝且无有效基础回复时，只诚实报告本轮表达未完成；不能从模型生成失败推断用户意图不清，也不能把无 Memory 变化解释为当前消息无内容。有效基础回复、合法状态候选、sealed 来源与显式状态查询保持原有优先级；本地失败表达复用临时 dialogue_priority，不增加状态。该回退本身不算承接成功，须以真实后续对话验证。

Knowledge 与 Memory 同轮合并时，非创作 Memory 表达只引用当前用户原话或已校验的 canonical recalled 内容，不夹带该能力自由生成的 Knowledge 事实。已有目标/姿态/中期表达优先级继续执行；含 Knowledge 的后续合并把来源与记忆引用作为完整证据保留，不做未知句剥除或近似去重。检查只覆盖有界契约和明确语法，不等于对任意自然语言真实性的证明。

明确的目标/承诺查询与闭集变化由 Python 直接处理，不调用模型。含糊输入才进入 ModelGateway；JSON Adapter 可对 `noop` 的 `null → 空值` 做 action-aware 规范化，但未知 action、越界引用、非逐字证据和非法状态转换仍拒绝。六项 state-bearing proposal/classification 或既有 required reply 失败形成所属 Domain 的 FailedClosed 片段；失败项不写状态，也不阻断无依赖能力。Living Memory/Knowledge/Relationship 的 identity reply 是 proposal 之后、不承载状态的可选 expression refinement；失败按上述能力本地规则回退，不能取消候选或声称 identity grounding 成功。

## 数据

Slice-47在当前唯一编号修改中提取有限直接“别/不要用〔配对引号字面短串〕”约束，只校验指定替换句，不改未指定句、不继承历史禁词。直接错误引号或违规/错标签输出走原修改失败，不删词凑合或额外重试；引用/条件/转述及不明间隔分句不提升为当前约束。Provider模板/字段/预算及canonical schema不变，见[报告](reports/2026-09-18-slice-47/REPORT.md)。

Slice-46让完整旧新目标和命名目标共享不变安排尾句判定：有限1–24字中英文/数字主体加“照带”，不再枚举物件名；主体不是新安排或存在性证据，Memory不因此改变。明确条件/否定/操作、多尾句与引号仍拒绝；当前命名操作的非法引号尾句保留在拒绝路径，不落回普通Memory写入。Provider/历史/唯一目标契约保持，见[报告](reports/2026-09-18-slice-46/REPORT.md)。

Slice-45将句首明确“第N句我想/希望/请更…一点”等有限风格反馈接入原编号修改，保留引用/条件/撤回、多目标与最新安全原稿边界。既有LM reply仅对该当前意图附指定句的新版本指示，字段/历史/调用预算和其他11类请求不变；正文仍由Python局部重组。初次真实原样复述失败与风格质量限制见[报告](reports/2026-09-18-slice-45/REPORT.md)。

Slice-44在Memory候选裁决复用引用遮蔽和原文位置，拒绝摘录丢失引用所在原文单元、有限转述前缀或条件前缀。引用内部标点不切断来源，保留后置说话者；不猜重复摘录对应哪次出现。完整保留归属的原文、独立当前自述及既有exact偏好旧新原文更正仍可用，更正参数判定由共享接缝提供，目标/库存仍由Domain核验。Slice-38确认例外不变，不合成原文、不清洗旧Memory。仅本地证据检查，无Provider模板/字段/用途/预算或canonical schema变化；支持范围及真实NoOp/拒绝区别见 [Slice-44报告](reports/2026-09-17-slice-44/REPORT.md)。

Slice-42把“给〔场景〕挑颜色时，我〔通常〕〔也〕喜欢/偏爱〔颜色〕”及“〔最近〕〔场景〕用〔颜色〕也不错，我拿不准/不确定这算/是添一种/补充还是换掉原来的/替换”的有限当前表达接入原场景路由和Slice-38确认。未决新颜色不直接保存，无可靠旧场景需完整重述；原文和来源/确认ID分别保留。Timeline从既有确认回执派生本地preference_confirmed，查询/替换共用recorded_preference，旧未确认文本不因新解析器升级成确定偏好。无持久schema或Provider字段变化；复杂旧尾句、未知库存、引用/条件/撤回、下一轮/30分钟及重启限制保持。详见 [Slice-42报告](reports/2026-09-17-slice-42/REPORT.md)。

Slice-41将直接创作前的“那就”规范化，并在既有编号修改动作前接受“再”，复用同一创作许可、两句检查、最新安全稿件与局部替换路径。当前重贴后连续修改和重启仍依赖canonical历史；“别再提”等原控制不豁免，多目标/引用/条件/撤回不获新许可。不改Provider模板、字段、用途、历史窗口或调用预算；新识别的明确两句请求使用已有LM当轮格式指示。无新增稿件store；见 [Slice-41报告](reports/2026-09-17-slice-41/REPORT.md)。

Slice-40在当前消息增加带原文跨度的Goal command解析，供本地路由、Domain与Memory分工共享。仅去定位“换个话题：”“说正事：”“（诊断对照）”等明确前缀后的直接自述，不改写Admission；逗号前为当前第一人称会/准备/打算/要的安排（支持有限当天/明后天/周几及上下午时间词）时，“也给自己定个/一个目标”可继承当前主语，条件或混合限定不据此执行。完整“把目标〔配对引号旧条款〕改成/改为/换成〔配对引号新条款〕”绑定当前完整active库存唯一旧条款；省略目标二字仅在旧条款逐字命中已有目标时适用，不将普通改稿自动当目标。引号是操作参数，不能从转述/条件里截取为指令。尾部仅接受安排/计划保持不变或椅子/工具/材料/点心照带，其他尾句拒绝。Memory按同一完整消息跨度扣除操作，独立连续安排原文可保存；截取的命令证据须匹配完整消息中的直接命令及绝对位置，目标失败不授权Memory覆盖安排。原完整库存、同轮多命令、撤回与Provider投影/提示/预算不变，无跨轮状态依据扩展；见 [Slice-40报告](reports/2026-09-13-slice-40/REPORT.md)。

Slice-39扩展当前明确目标操作：“我也给自己定个/一个目标：…”与“〔名称〕这个/这项目标我想/希望改成/改为/换成〔内容〕”。名称须在完整active目标库存的条款，或当前修订记录的逐字修改证据中唯一匹配；未知/重名不猜测，不建立永久别名或通用历史指代。后附“不变”仅支持裸安排/计划、原有/原来/其他/其它/别的限定，以及我/我们/朋友/同事/家人来或一起吃早午晚餐、聚餐、见面、出游的安排/计划；不认识、条件或其他变化须分开说明，不能截掉后执行。Memory扣除完整明确目标操作及受支持不变说明，独立连续安排原文仍可保存；拒绝的混合修改不能借Memory改写。目标本地读取最多100条active，达到上限或完整性未知时拒绝变化，Provider仍仅用原20条窗口和原字段/提示/调用预算。最终成功回执读取实际Outcome，原完整消息/引用/撤回约束保持；见 [Slice-39报告](reports/2026-09-13-slice-39/REPORT.md)。

Slice-38用户明确批准限定偏好澄清例外：原声明提供内容、下一短答在30分钟内提供选择，二者以canonical问题引用绑定，Python重新核对身份、冻结前缀、完整库存和权限后一次Publication。待确认片段只存原Timeline，不新建store或向Provider发送历史状态依据；普通Memory仍要求当前逐字证据，原隐私控制保持。取消/换话题/过期/未知/重复不能复活旧问题。具体字段与验收见 [设计](reports/2026-09-13-slice-38/DESIGN.md)。

Slice-37将当前自然共同写作框架接入既有许可/原稿/编号修改：协作前缀规范化后复用原创作和句数检查；“我…写了/写的N句：引号原稿”与原文声明统一计数，只在唯一可用时编辑。当前原稿多份/不足/格式不可用不得回退旧历史；编号动作与当前句目标绑定，引用/假设不作指令。用户明确保留“别再提”等原历史控制，因此独立验收第14原样仍受限，需要当前重贴后修改，不加入措辞例外。Provider字段、用途、历史预算与状态权限不变；自然目标及短答澄清未扩展。见 [Slice-37报告](reports/2026-09-13-slice-37/REPORT.md)。

Slice-36对完整明确颜色偏好句提供本地场景路由：场景按字面匹配，当前可解析active记录完整引用；无关场景/无场景颜色不混入，同场景普通偏好多值不按时间猜替换，显式“也喜欢”与唯一基准并存。新颜色无补充/更正意图先澄清；简单“场景改用颜色”仅对唯一无其他尾句记录revise，复杂/多条需要完整旧新原文。库存/披露不明不答颜色或更正，裸补充不借历史推断场景。Domain在目标证据收窄后复核最终写入依据，并使用能力本地preference_memories canonical完整active快照及真实完整性；Provider/recall原20条窗口不变，缺快照不能证明唯一性。没有新store、模型字段/用途/调用阶段，旧史保留；非闭集句式、颜色别名和多意图仍有限。见 [Slice-36报告](reports/2026-09-13-slice-36/REPORT.md)。

Slice-35仅将结构完整的五类已知目标局部失败解释为“没有Memory revision”：无Memory片段、exact Goal failed-closed/noop/reason_code、受限顶层字段与experience-1.0版本同时满足才成立；未知/额外/不匹配结果仍unknown。其后原identity、完整性、冻结basis、pending、控制与预算检查不变，目标消息仍不进入历史，未扩大recent_dialogue用途。编号修改只替换同一已授权作品的指定句：接受单替换句或同句数完整稿，保留其他原句及段落，重组全文再检查；无对应句数或未变明确失败。历史按原首段稿件契约，当前完整重贴不套首段截断，不新建稿件store。见 [Slice-35报告](reports/2026-09-13-slice-35/REPORT.md)。

Slice-34在ExperienceDomain完成原逐字、ID、动作和kind校验之后，按共享的既有目标/承诺闭集语法与完整引用跨度限定Memory写入依据。仅处理无逗号的明确操作分句：候选中扣除这些操作后只剩一段连续原文才保存；纯操作为Memory NoOp，多段、重复定位不明或有限依赖限定残余为rejected，不拼接/改述。引用/假设与逗号复合结构不据此裁切，目标成败不授权Memory替换独立安排。旧混合历史不迁移，用户明确Memory更正仍正常追加；Provider输入、调用、历史用途和原消息Admission不变，回执读取最终内容。该有限分工不等于通用事实/目标语义分库，详见 [连续体验对照](reports/2026-09-13-slice-34/REPORT.md)。

Slice-33 以完整消息的引用跨度为先，再提取逐字直接陈述供既有目标闭集路由和Domain证据检查使用；句号/分号/换行支持目标分句位于前中后，不从逗号后提升条件或转述。嵌套/未闭合引用保守遮蔽，完整消息仍裁决撤回、多操作和目标选择。创作许可、两句数量和多份歧义共用当前请求解析，新增写两句/2句与一版两句短诗；多份要求不猜一份，未生成作品明确说明。创作及其失败不以Memory写入为前提，Goal最终确认保留已核准作品；Knowledge仍仅在最终accepted时保留自己的作品。既有事实、活动、提醒和控制边界不解除，含目标/显式记住的历史仍不进入recent_dialogue；当前重贴完整原文可用原编号修改契约。详见 [设计](reports/2026-09-13-slice-33/DESIGN.md)。

Slice-33用户另行明确批准DeepSeek返回标识兼容。官方2026-09-10已将旧deepseek-v4-flash请求临时路由至V4.1-Flash；请求模型字段仍保持原值，响应只接受deepseek-v4-flash与deepseek-flash两个精确值，其他响应校验不放宽。不是模型权重保持不变的声明，也不接受任意后缀/未来型号；无新Provider、凭据用途、请求字段或预算。详见 [官方依据及复现](reports/2026-09-13-slice-33/PROVIDER-COMPATIBILITY.md)。

Slice-32 的 `memory_write_receipt` 在原有express阶段读取最终Experience Outcome形成新增/更正/拒绝/失败/NoOp回执，与完整Outcome一起原子Publication后可见。确认只引用actual living_memory_content，memory_revision区分更正，不采用模型提前成功台词，不改变候选裁决或旧历史。CognitiveProposal的memory_write_requested/memory_continuation/knowledge_continuation仅为本地临时组合信息，不持久化、不外发；纯写入压下自由改述，已检查的当前创作或明确独立问题另行保留。独立问题无效refinement不恢复base；Knowledge事实仍由完整来源路径负责，Goal覆盖确认时保留已检查独立Memory表达或最终Knowledge accepted的独立作品，其他能力失败不取消Memory成功。作品在首段、回执单独后置，历史重复比较只取原有首段稿件，当前输出计数不截段。仅LM reply提示细化“不提前确认写入”，字段/历史用途/调用预算及其他11请求字节不变。真实“写两句”组合请求仍未被既有创作识别器接受，作品丢失及后续无稿件失败保留，不能宣称所有独立意图稳定保留。详见 [Slice-32设计](reports/2026-09-09-slice-32/DESIGN.md) 与 [真实报告](reports/2026-09-09-slice-32/REPORT.md)。

Slice-31 的 `memory_subject` 为完整单个指名安排查询提取当前字面对象（有限句式见任务报告/设计），不猜控制、引用/转述、建议、代词/时间指代开头和多问题消息。Runtime 从已读active记录的有限动作/变更槽位提取单一完整对象，按完整名称比较后使用既有20条排序预算；允许一个有界文稿类别后缀的无歧义简称，不将带类别的名字再次缩为另一对象简称。多个完整名或不可解析结构不猜测；Cognition外发前复查并保留披露过滤。模型返回ID必须属于实际候选，明确查询提出create/revise或越界ID形成Memory FailedClosed。有效proposal后Python复用原文/未知渲染，错误类型/可选reply失败或legacy自由文本不允许另挑对象。12类提示、字段、调用上限均不变，不使用forgotten文本作候选，不增加索引或实体状态；有限名称槽位不等于通用语义识别，任意别名/复合陈述仍有限。见 [Slice-31设计](reports/2026-09-09-slice-31/DESIGN.md)。

Slice-29 的 `memory_retrieval.select_memory_candidates` 从 Runtime 已恢复的最多 100 条 Living Memory 历史中只取 active。超过 20 条时，以当前消息和当天内容投影在一次性内存 SQLite FTS5 中按 BM25 排序后取最多 20 条；不足预算的槽位按原最近顺序补齐，20 条以内或无词面匹配时保持原窗口。中文使用通用连续双字片段、英文/数字使用词元；无题材词表、embedding、额外 Provider 或持久索引，原内容、ID、状态与 canonical 历史不改写。排序仅决定候选，模型仍选择引用，Python 仍裁决；它不证明相关性、唯一性或语义等价。

候选窗口与完整控制库存分开，exact 状态仍查 canonical 原文；姓名查询保持原有候选窗口不可确认时的本地安全回复，不因为全库存存在姓名就让未收到姓名的 Provider 自由回答。撤回/披露过滤在外发前继续执行，superseded/forgotten 不进入排序。FTS 不可用返回 typed `MemoryRetrievalUnavailable`，Runtime 只标记本轮 Memory 检索不可用；完整清单、撤回和 exact 状态仍可本地处理，其他 Memory 请求在 Provider 之前产生所属 `living-memory-retrieval-unavailable` FailedClosed，包括姓名查询，不把检索失败说成空库存，不影响独立能力。12 类 Provider 的提示/字段与调用预算不变，仅溢出时 Memory 候选成员/次序及其选中内容可能不同。100 条之外、无共同词元、纯指代和模型窗口内错选仍有限；详细对照见 [Slice-29 报告](reports/2026-09-09-slice-29/REPORT.md)。

权威历史、当前状态和可重建投影分离。普通更正与遗忘只向前追加；Host 删除是独立治理行为。源码仓库不保存运行数据、凭据、私人来源或模型。

Slice-23 Logical Forgetting 由 MemoryControl 本地选择唯一姓名/昵称完整记录或 exact「原文」，ExperienceDomain 对完整 admitted command 与本地库存再次校验，向原 canonical Outcome 追加 forget 结果；Timeline 只派生 `forgotten` 状态，不删除旧记录或改写旧 Timeline。控制库存完整性与 Provider 的 20 条 active 投影分离；100 条历史窗口无法证明完整时拒绝猜测。`memory_withdrawal_status` 只用于裁决后确认与当轮/历史说明，accepted 不再被 UI 说成新建记忆。

未提交的撤回意图按该操作冻结前缀定位，仅限制后续 Memory/近期历史披露，不伪装为 canonical 停用；未知/混合 pending 会保守限制，不能自动解封或说已完成。纯保留/引用与真实控制区分，引用对象不消除外部控制动词。读取失败与真实 pending 分开说明。已停用记录不进入 active 投影，修订链不得复活其内容；用户重新直接报告可建立独立新记录。明确清单与缺失姓名查询可本地回答，只说明当前可用范围，不声称用户从未提供过信息。完整有限语法见 Slice-23 任务书，物理删除和跨 Domain 数据治理不在此实现内。

每轮 `ExperienceBasis.observed_at_us` 与 `ExperienceRecord.experienced_at_us` 来自同一 canonical Admission。新 Living Memory plan 或参与者目标/承诺只在消息含唯一受支持时间表达时附加 `TemporalAnchor`；旧记录不回填。离线时间只改变投影，不生成 Experience、状态转换、提醒或主动消息；Provider 仍只见原有 content/terms 字段，不见 timestamp、时区或 anchor 结构。

Interaction Recency 不持久化：明确查询从当前 Admission 与最近完整 TimelineOutcome 的 publication time 现场派生；pending、interrupted、FailedClosed 和 UI 20 轮窗口不参与。查询本身提交后就是下一次查询的最近 turn。SubjectTimeContinuity 对非闭集消息不读取 history；四条闭集命中时六类 Provider 零调用。Slice-21 另授权 Living Memory reply 的有界近期文本用途，timestamp、日期差仍不外发。

Slice-21 仅 Living Memory reply 可使用 `recent_dialogue`：从本轮冻结 basis 对应的当前 identity canonical Timeline 惰性派生最多两轮完整 user/assistant 文本、总计 4,000 字符，不建立新 store。历史读取/权限/完整性不明确或更正遗忘边界无法证明安全时退回无历史；历史只影响当前回复，不进入 proposal/classification 或 Domain 状态依据。详细窗口和控制截断规则见 [Slice-21](slices/slice-21-recent-dialogue.md)。

整条明确“把上一句/刚才那句改短/缩短”的有限句式只提供上述安全窗口中的最新完整轮，避免把更早话题提供为改写对象。Slice-25 增加“能/可以/请…缩到/缩短到/改短到 N 个字以内”（1–99，中文整数或十进制），允许当前评论加独立直接限字请求，也仅取最新完整轮；其他指代保持原两轮上限，控制/修订/权限/完整性边界不变。没有安全前文或最近回复仅为拒绝/澄清时请用户贴出原句，不跳回更早话题。

配文与续写共用当前请求作用域：引号中的命令和有限过去转述句不成为许可，全文明确撤回优先，风格“别写成/别写得”不取消独立写作。明确续写与最近 assistant 正文完全重复时拒绝 refinement；计数/比较复用受控正文规范化，剥离受控创作前缀与一对外引号（包括引号内的旧前缀），不改写原历史。限字按非空白 Unicode 字符计，标点计入；超限或未形成新版本诚实说明，不截断或增加模型重试，合法状态候选仍独立。LM reply 仅补充同用途计数提示，其他11类请求字节不变。不做语义相似度、通用自然语言许可或风格质量保证，有限句式详见 Slice-25。

桌面 HTTP/UI Adapter 只暴露可解释的内容、闭集状态和计数；canonical memory/revision/source ID、Timeline ID、profile ID 与 credential 不进入可见记忆卡或逐轮状态注记。

Dogfood conversation history 是 `TimelineEngine` 的只读投影：查询会重建完整 TimelineOutcome 链，验证每轮 plan/domain/Expression/outcome/receipt digest、previous digest 和最终 head，再只返回当前 identity 最近 20 个 `{head_sequence, user_text, user_language, assistant_text, assistant_language, published_at_us, outcome_summary}`。`ConversationOutcomeSummary` 从当轮 verified Outcome 派生 typed status/action/reason、已接受记忆内容、选中计数与 citation 引用；兼容旧纯文本 reason。`SubjectRuntime → RuntimeLease → ApplicationFacade` 只转发 typed projection；Desktop 不建第二份 transcript。pending、interrupted 与 FailedClosed 操作没有 TimelineOutcome，因此不显示为完成轮次。

逐轮因果解释只读取当轮已提交 Outcome 的 typed summary，由 Python 确定性翻译为 changed/used/kept/failed 用户语言；citation 标题通过当前身份 sealed Knowledge 解析。当前与历史轮次复用同一说明投影，下一轮、刷新和重启恢复时一并显示；不能用今天的 Memory/目标卡反推过去。旧主回复保留原文，即使与当轮失败说明矛盾。普通 NoOp 不显示为变化；Relationship 声称拒绝、目标直接查询、Situated carry/直接命令和 Medium 证据门槛均不得由模型事后编写理由。

目标/承诺操作主确认在既有 `CognitionEngine.express` 裁决后阶段由最终 Experience Outcome 确定：accepted 才确认成功，rejected/FailedClosed/no-candidate 不复用模型成功台词；无关目标故障只留说明，保留独立主表达。精确目标查询（包括空列表）直接读取 canonical 记录。自然创建与命名修订见上述Slice-39限定扩展；原命名修订路径仍匹配旧 terms，受限“写X→X写完”允许原报告写作句，其他意译不猜测，多目标需要可唯一核实的明确对象。Domain 检查整条 admitted message 的混合闭集命令与撤回，不能被截短 evidence 绕过；Provider policy/字段不变。

表达组合有独立于状态裁决的发言预算：Memory/Knowledge/目标形成非状态主干时，Situated 与 Medium 只提交 typed 结果而不追加重复回复；无非状态主干时 Situated 优先于 Medium，显式状态查询以其确定性 priority 覆盖普通 carry。未发言不等于 NoOp、Rejected 或失败，Domain Outcome 保持完整。

确定性裁决解释与主表达分离：Domain status/reason 由 Desktop 从已提交 Outcome 翻译为 explanation；主 `ExpressionCandidate` 不朗读“状态证据/短时姿态/中期基线/候选/裁决”等实现术语。Situated 直接命令仍由 Python 拒绝，但自然询问具体情境。关系直接声称按分句后的精确闭集由 Python 生成 deterministic `relationship_claim` NoUpdate candidate，过滤仅与声称分句重叠的 Memory evidence，并与同轮合法 Knowledge/目标表达合并；Provider failure 仍保持所属 Relationship FailedClosed。

## Slice-24 有限事实表达边界

Living Memory 的 conversation 只承接主观讨论、澄清和不引入外部事实的建议；既有 reply 提示按此收紧，其他 11 类请求字节基线不变。Python 对明确物理因果/材质辨识与未知材质且担心损坏的输入给出有限边界，正常、fallback、FailedClosed 和最终组合均不能恢复已拒建议。合法 Memory 候选仍独立提交，确认引用最终 canonical 内容；事实场景的目标附带表达只引用选中 canonical terms，关系回执不能为整段自由建议背书。

完整封存 Knowledge 引用保持原文；未知原物的约束不因引用存在而消失，资料引用不等于能直接用于当前物件。Knowledge 失败明确说查询未完成。创作只豁免自身分句；冒号故事范围在硬句界结束，独立答问及其引用保持约束，主观比喻/语言点评不按科学解释处理。有限语法不是通用语义分类或事实核验：复杂多句虚构可能被保守处理，明确虚构仍可能写入未核验的类科学内容，必须保留创作标记。真实证据见 [Slice-24 报告](reports/2026-09-08-slice-24/REPORT.md)。

## Slice-26 共同创作交付与恢复

明确“给我一版…短句/祝福/文案/短诗”按当前直接请求处理，继续应用引用、过去转述和撤回边界。Memory 的已核准创作不以 Memory 状态变化为发言前提；与封存来源同轮时保留创作及完整来源，两能力都创作时仅选 Memory 一稿、Knowledge citation 仍提交并可见。Knowledge 使用已有本地 `is_creative` 标记，不进入 Provider 或 canonical Expression。

有限“第一/二/三句我想/请保留/改成/换成/改为”修改仅取最新安全轮；只把受控创作前缀之后的首段计为稿件，排除受控来源尾注、空白及后续独立段落的状态/资料说明。该格式判断是保守文本定位，不是通用文稿解析；多段作品或不明所指要求用户贴原文。当前明确 `原文是：「完整文本」` 的单份引号原文可供同一编号请求使用，不能将原文里的命令当新许可；未提供足够句子与提供后生成失败使用不同本地提示。两种恢复说明都不会被背景来源覆盖。

“不要再提”等控制仍关闭历史；用户当前重贴的文本可作为当前消息处理，不恢复旧历史、不建草稿store。直接索要一版两句祝福/短句时，两句要求只绑定该请求分句，背景提及和单句修改不推导数量；对最终过滤后的正文检查，conversation 标签不豁免。LM reply 在既有 system 提示内细化两句、并在上述明确请求时附当轮两行格式指示，只由当前消息派生；其余11类请求字节保持不变，调用预算/字段/历史范围不变。详情与真实失败见 [Slice-26 报告](reports/2026-09-08-slice-26/REPORT.md)。

## 明确目标与承诺清单（Slice-51）

Slice-51混合验收修复明确清单入口：“列出/请列出我的目标/承诺”、四条完整的目标和承诺合并询问走已有Python只读路由；合并结果标明最多显示5条。最终表达读取同一canonical完整库存投影，不回退到20条Provider窗口；完整性不可证时说明未能核实，不冒充空库存。引用、转述、条件和混合消息不因包含查询子串命中；不新增写动作或Provider投影，目标分类/reply零调用，其他能力保持原调用契约。

## 提醒表达边界（Slice-27）

当前没有可承诺的定时或下次聊天自动提醒契约，参与者目标 Domain 已将提醒列为范围外。有限直接未来提醒、设置/取消请求及能力询问由本地明确说明边界；记忆确认读取最终 Outcome，accepted 才引用已记录原话，FailedClosed 明确未完成记录，NoOp/召回不当新建。该确认不产生提醒任务、主体承诺或触发器。

六项候选的自由表达在各能力组合前检查未来提醒/设置成功等声称，合法状态候选不因此取消。豁免仅限所属能力已核准创作；Knowledge 本就渲染完整封存来源，引用不按主体承诺删改。当前明确引用解释、canonical 用户/记忆/目标引用作为独立片段保留，不让一个片段豁免后续自由回复。提醒请求中的目标附带表达只引用 canonical terms。最终提醒边界与独立事实/关系/状态/目标结果并存，不被另一条边界覆盖。

即时回顾用户未来计划不是未来提醒动作，时间词需修饰提醒动作而非被回顾的内容；明确故事中的台词不当现实请求。上述为有限中文语法，不保证识别所有措辞。12类 Provider 的字段、提示字节基线及调用预算均不变。旧错误台词与本地记录不清洗；自由回忆对全体库存的错误断言仍是独立缺口，见 [Slice-27 报告](reports/2026-09-08-slice-27/REPORT.md)。

## 记忆回答范围（Slice-28）

非精确的有限活跃记忆状态询问只回答本轮已核实的选中范围：无选中不等于全库存空，有选中不等于必定命中所指；不可读/控制不明确时不判断空库存或停用。LM非创作中直接全库存/从未提供的否定不能靠空选择成立。原有完整清单仍由Python在完整可读前提下回答；生成失败与读取/选择失败不混同。

`「完整原文」记录现在活跃吗？` 等有限exact语法在本地唯一、安全匹配时只答active/forgotten/superseded状态，不回显旧内容。Runtime把同次已读取的原始tuple作为 `canonical_memory_history` 供此匹配，日期渲染的living_memory_history仍用于既有显示/投影。没有额外IO、store或Provider用途；不可完整确认/有未决控制时不猜测。精确路由和组合保护共用同一匹配器，Goal只引用自己的canonical terms，独立来源/事实边界不覆盖Memory范围。

有限语法不是通用实体匹配；相似题材可能选到其他记录并要求确认。完整真实证据及限制见 [Slice-28 报告](reports/2026-09-08-slice-28/REPORT.md)。

## Credential seam

`CredentialStore` 是 Host 侧深 Module Interface，以 `{provider_id, account_id}` 的 `CredentialSlot` 读写；生产使用 Windows Credential Manager Adapter，测试使用内存 Adapter。桌面仅查询 configured/verified 状态，不能读取或回显 key。当前 DeepSeek 验证只访问 `/models`，不携带产品、角色或用户内容；无 Windows secure backend 时失败关闭。
