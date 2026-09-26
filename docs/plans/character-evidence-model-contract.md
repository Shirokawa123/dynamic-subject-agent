# 人物证据草稿与起点预览契约

该格式用于未封存的作者审阅，不是运行身份、聊天上下文或新的canonical store。输入是带人工核对结论的草稿；程序检查结构、引用和已给定判断，不能证明命题语义为真。

## 分层

- **指称对象**：人物、公开角色/笔名、作品、地点和目标。现实人物与公开身份的关联作为独立命题，带获知阶段；不能在名称归并时提前泄露角色尚未识别的身份。
- **证据**：原文件/文档/段落或HTML文本节点及hash、来源主线/IF分组、发言者。资料发言者不是经历主体，也不自动是角色知情者。
- **命题**：内容、涉及对象、关系、维度、事实/信念/观察归纳、知情者、成立阶段、获知阶段、依赖、审核状态和时间判断依据。
- **覆盖审核**：九个维度各自的已审状态与缺口。条目多不代表完整；无可用条目或仍有缺口的维度不能标成reviewed-adequate。
- **起点预览**：按指定主体/锚点筛选，保留包含/排除理由、知情/时间依据、依赖和可回指的证据表；不封存、不生成台词。

命题的event_time指这条背景、状态或信念何时成立，不是愿望所指未来目标的实现日期；knowledge_time独立说明角色何时获知。时间可before/at/after/unknown。直接证据与跨段关联推断分别标记，不要求每项合理本人认知都必须有逐字内心独白，也不把推断隐藏成直接引文。

## 预览规则

候选未审、非主线来源、观察归纳、其他人的认识视角、时间/知情待核、晚于起点或依赖未成立的条目不纳入。其他人知道并不证明目标角色不知道；未提供获知依据也只表示待核。来源位置/录入顺序不用于替代故事时间。

人物已知的一种错误信念可以以belief保留，不提升为世界事实。针对其他人的事实只要是目标角色已知，仍可进入；不能简单丢弃所有about不为本人的记录。未纳入关系涉及的指称对象不自动并入已知实体列表，避免通过元数据泄漏身份关联。

草稿、引用结构/对象、依赖环或证据完整性异常时整体failed-closed；缺本地文件时unavailable；正常预览为previewed，sealed_from_draft始终false。覆盖状态仍可能全部partial；previewed不代表人物已完整或可部署。

## Interface与运行范围

`ApplicationFacade.preview_character_model(CharacterModelRequest)`为唯一业务入口，普通产品默认unavailable。`open_character_model_preview`在独立目录经既有open_local_product装配Dormant环境，只附加只读作者预览；会创建隔离的空白承载环境，不将目标人物草稿封存或读取正式身份。

CLI接受显式草稿路径、来源目录、审阅digest、主体与锚点，不装配Provider。草稿变化需重新审阅digest；这只是本地一致性门槛，不是来源语义正确或用户批准模型外发的证明。

来源验证抽为共享Module，S60原有固定材料预览继续使用同一验证逻辑。支持真实段落定位和无p标签时的显式文本节点定位，不伪造段落编号。模型/语义提取未来只能产出未审候选，不能自动标reviewed或创建运行身份。

研究与取舍见[来源/时间研究](../research/2026-09-22-character-evidence-model.md)。未采用RDF库或引入图数据库；结构是否需要进一步深化，依据多卷覆盖和后续使用效果决定。

## Slice-69连续语境

同一预览入口接受CharacterContextRequest(subject_id, anchor_id, evidence_id, before=5, after=5)。各侧0–20个真实单位，单文档最多6000字符；完整单位超限拒绝，不静默截断。返回引用元数据、带原位置的相邻单位及文档边界。使用来源核验时的解析快照，不另行重读未核验正文。相邻文本的说话者、事件和人物知情仍需审核，窗口不保证覆盖完整场景。CLI以--context选择引用，--before/--after指定范围；本地读取不产生新增外发授权。

## Slice-71离线聊天上下文

Facade的preview_character_chat_context接受CharacterChatContextRequest(subject_id, anchor_id, current_message)，消息为非空字符串且最多1000字符。复用每次完整来源核验与起点判断；只取全部known的摘要、维度、kind、derivation和相对时间，不复制作者审查字段或实体标签。序列化知识超过20,000字符拒绝，不做部分人格回退。错误/损坏/关闭沿用明确结果。

