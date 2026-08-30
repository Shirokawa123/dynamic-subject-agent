# 产品架构

## 外部 seam

Presentation Adapter 只通过 `ApplicationFacade` 提交命令、等待结果和查询投影。`open_local_product(config, cognition=...)` 是唯一 production composition root，负责隐藏身份创建、Studio、QRI、RuntimeHost、provider Adapter、恢复和关闭顺序。

## 深 Module

- `SubjectRuntime`：一次 SubjectCommand 的唯一编排和写入授权者。
- `TimelineEngine`：Admission、幂等、Timeline head 与原子 Publication。
- `CognitionEngine`：有界输入、结构化候选与最终表达；没有持久写权。
- `Experience`：Observation、Claim、Evidence、Belief、Memory，以及现实参与者自己明确报告的目标/承诺；后者不是主体 Agency。
- `SubjectState`：Situated、Medium 与长期主体状态。
- `Agency`：Motive、Intention、Project、Commitment、ActionRequest。
- `Relationship`：Subject Stance、Interaction Norms、Mutual Commitment、Relationship Narrative。
- `SubjectStudio`：Genesis、Knowledge、封存和 QualifiedRuntimeInput。
- `PolicyKernel`：能力、访问、外发与反操纵政策。

## Experience Cycle

`ApplicationFacade → Admission → bounded Cognition → Domain adjudication → grounded Expression → atomic TimelineOutcome → post-commit effect`

模型输出只能成为候选。Domain 独立返回 accepted、rejected、NoOp 或 FailedClosed；完整 Outcome 全可见或全不可见。effect 只消费已提交引用，失败不会重跑经历。

## 数据

权威历史、当前状态和可重建投影分离。普通更正与遗忘只向前追加；Host 删除是独立治理行为。源码仓库不保存运行数据、凭据、私人来源或模型。
