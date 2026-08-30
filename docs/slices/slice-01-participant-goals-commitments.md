# Slice-01：参与者目标与承诺迁移

状态：done（2026-08-30 用户真实桌面验收通过并收口）。规模预算：≤ 2 个工作会话。

## 目标

用户在桌面聊天中明确说出“我的目标是……”或“我承诺……”后，系统以逐字证据和 Python 裁决形成一条参与者目标/承诺；后续可明确修订、达成、放弃、履行或解除，历史只向前追加，关闭重开后仍可查询并用于有界回复。

## 领域归属

这是现实参与者对自身目标与承诺的有来源记录，归 `Experience` 管理；不是主体的 `Agency`，不是 `Relationship.MutualCommitment`。本切片不开放角色侧承诺、共同承诺、提醒、计划执行、后台行为或 effect。

## 随迁规格

- 迁移旧救援仓库 `goal_commitment.py`、`goal_commitment_policy.py` 与 `tests/test_goal_commitment.py` 的行为语义，不复制 legacy persistence、DTO identity 或调用链。
- 每轮至多一个计划；create/revise/transition/noop 闭集；goal 状态为 active/achieved/abandoned，commitment 状态为 active/fulfilled/released。
- evidence 与 terms 必须逐字出现在当前用户消息；重复、未知目标、歧义目标、普通计划、提醒、角色/共同承诺全部拒绝。
- 修订创建新记录并 supersede 旧记录；状态变化只接受用户明确报告，不冒充外部事实验证。

## Provider 数据边界

沿用用户已授权的既有用途：分类阶段只发送当前用户消息、最多 20 条 active `{turn_ref, kind, terms, status}` 和固定版本策略；`turn_ref` 仅本轮有效。回复阶段使用当前消息且只附加本轮 Python 实际选中的最多 5 条 `{kind, terms, status}`。两阶段不发送历史消息、Memory、Knowledge、Relationship、其他 Domain 状态、内部持久 ID、数据库行、完整 provider 响应、raw chain-of-thought 或 API key。

## 实现范围

1. 建立 participant goal/commitment 候选、政策与 Python 裁决 Module。
2. 扩展 `CognitionRuntimeView`、Experience request/outcome 与 Timeline read model；所有记录仍随同一 `TimelineOutcome` 原子发布。
3. 增加 DeepSeek Adapter 的严格两阶段投影，并接入 composite；各能力 provider 投影继续分开发送。
4. `ApplicationFacade` 增加 typed query/projection，桌面轮次注释和侧栏显示目标/承诺状态。
5. 随迁行为测试，并覆盖原子失败、provider 越界、重启恢复和现有能力同轮不回归。
6. 用户于 2026-08-30 明确批准验收前置：桌面内配置 DeepSeek key，保存到 Windows Credential Manager，支持保存并验证、替换和删除；key 只用于 HTTPS Bearer 鉴权。
7. 用户于 2026-08-30 要求修复结构化输出脆弱与 DeepSeek 耦合：明确目标查询/变化由 Python 优先处理；含糊输入通过 provider-neutral `ModelGateway`；JSON 只在 Adapter 内规范化，单项失败不得杀死整轮聊天。
8. CredentialStore 改为 provider/account slot；DeepSeek 仅为当前生产 Adapter，未来云端或本地 Adapter 不得修改 Domain、Timeline 或产品业务 Interface。

## 范围外

- Subject Agency、MutualCommitment、提醒、计划调度、后台执行、effect。
- Situated State、Medium State、Belief、历史消息投影、跨能力合并投影。
- 正式身份迁移、自动真实调用、新测试类别或治理机制；真实 key 的保存/验证只由用户在桌面明确操作触发。

## 验收

- fake provider 全链：create → query → revise/transition → restart，逐字证据和不可变历史可见。
- 既有 Memory、Knowledge、Relationship、原子 Publication 与恢复测试全绿。
- 用户在桌面入口真实完成一次创建与重启查询后转 done；本会话若未进行真实调用则保持 in_progress。
- 回归场景“我的目标是什么？”不得调用结构化 provider；DeepSeek `noop + null` 形状必须被安全规范化；含糊分类失败只形成目标能力 FailedClosed，其他回复仍完成。