新View附proposed-branch兴趣推荐/跨世界情境、披露和连续性约束，history_status=not-connected、provider_ready=false、can_chat=false；没有模型或canonical写入。CLI --chat-message与--context互斥。角色具体入口动机、私信时刻和可外发起点文字尚未确定，预览不是可直接发送的模型任务。

## Slice-72明确起点与相识

草稿可提供chat_stage_description（字符串<=500字符，不可全空白）；缺失/空字符串仍兼容作者预览，但聊天上下文unavailable/chat-stage-not-reviewed。该字段与草稿共同校验digest，禁止自动复制作者anchor.description。聊天View显示明确stage_description。Encounter包含助手提出的动机/时间安放，不升级为运行事实；PublicOpening仅由Encounter字段生成且status=proposed-branch，不从本人知识或消息提取私人信息。后续历史依赖和接续要求见[契约草案](character-history-integration-contract.md)，本片未实现历史。

## Slice-73回复候选

preview_character_reply通过已核验上下文生成CharacterReplyProjection六项白名单及请求digest；propose_character_reply需显式local CharacterReplyLab，默认unavailable，remote声明拒绝。单独CHARACTER_CONTEXT_REPLY任务不走旧角色Adapter。候选exact reply_text/language结构校验后仅标candidate/semantic_review=required，不写状态、不自动重试。CLI --reply-request只预览。此Lab无缓存/幂等会话承诺，不支持历史或真实Provider。

## Slice-78人物组织与按需装配

同一审核草稿可带`chat_organization`，exact顶层字段为version=`character-chat-organization-1`、subject_id、anchor_id、core、episodes、details。前三者绑定本草稿主体/起点；core非空，各组最多100项。单元包含id/title/content/claim_ids，可选cues；ID全组唯一，只引用本草稿经完整时间/知情/依赖筛选后仍适用的命题，不建立单元之间的第二依赖图。无组织继续旧预览；有组织但非法则明确FailedClosed，不通过flat绕过审核。内容语义正确仍由作者审阅负责，不由ID存在或摘要标签证明。

CharacterChatContextRequest增加context_mode=`auto|flat|organized`与max_knowledge_chars（真整数1–20000）。auto在有合法组织时采用组织，否则兼容平铺；显式organized缺配置返回unavailable。知识预算按最终self_knowledge紧凑JSON字符数计算，不是token数；核心全量常驻，超限拒绝，不截断核心凑预算。

相关经历/细节以明确线索及有门槛的中文二/三字或英文文本重叠排序，最多6个。只有单个偶然二字重叠不足以选入长消息的材料；显式线索和直接短词仍可命中。该算法是本地词法基线，不理解所有转述/否定。detail仅在正文与核心规范化后完全相同时省略，引用同一命题不代表细节内容重复。无匹配只保留核心，不声称不知道或库存为空。

组织内容仍进入原projection.self_knowledge六字段单元，dimension为core/episode/detail，保守保留belief与关联依据标记。组织policy补充选择范围/披露语义；flat保持既有projection和policy。两种请求的policy并不完全相同，后续实验若比较整套策略应说明这一点，若隔离组织因素须使用统一实验policy。

context.selection只供本地查看草稿指纹、知识字符数、单元/命题依据及选用/预算原因；reply projection不包含此诊断、cues、出处或ID。CLI沿原入口加--context-mode及--max-knowledge-chars。仍无远程调用、正式身份写入或历史输入。

## Slice-79冻结对照的独立执行门槛

新增独立CharacterContextTrial Producer，仍经Facade.preview/propose_character_reply，原CharacterReplyLab保持local-only。local_product准备/装配实验，CLI默认仅prepare。计划由同一Facade对12条固定消息分别flat/organized重建，共24项，使用统一TRIAL_POLICY；plan绑定草稿指纹、消息、请求/出站指纹、参数与保留范围。普通产品默认没有此Producer。

只有显式批准当前精确plan digest且重新准备一致时才装配既有DeepSeek Transport，credential仍延迟到发送。新Adapter仅接受计划白名单中的CHARACTER_CONTEXT_REPLY；max_tokens600、temperature0.3、非思考JSON、不流式，要求完整stop输出、zh和<=1200字符回复，不接状态提议。旧六能力及原试聊/提取授权不因此改变。

