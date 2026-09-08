# 产品架构

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

`ApplicationFacade → Admission → bounded Cognition → Domain adjudication → grounded Expression → atomic TimelineOutcome → post-commit effect`

模型输出只能成为候选。Domain 独立返回 accepted、rejected、NoOp 或 FailedClosed；完整 Outcome 全可见或全不可见。effect 只消费已提交引用，失败不会重跑经历。

文本来源预览也只经 `ApplicationFacade`，但不伪装成 SubjectCommand：`ApplicationFacade → TextSourceCharacterAuthoring → ModelGateway → Python candidate adjudication → ephemeral preview`。该 Module 没有 Studio publish/freeze、Timeline 或 Runtime 写权；未确认权利/用途时 Provider 零调用，刷新页面即丢失预览。

用户确认本地保存后，候选进入 SubjectStudio root 内独立的 `source-character-draft` sidecar；现有 ProfileStore schema 不迁移。sidecar 只允许一个 active draft，原文与候选 basis 固定，选择变化 append-only revision，stale base 冲突；query 不回显原文或内部 ID。每条 HTTP 命令在当前请求线程按 StudioRootRef 打开/关闭 SubjectStudio，SQLite connection 不跨线程持有。显式删除级联清除 draft/revisions，保留空 schema manifest。

Freeze Mapping 是 Source Draft 的纯 Python、只读投影：identity→Profile identity core，identity+trait→Genesis subject identity，origin+voice+“尚无运行时经历”→canon start，初始关系固定为空白新关系，selected Knowledge 独立映射。Freeze Basis 绑定 source digest、draft revision、mapping policy 和全部映射内容；mapping preview 不调用 seal、不写 ProfileStore/snapshot/QRI/Timeline。

Source Identity Freeze 仍只经 `ApplicationFacade`：`LocalIdentityAuthority` 让 SubjectStudio 在写前重读 Source Draft 完整 revision 链并重算 exact basis，以 basis 派生稳定的新 Studio/Profile/draft/snapshot/QRI identity。ProfileStore schema v2 在 KnowledgeSnapshot 内封存最多 6 条有摘要的 member；v1 root migration-free 兼容读取，只有旧 `local-product-deepseek-qri-v1` 可使用代码内 fixture。identity registry 原子保存多个隔离 authority 与 active selector；首次选择才创建该身份自己的 Host/Timeline。切换重组 production composition 并清空 Presentation 会话 DOM，不复制或合并 Timeline。QRI 已发布但 registry 未写可幂等恢复；已封存 snapshot 可由同一 exact PolicyQuestion 的新 PolicyDecision 恢复 QRI 发布。`local_product` 不解析 registry 或编排 freeze/select，只消费 Module 返回的已验证 active authority 来装配 cognition 与 ApplicationFacade。

Runtime identity 只进入六类 capability-local reply request，proposal/classification outbound 不含身份。Living Memory、Knowledge、Relationship 保留原 proposal outbound 并新增各自 reply task。Slice-19 用户批准 Living Memory/Knowledge 的正常与基础回退表达接受同级校验，基础回复不合格时使用安全本地表达，不能反向取消合法候选、改变 Domain Outcome 或 Timeline 写入。Relationship 仍退回同一 proposal 已验证的 identity-free reply；目标、Situated、Medium 保持既有两阶段失败语义。表达检查不产生或改写状态。

Knowledge reply 返回 `reply_kind/source_quotes/reply_text/language`：source/unknown 的 quote 必须与本次已选条目的 title 和完整原句匹配；可见事实展开到所匹配条目的完整上下文，保留跨句否定/条件，不能用 citation accepted 证明自由改写。无效或失败的 refinement 回退到同一候选所选 sealed 原文；无来源时给自然的未知答复。creative 仅在本地明确请求检查通过时显示为当前创作，引用说明为创作背景。

Living Memory reply 返回 `reply_kind/reply_text/language`：conversation、creative、activity 均不承载状态。正常与 base fallback 经过同一 context-aware 检查；明确活动询问使用本地真实能力边界，不把 elapsed Civil Time 说成离线经历。模型标签不能豁免本地检查。`ExpressionCandidate.is_creative` 仅为 cognition 本地核准的临时表达元数据，不进 Provider 或 canonical Expression；只有已标明的创作文本才可保留为创作，不因同轮出现某个创作分句就放开事实文本。

