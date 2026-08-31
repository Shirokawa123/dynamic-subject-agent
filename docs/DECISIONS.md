# 当前决定

## D-001：建立独立产品仓库

2026-08-30，用户决定结束学习/救援仓库阶段，在 `E:\dynamic-subject-agent` 建立唯一未来产品主线。旧仓库保留为只读历史和未迁能力规格来源，不删除、不运行时依赖、不自动回退。

## D-002：保持 mature 单时间线架构

保留单写入者、原子 Publication、四 Domain、模型提议/Python 裁决和 provider 最小投影。产品抽取不等于重新发明架构。

## D-003：按产品缺口推进

当前已有能力冻结维护；目标与承诺、Situated State、Medium State 完成后，以六项既有能力同轮整合和隔离身份长链验收收口当前最小产品。Agency、effect、人格发展、Reflection 与主动消息等待新的明确授权。历史治理流程、学习计划和证据生成体系不进入新仓库。

## D-004：软件内管理 DeepSeek credential

2026-08-30，用户确认由桌面软件配置 key。生产只使用 Windows Credential Manager，不使用仓库文件、SQLite、环境变量持久化或明文 fallback；“保存并验证”只对 DeepSeek `/models` 发 Bearer 鉴权请求。

## D-005：模型能力与产品语义解耦

2026-08-30，用户要求未来可接入其他云端或本地模型。所有含糊任务经 provider-neutral ModelGateway 和能力声明进入 Adapter；明确产品语法由 Python 直接处理。JSON mode 不被视为 schema 保证，只有无语义差异的 action-aware 规范化可在 Adapter 内执行；Provider 单项失败不再自动终止整轮。

## D-006：Situated State 为一次 carry 的短时姿态

2026-08-31，迁移 focused/gentle/cautious 闭集：set 当轮使用并保留 1 次下一完成轮 carry，绝对 TTL 30 分钟；replacement、consume 与 expiry 只向前记录。Provider 只提议，包含“必须”的直接命令不能成为证据，失败消费旧状态但不终止整轮。

## D-007：Medium State 由独立经历证据裁决

2026-08-31，迁移 settled/concerned/encouraged 闭集：Provider 每轮只从当前消息提议 concern、encouragement 或 settling signal，Python 以最近 7 个已完成 Experience、至少 2 条独立逐字证据、2 轮冷却和旧证据不可复用规则裁决转换。直接状态命令不构成证据；失败保持既有 baseline 且不终止整轮。

## D-008：六项能力原子组合且故障局部化

2026-08-31，六项能力各自通过 ModelGateway 与独立最小投影提出候选；组合层只合并候选、typed failure 和有依据的表达，四个 Domain 独立裁决后由单写入者一次 Publication。Memory、Knowledge、Relationship 与目标/Situated/Medium 一致：Provider 故障形成所属能力 FailedClosed，不携带候选、不写该项状态，也不取消其他无依赖能力。

## D-009：以隔离 Windows 长链收口当前最小产品

2026-08-31，仅使用新临时身份和 project-original 文本完成真实 DeepSeek 长链、关闭重开和 Windows 页面验收。Memory、Knowledge、Relationship、目标、Situated carry 与 Medium 双证据均可解释；页面不显示 canonical memory ID，credential 仅由 Windows Credential Manager 供生产 Transport 使用。该验收不扩大为正式身份迁移或新能力授权。

## D-010：先提高既有能力可辨识度，不建立统一表达层

2026-08-31，短暂体验“仍像普通聊天”先作为可辨识度证据处理。逐轮说明由 canonical Outcome 和 Python 生成，不新增 Provider 数据用途；明确无关的目标输入走本地 NoOp，直接状态命令由 Python 拒绝，显式目标查询隔离无关 Memory/Knowledge 表达。高相似回复只做确定性去重；通用对话表达与更深表达校准仍需后续独立决定。

## D-011：状态裁决与状态发言分离

2026-08-31，真实流程证明 Situated 与 Medium 分别生成完整回复会重复，且局部 Provider 无法知道其他能力已说什么。组合层因此采用确定性发言预算：非状态主干存在时状态不追加；状态独占时 Situated 优先，显式 Medium 查询可覆盖普通 carry。六项仍分别裁决并原子提交，不新增统一表达任务或跨能力 Provider 输入。
