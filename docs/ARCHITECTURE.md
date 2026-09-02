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

Runtime identity 只进入六类 capability-local reply request，proposal/classification outbound 不含身份。Living Memory、Knowledge、Relationship 保留原 proposal outbound 并新增各自 reply task；identity reply 无效时退回同一 proposal 已验证的 identity-free reply，因此不反向改变候选、Domain Outcome 或 Timeline 写入。目标、Situated、Medium 保持既有两阶段失败语义。Python 的 identity-scoped expression guard 只删除无来源的第一人称当前活动句，不产生或改写状态。

明确的目标/承诺查询与闭集变化由 Python 直接处理，不调用模型。含糊输入才进入 ModelGateway；JSON Adapter 可对 `noop` 的 `null → 空值` 做 action-aware 规范化，但未知 action、越界引用、非逐字证据和非法状态转换仍拒绝。六项 state-bearing proposal/classification 或既有 required reply 失败形成所属 Domain 的 FailedClosed 片段；失败项不写状态，也不阻断无依赖能力。Living Memory/Knowledge/Relationship 的 identity reply 是 proposal 之后、不承载状态的可选 expression refinement；失败只回退该 proposal 已验证的 identity-free reply，不能取消候选或声称 identity grounding 成功。

## 数据

权威历史、当前状态和可重建投影分离。普通更正与遗忘只向前追加；Host 删除是独立治理行为。源码仓库不保存运行数据、凭据、私人来源或模型。

每轮 `ExperienceBasis.observed_at_us` 与 `ExperienceRecord.experienced_at_us` 来自同一 canonical Admission。新 Living Memory plan 或参与者目标/承诺只在消息含唯一受支持时间表达时附加 `TemporalAnchor`；旧记录不回填。离线时间只改变投影，不生成 Experience、状态转换、提醒或主动消息；Provider 仍只见原有 content/terms 字段，不见 timestamp、时区或 anchor 结构。

Interaction Recency 不持久化：明确查询从当前 Admission 与最近完整 TimelineOutcome 的 publication time 现场派生；pending、interrupted、FailedClosed 和 UI 20 轮窗口不参与。查询本身提交后就是下一次查询的最近 turn。非闭集消息不读取 history；四条闭集命中时六类 Provider 零调用，timestamp、日期差和历史文本均不外发。

桌面 HTTP/UI Adapter 只暴露可解释的内容、闭集状态和计数；canonical memory/revision/source ID、Timeline ID、profile ID 与 credential 不进入可见记忆卡或逐轮状态注记。

Dogfood conversation history 是 `TimelineEngine` 的只读投影：查询会重建完整 TimelineOutcome 链，验证每轮 plan/domain/Expression/outcome/receipt digest、previous digest 和最终 head，再只返回当前 identity 最近 20 个 `{head_sequence, user_text, user_language, assistant_text, assistant_language, published_at_us}`。`SubjectRuntime → RuntimeLease → ApplicationFacade` 只转发 typed projection；Desktop 不建第二份 transcript。pending、interrupted 与 FailedClosed 操作没有 TimelineOutcome，因此不显示为完成轮次。

逐轮因果解释只读取已提交 Outcome 的 typed status、reason、selected count 与当前可见投影，由 Python 确定性翻译为 changed/used/kept/failed 用户语言。普通 NoOp 不显示为变化；Relationship 声称拒绝、目标直接查询、Situated carry/直接命令和 Medium 证据门槛均不得由模型事后编写理由。

表达组合有独立于状态裁决的发言预算：Memory/Knowledge/目标形成非状态主干时，Situated 与 Medium 只提交 typed 结果而不追加重复回复；无非状态主干时 Situated 优先于 Medium，显式状态查询以其确定性 priority 覆盖普通 carry。未发言不等于 NoOp、Rejected 或失败，Domain Outcome 保持完整。

确定性裁决解释与主表达分离：Domain status/reason 由 Desktop 从已提交 Outcome 翻译为 explanation；主 `ExpressionCandidate` 不朗读“状态证据/短时姿态/中期基线/候选/裁决”等实现术语。Situated 直接命令仍由 Python 拒绝，但自然询问具体情境。关系直接声称按分句后的精确闭集由 Python 生成 deterministic `relationship_claim` NoUpdate candidate，过滤仅与声称分句重叠的 Memory evidence，并与同轮合法 Knowledge/目标表达合并；Provider failure 仍保持所属 Relationship FailedClosed。

## Credential seam

`CredentialStore` 是 Host 侧深 Module Interface，以 `{provider_id, account_id}` 的 `CredentialSlot` 读写；生产使用 Windows Credential Manager Adapter，测试使用内存 Adapter。桌面仅查询 configured/verified 状态，不能读取或回显 key。当前 DeepSeek 验证只访问 `/models`，不携带产品、角色或用户内容；无 Windows secure backend 时失败关闭。
