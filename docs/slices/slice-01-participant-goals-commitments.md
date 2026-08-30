# Slice-01：参与者目标与承诺迁移

状态：in_progress（2026-08-30 用户明确要求继续推进）。规模预算：≤ 2 个工作会话。

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

## 范围外

- Subject Agency、MutualCommitment、提醒、计划调度、后台执行、effect。
- Situated State、Medium State、Belief、历史消息投影、跨能力合并投影。
- 正式身份迁移、自动真实调用、新测试类别或治理机制；真实 key 的保存/验证只由用户在桌面明确操作触发。

## 验收

- fake provider 全链：create → query → revise/transition → restart，逐字证据和不可变历史可见。
- 既有 Memory、Knowledge、Relationship、原子 Publication 与恢复测试全绿。
- 用户在桌面入口真实完成一次创建与重启查询后转 done；本会话若未进行真实调用则保持 in_progress。

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