Slice-22 在既有 Living Memory reply 提示内区分提供题材、已明确讨论、事实询问与创作，字段/用途/历史窗口/调用预算不变。模型返回的 creative 被本地拒绝且无有效基础回复时，只诚实报告本轮表达未完成；不能从模型生成失败推断用户意图不清，也不能把无 Memory 变化解释为当前消息无内容。有效基础回复、合法状态候选、sealed 来源与显式状态查询保持原有优先级；本地失败表达复用临时 dialogue_priority，不增加状态。该回退本身不算承接成功，须以真实后续对话验证。

Knowledge 与 Memory 同轮合并时，非创作 Memory 表达只引用当前用户原话或已校验的 canonical recalled 内容，不夹带该能力自由生成的 Knowledge 事实。已有目标/姿态/中期表达优先级继续执行；含 Knowledge 的后续合并把来源与记忆引用作为完整证据保留，不做未知句剥除或近似去重。检查只覆盖有界契约和明确语法，不等于对任意自然语言真实性的证明。

明确的目标/承诺查询与闭集变化由 Python 直接处理，不调用模型。含糊输入才进入 ModelGateway；JSON Adapter 可对 `noop` 的 `null → 空值` 做 action-aware 规范化，但未知 action、越界引用、非逐字证据和非法状态转换仍拒绝。六项 state-bearing proposal/classification 或既有 required reply 失败形成所属 Domain 的 FailedClosed 片段；失败项不写状态，也不阻断无依赖能力。Living Memory/Knowledge/Relationship 的 identity reply 是 proposal 之后、不承载状态的可选 expression refinement；失败按上述能力本地规则回退，不能取消候选或声称 identity grounding 成功。

## 数据

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

目标/承诺操作主确认在既有 `CognitionEngine.express` 裁决后阶段由最终 Experience Outcome 确定：accepted 才确认成功，rejected/FailedClosed/no-candidate 不复用模型成功台词；无关目标故障只留说明，保留独立主表达。精确目标查询（包括空列表）直接读取 canonical 记录。自然创建仅支持当前用户直接“我给自己定个目标：…”；命名修订须匹配旧 terms，受限“写X→X写完”允许原报告写作句，其他意译不猜测，多目标仍需完整旧 terms。Domain 检查整条 admitted message 的混合闭集命令与撤回，不能被截短 evidence 绕过；Provider policy/字段不变。

表达组合有独立于状态裁决的发言预算：Memory/Knowledge/目标形成非状态主干时，Situated 与 Medium 只提交 typed 结果而不追加重复回复；无非状态主干时 Situated 优先于 Medium，显式状态查询以其确定性 priority 覆盖普通 carry。未发言不等于 NoOp、Rejected 或失败，Domain Outcome 保持完整。

确定性裁决解释与主表达分离：Domain status/reason 由 Desktop 从已提交 Outcome 翻译为 explanation；主 `ExpressionCandidate` 不朗读“状态证据/短时姿态/中期基线/候选/裁决”等实现术语。Situated 直接命令仍由 Python 拒绝，但自然询问具体情境。关系直接声称按分句后的精确闭集由 Python 生成 deterministic `relationship_claim` NoUpdate candidate，过滤仅与声称分句重叠的 Memory evidence，并与同轮合法 Knowledge/目标表达合并；Provider failure 仍保持所属 Relationship FailedClosed。

## Slice-24 有限事实表达边界

Living Memory 的 conversation 只承接主观讨论、澄清和不引入外部事实的建议；既有 reply 提示按此收紧，其他 11 类请求字节基线不变。Python 对明确物理因果/材质辨识与未知材质且担心损坏的输入给出有限边界，正常、fallback、FailedClosed 和最终组合均不能恢复已拒建议。合法 Memory 候选仍独立提交，确认引用最终 canonical 内容；事实场景的目标附带表达只引用选中 canonical terms，关系回执不能为整段自由建议背书。

完整封存 Knowledge 引用保持原文；未知原物的约束不因引用存在而消失，资料引用不等于能直接用于当前物件。Knowledge 失败明确说查询未完成。创作只豁免自身分句；冒号故事范围在硬句界结束，独立答问及其引用保持约束，主观比喻/语言点评不按科学解释处理。有限语法不是通用语义分类或事实核验：复杂多句虚构可能被保守处理，明确虚构仍可能写入未核验的类科学内容，必须保留创作标记。真实证据见 [Slice-24 报告](reports/2026-09-08-slice-24/REPORT.md)。

## Credential seam

`CredentialStore` 是 Host 侧深 Module Interface，以 `{provider_id, account_id}` 的 `CredentialSlot` 读写；生产使用 Windows Credential Manager Adapter，测试使用内存 Adapter。桌面仅查询 configured/verified 状态，不能读取或回显 key。当前 DeepSeek 验证只访问 `/models`，不携带产品、角色或用户内容；无 Windows secure backend 时失败关闭。
