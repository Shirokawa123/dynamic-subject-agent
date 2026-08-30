# Slice-02：Situated State 迁移

状态：done（2026-08-31 自动真实验收通过并收口）。规模预算：≤ 2 个工作会话。

## 目标

在同一 Windows 产品中形成一个有逐字证据、有限轮次和绝对到期时间的短时情境姿态。UI 显示 posture、remaining_turns 与 expires_at；每个 completed Experience 后确定性递减，过期后不再进入回复，关闭重开只恢复仍有效的状态。

## 规格来源

- 旧救援仓库 `situated_state.py`、`situated_state_policy.py` 与对应行为/仓储/ConversationService 测试，只迁移行为语义，不复制 legacy DTO、数据库或调用链。
- 新仓库 `SubjectState` Domain、TimelineOutcome、ModelGateway、ProviderAdapter、CredentialSlot 与桌面 projection 是唯一实现宿主。

## Provider 数据边界

沿用用户已授权用途：分类只发送当前用户消息、当前 Timeline 最多一个未到期 `{posture, remaining_turns, expires_in_seconds}` 与固定版本策略；回复只使用当前消息并附加本轮实际选中的一个 `{posture}`。不发送历史消息、Memory、Knowledge、Relationship、目标承诺、用户画像、内部 ID、数据库行、完整 provider 响应、raw chain-of-thought 或 API key；各能力投影保持分离。

## 实现范围

1. 随迁 posture 闭集、明确证据、刷新/替换、轮次衰减、绝对过期和命令拒绝规则。
2. 建立 provider-neutral Situated ModelTask、action-aware canonicalizer 与 DeepSeek Adapter；明确查询/过期由 Python 处理。
3. 将候选落入 SubjectState Domain；TimelineOutcome 原子保存变化、NoOp 或单项 FailedClosed，失败不终止无依赖的其他回复。
4. ApplicationFacade 提供 typed query/projection；桌面侧栏与轮次注释显示 posture 和剩余寿命。
5. fake 全链、provider 数据边界、崩溃/重启、对抗性输入、现有能力组合和全量回归。
6. 使用新的隔离产品身份和 project-original 消息完成真实 DeepSeek、Windows UI、关闭重开与过期验收；不读取或修改正式身份。

## 范围外

- Medium State、长期人格、情绪诊断、Agency、提醒、后台行为、effect。
- Situated 自动晋升 Medium、跨能力合并投影、隐式 provider fallback。
- 新 guard/mutation/证据 JSON/治理状态机/测试框架类别。
- 旧仓库、私人数据或正式身份的删除、迁移或修改。

## 验收

- legacy 行为语义随迁；用户直接命令角色状态不能成为证据。
- create/refresh/replace/noop、turn decay、wall-clock expiry、restart recovery 与原子失败可复核。
- JSON harmless noop 变体可规范化，状态变化格式仍严格；provider 失败只标记 Situated FailedClosed。
- 桌面真实旅程显示当前 posture 和寿命，过期后消失；全量测试绿并提交。
- 切片完成提交已 push 到配置远端；若 remote 尚未配置，则该项是唯一允许的收口阻塞。

## 收口结果

- 随迁 focused/gentle/cautious、set/carry/consume/noop、1 次 carry、30 分钟 TTL、replacement、逐字证据与 provider failure consume 语义。
- SubjectState/Timeline/ApplicationFacade/Windows UI 全链完成；直接“必须谨慎”命令被 Python 拒绝，JSON noop-null 可规范化，失败不终止其他回复。
- fake set→restart→carry→absent、桌面 projection、数据边界和对抗输入通过；全量回归 204 passed。
- 真实 DeepSeek 隔离身份完成 gentle set、关闭重开恢复、carry 消费；真实本地页面显示 `set · accepted · gentle`、剩余寿命和最终 neutral，无控制台错误。
- 正式身份、旧仓库和私人数据未读取或修改；临时验收目录已自动清除。