独立Git忽略实验目录按plan digest独占启动，发送前写入attempt并flush/fsync；同进程重复请求读取原结果，已启动计划重启不获得新Gateway，结果缺失/损坏返回unknown且不重发。来源、凭据、网络、输出或记录故障停止本批；预览不消耗远程调用。具体新数据用途以[真实对照批准方案](character-context-comparison-trial.md)为准，此文不是用户批准。

实验计划/结果不是正式聊天或第二角色canonical store，不改Memory/Relationship/生活状态。恢复保证限于此有界实验的“不自动重复请求”，不宣称远程模型调用普遍exactly-once或硬件断电绝不丢失。

## Slice-83独立依据审核与校准

内部CharacterReplyProducer收束不同候选来源，Facade仍使用preview/propose_character_reply，不增加公开步骤。原CharacterReplyLab仅可显式注入local审核Gateway；未配置时仍单次生成且semantic_review=required，remote审核不被借此开启。生成后构成独立CHARACTER_REPLY_REVIEW任务，输入是本人摘要(F标签)、阶段(S1)、原相识分支(I标签)、当前消息、候选正文及固定审核policy，移除生成policy/作者诊断；候选和用户消息均为数据。

审核返回verdict=supported/unsupported/uncertain与最多6项issues，每项exact quote/kind/basis_labels。quote必须是候选精确非空片段且<=240字符；类别闭集，标签只引用本请求可见F/S/I且不得重复。supported必须无issues，unsupported必须有issues；不确定不冒充已证伪。Python验证结构/定位，不能证明语义审核正确。

supported保留candidate正文，semantic_review标model-supported；unsupported/uncertain返回rejected、主reply_text为空，并带审核判定/有限问题片段供诊断。Provider/格式失败为failed-closed，安全凭据不可用保留unavailable；不自动改写/重试，不写canonical状态。

固定校准通过CharacterReplyReviewRequest(context_request,case_id)复用同一Facade：原资料重验后审核该case的冻结候选，不调用生成器。默认prepare；只有独立新用途的精确plan批准可装配审核Adapter。固定24项、deepseek-flash、600输出token、temperature0.0、非思考JSON，完整stop响应及65536字节上限检查。参考标签不作为输入。

生成试验和审核校准共用内部FrozenAttemptRun，旧生成审计字段保持；独占启动/发送前attempt/缓存及故障/重启不重发规则相同。校准中的supported/unsupported/uncertain都是正常完成，会继续剩余样本，只有基础/调用/格式/审计失败停止。新审核用途尚未获准，不能由S82已消费的48次覆盖。精确范围见[校准方案](character-reply-review-calibration.md)。

## Slice-85同题思考配置

S84后续已获准执行standard的24项校准，但明确反例误放8/11，因此不启用日常审核。新review_profile默认standard：继续24项、600输出、temperature0.0、非思考，原plan/字节不变。显式thinking-high只接受8项，绑定thinking enabled、reasoning_effort high、4096总completion预算、无temperature、JSON且不流式；计划增加明确profile，不借旧批准开启。

### Slice-87安全失败诊断

S86首项技术失败而无可用审核，不能解释为语义判断错误。新thinking-diagnostic严格1项，plan另绑定safe_diagnostics=true；生成参数及出站内容与thinking-high相同。诊断默认关闭，旧standard/high计划与公开失败码保持。

诊断只在传输/HTTP、响应信封、长度截断/预算、最终JSON及审核结构/引用阶段给出闭集码，经Adapter/Gateway/Candidate到既有审计。截断先于最终content解析；推理、异常原文、响应正文、headers及凭据不进入诊断结果。缓存只认可对应模式的闭集失败码，正常审核判定仍与技术失败区分；凭据不可用仍是unavailable。每个冻结计划故障即停、重启不重发，CLI不提供自动循环重试。

本地诊断通过不等于原真实故障已修复，也不恢复旧7项。追加诊断及必要修复验证依[新方案](review-failure-diagnostic.md)的单独授权；当前只准备首项，新增真实调用0。

仅该Adapter调用共享响应helper的discard_reasoning=True；参数必须bool，新分支最大4096，原默认最大2048且继续拒绝非空reasoning。新分支只允许None/字符串推理、原始usage整数；reasoning不返回、不作证据、不写审计或回传。最终content/完整stop/工具为空/模型/usage上限及审核结构仍核验，传输仍为30秒且响应<=65536字节。计划/输入/剩余额度规则沿原一次性机制，新的8次配置尚未获准，见[诊断方案](review-thinking-diagnostic.md)。