## 2026-08-30 会话 1

- 随迁 create/revise/transition/noop、逐字证据、歧义、重复、提醒与角色承诺拒绝语义；参与者记录归 Experience，不开放 Agency。
- 新增两阶段 DeepSeek Adapter：分类只见临时 `turn_ref`，回复只见无 ID 的 selected records；越界 ref、额外字段和 provider failure 均 fail-closed。
- Facade fake 全链完成 create → query → restart recall → revise → achieved；旧记录保留 superseded，新记录终态为 achieved，provider failure 无部分写入。
- Windows state/turn JSON 与侧栏已显示 goal/commitment、状态和动作，不暴露 record/source ID；全量回归 174 passed。
- 未读取真实 credential、未发网络请求、未触碰正式身份；切片保持 in_progress，等待用户真实桌面验收。

## 2026-08-30 凭据设置批准

- 用户明确确认软件内配置 DeepSeek API key；允许写入 Windows Credential Manager，并在用户点击“保存并验证”时调用 DeepSeek `/models` 进行无聊天内容的 Bearer 鉴权验证。
- 仓库、SQLite、Timeline、state.json、日志、错误文本和 provider 消息不得保存或回显 key；无 Windows secure backend 时保持 typed unavailable，不使用文件或明文 fallback。

## 2026-08-30 会话 2

- 新增 `CredentialStore` Interface、Windows Credential Manager 与内存 Adapter；`keyring 25.7.0` 的 secure backend 实机可用，当前 configured=false。
- 首次启动无 key 不再崩溃，直接进入设置页；保存并验证、替换、删除均为用户显式操作，删除凭据不删除对话数据。
- 验证只 GET DeepSeek `/models` 并发送 Bearer header；无用户消息、角色状态、持久 ID 或数据库内容，401/403 与网络不可用分开显示。
- UI 使用 password input，不使用 localStorage/sessionStorage；server 不读环境变量或 key 文件，响应不回显 secret。
- 无 key 真实进程烟测通过；凭据定向 20 passed，全量 188 passed；未使用真实 key、未发真实网络请求。

## 2026-08-30 结构化输出与 provider-neutral 修复批准

- 用户明确要求不把产品限定于 DeepSeek；允许建立 provider-neutral ModelGateway、能力声明与 provider/account credential slot。
- 当前不启用 DeepSeek strict-tool Beta：官方 JSON mode 只保证合法 JSON，strict schema 仍属 `/beta`；先以 Python 确定性路径、action-aware canonicalizer 和 Adapter capability 资格化机制保证正确性。

## 2026-08-30 会话 3

- 新增 provider-neutral `ModelGateway.execute(ModelTask)`、`ProviderAdapter` 与 strict-schema/tool-call/json-object/text 能力声明；composite/goal cognition 不再 import DeepSeek。
- “我的目标是什么？”及明确 create/revise/transition 由 Python 直接处理，测试确认零结构化模型调用；用户截图中的现有 active 目标无需迁移。
- 真实诊断响应 `noop + evidence_quote:null + experience_summary:null` 已成为回归：Adapter 仅在 noop 时规范化为空字符串，状态变化候选仍严格验证。
- 含糊分类/reply 失败只在 Experience 中记录 participant goal `failed-closed`，Memory/Knowledge/Relationship 回复仍可原子完成且不产生目标部分写入。
- CredentialStore 已按 provider/account slot 泛化并保持现有 DeepSeek vault 兼容；定向 26 passed，全量 192 passed，未再次发送真实 provider 请求。

## 真实用户收口

- 用户完全重启 Avery 后再次询问“我的目标是什么？”，现有 active 目标由 Python 确定性路径正确回答；原 `participant-goal-classification-failed` 不再出现。
- Slice-01 的真实创建、持久化、重启查询与失败修复验收完成，参与者目标与承诺从 INTEGRATED 提升为 STABLE。
