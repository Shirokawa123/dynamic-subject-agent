# 产品架构

## 外部 seam

Presentation Adapter 只通过 `ApplicationFacade` 提交命令、等待结果和查询投影。`open_local_product(config, cognition=...)` 是唯一 production composition root，负责隐藏身份创建、Studio、QRI、RuntimeHost、provider Adapter、恢复和关闭顺序。

模型任务通过 `ModelGateway.execute(ModelTask)` 进入 provider-neutral seam。`ProviderAdapter` 声明 provider/model identity、本地/远程与 strict-schema/tool-call/json-object/text 能力；DeepSeek 只是当前生产 Adapter。运行中不做隐式 provider fallback。

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

明确的目标/承诺查询与闭集变化由 Python 直接处理，不调用模型。含糊输入才进入 ModelGateway；JSON Adapter 可对 `noop` 的 `null → 空值` 做 action-aware 规范化，但未知 action、越界引用、非逐字证据和非法状态转换仍拒绝。单项 provider 失败形成该能力的 FailedClosed，不阻断无依赖的其他 Domain 与表达。

## 数据

权威历史、当前状态和可重建投影分离。普通更正与遗忘只向前追加；Host 删除是独立治理行为。源码仓库不保存运行数据、凭据、私人来源或模型。

## Credential seam

`CredentialStore` 是 Host 侧深 Module Interface，以 `{provider_id, account_id}` 的 `CredentialSlot` 读写；生产使用 Windows Credential Manager Adapter，测试使用内存 Adapter。桌面仅查询 configured/verified 状态，不能读取或回显 key。当前 DeepSeek 验证只访问 `/models`，不携带产品、角色或用户内容；无 Windows secure backend 时失败关闭。
