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
- `PolicyKernel`：能力、访问、外发与反操纵政策。

## Experience Cycle

`ApplicationFacade → Admission → bounded Cognition → Domain adjudication → grounded Expression → atomic TimelineOutcome → post-commit effect`

模型输出只能成为候选。Domain 独立返回 accepted、rejected、NoOp 或 FailedClosed；完整 Outcome 全可见或全不可见。effect 只消费已提交引用，失败不会重跑经历。

文本来源预览也只经 `ApplicationFacade`，但不伪装成 SubjectCommand：`ApplicationFacade → TextSourceCharacterAuthoring → ModelGateway → Python candidate adjudication → ephemeral preview`。该 Module 没有 Studio publish/freeze、Timeline 或 Runtime 写权；未确认权利/用途时 Provider 零调用，刷新页面即丢失预览。

用户确认本地保存后，候选进入 SubjectStudio root 内独立的 `source-character-draft` sidecar；现有 ProfileStore schema 不迁移。sidecar 只允许一个 active draft，原文与候选 basis 固定，选择变化 append-only revision，stale base 冲突；query 不回显原文或内部 ID。每条 HTTP 命令在当前请求线程按 StudioRootRef 打开/关闭 SubjectStudio，SQLite connection 不跨线程持有。显式删除级联清除 draft/revisions，保留空 schema manifest。

Freeze Mapping 是 Source Draft 的纯 Python、只读投影：identity→Profile identity core，identity+trait→Genesis subject identity，origin+voice+“尚无运行时经历”→canon start，初始关系固定为空白新关系，selected Knowledge 独立映射。Freeze Basis 绑定 source digest、draft revision、mapping policy 和全部映射内容；mapping preview 不调用 seal、不写 ProfileStore/snapshot/QRI/Timeline。

明确的目标/承诺查询与闭集变化由 Python 直接处理，不调用模型。含糊输入才进入 ModelGateway；JSON Adapter 可对 `noop` 的 `null → 空值` 做 action-aware 规范化，但未知 action、越界引用、非逐字证据和非法状态转换仍拒绝。六项单项 Provider 失败都形成所属 Domain 的 FailedClosed 片段，与其他候选一起进入同一个原子 Outcome；失败项不写状态，也不阻断无依赖的其他 Domain 与表达。

## 数据

权威历史、当前状态和可重建投影分离。普通更正与遗忘只向前追加；Host 删除是独立治理行为。源码仓库不保存运行数据、凭据、私人来源或模型。

桌面 HTTP/UI Adapter 只暴露可解释的内容、闭集状态和计数；canonical memory/revision/source ID、Timeline ID、profile ID 与 credential 不进入可见记忆卡或逐轮状态注记。

逐轮因果解释只读取已提交 Outcome 的 typed status、reason、selected count 与当前可见投影，由 Python 确定性翻译为 changed/used/kept/failed 用户语言。普通 NoOp 不显示为变化；Relationship 声称拒绝、目标直接查询、Situated carry/直接命令和 Medium 证据门槛均不得由模型事后编写理由。

表达组合有独立于状态裁决的发言预算：Memory/Knowledge/目标形成非状态主干时，Situated 与 Medium 只提交 typed 结果而不追加重复回复；无非状态主干时 Situated 优先于 Medium，显式状态查询以其确定性 priority 覆盖普通 carry。未发言不等于 NoOp、Rejected 或失败，Domain Outcome 保持完整。

## Credential seam

`CredentialStore` 是 Host 侧深 Module Interface，以 `{provider_id, account_id}` 的 `CredentialSlot` 读写；生产使用 Windows Credential Manager Adapter，测试使用内存 Adapter。桌面仅查询 configured/verified 状态，不能读取或回显 key。当前 DeepSeek 验证只访问 `/models`，不携带产品、角色或用户内容；无 Windows secure backend 时失败关闭。
