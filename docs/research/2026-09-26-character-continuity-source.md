# 身份来源与对话连续性：S97开工依据

用户结果是关闭/重开后仍是同一个人物、能接上真实说过的话。S96已覆盖有用的单轮行为，但lab候选不持久化；v9也不是sealed identity。需要先准备真实身份来源及历史数据用途，不应把更多单轮分数当连续性。

## 现有仓库事实

Luna high只读定位、主窗口复核关键Interface：ApplicationFacade.submit→Host lease.admit→SubjectRuntime.admit→TimelineEngine.admit/原子publish，恢复由list_conversation_turns读取命令原文和已提交expression；这不是任意写两段文本的接口。CognitionEngine已有_bounded_noop_proposal可保持Domain状态不变，不必为了聊天增加第二store，也不能直接绕过Admission/Publication。

角色当前send只有lab内存，ModelPreview只读。已有source_draft/preview_source_freeze_mapping/freeze_source_identity，固定映射Profile/Genesis/Knowledge；freeze必须显式确认exact basis。进一步核对local_identity_authority._freeze_mapped_source_identity发现SourceDeclaration硬编码project-original，Studio PolicyKernel与isolation_proof也只支持project-original-only；因此小说派生定义只能复用纯内容映射，不能直接封存。将派生摘要重新标成原创不能解决来源冲突。

## 一手资料与适配

- [W3C PROV-DM](https://www.w3.org/TR/prov-dm/#term-Quotation)区分派生和直接引用，[Primary Source](https://www.w3.org/TR/prov-dm/#term-primary-source)要求可追溯到原来源。本次实际阅读这些章节；适配为明确标记“从已审核v9整理的派生定义”，不把自动汇总文字或它的evidence_quote伪称小说原文。保留v9/起点及派生文档指纹，供完整重建和复核；不引入RDF、图库或PROV运行时。
- [Clark与Brennan原文](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf)区分发出话语与足以继续交谈的理解证据。工程类比：已提交对话证明说过什么，不能自动证明其中自述/用户推断为世界事实，更不能自动升级信任。需要保留原文、纠错和界限，不以“接受了输入”宣称模型理解正确。
- 复用已有TimeChara与自我记忆系统研究：起点/获知边界必须保留，人的回忆/自我理论仅启发信息组织，不证明虚拟人物有心理体验。此次源映射本身是工程完整性工作，不新造心理状态字段。

没有引入外部代码、包或数据；因此当前无新增许可/维护依赖。放弃新chat store、绕过身份Authority、把原书全集作为每轮历史和把模型旧话直接写入Knowledge等路线。

## 本片决定和可观察验收

只实现确定性身份准备：由同一Facade验证v9及起点，生成明确标识派生的源文档/候选清单，保持所有纳入知识和限定，排除/待核项只做人类说明；提供仅限内容的Profile/Genesis/Knowledge mapping。旧save/freeze请求不可用。独立definition basis绑定reviewed-fiction-derived声明、private-character-chat用途及自持运行资料摘要；确认保持false。映射不等于保存/封存，本片不改来源权限、不调用保存或freeze。未采用直接适配旧封存，是因为会错误声称原创；新的来源路径需后续针对批准内容验证。

连续聊天另给具体方案：独立身份、本地canonical原文、每轮最多2个完整已提交对话轮且总4000字符进入同一DeepSeek规划/表达任务；历史只作说过的话，私人文件/其他身份/推理/数据库ID/时间戳均不外发。新用途须用户批准，200次数不替代。

验收以源变化/起点变化导致basis变化、名称/类型/时序/信念限定不丢、全部入选项覆盖、无未来/排除资料冒充知识、预览不写draft/registry/Timeline、不调用Provider为准；真实v9仅出可审预览。下一步批准后再沿既有identity Authority和Timeline接入，不提前宣称对话接续已实现。
