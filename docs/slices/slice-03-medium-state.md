# Slice-03：Medium State 迁移

状态：done（2026-08-31）。规模预算：≤ 2 个工作会话。

## 目标

在同一 Windows 产品中建立可恢复的中期主体基线。Provider 只从当前消息提议 signal；Python 使用独立证据、冷却和状态机决定 settled/concerned/encouraged，UI 显示当前 baseline、版本、来源与本轮决策。

## 规格来源

- 旧救援仓库 `medium_state.py`、`medium_state_policy.py` 及对应领域、仓储、ConversationService 测试；只迁移行为语义。
- 新仓库 `SubjectState` Domain、TimelineOutcome、ModelGateway、ProviderAdapter、ApplicationFacade 与桌面 projection 是唯一实现宿主。

## Provider 数据边界

沿用用户已授权用途：分类只发送当前用户消息和固定版本 Medium policy；回复只使用当前消息并附加本轮实际选中且已验证的 `{baseline}`。不发送消息历史、assistant 文本、Memory、Knowledge、Relationship、目标承诺、Situated State、用户画像、CharacterPack、profile 名称、内部 ID、数据库行、完整 provider 响应、raw chain-of-thought 或 API key；各能力投影保持分离。

## 实现范围

1. 随迁 baseline/signal 闭集、双独立证据、最近 completed Experience 窗口、冷却、版本和旧证据不可复用规则。
2. 用户直接命令主体状态不能成为证据；Provider 只提议当前消息 signal，Python 独占状态转换。
3. provider-neutral Medium ModelTask、action-aware canonicalizer 与 DeepSeek Adapter；失败只形成 Medium FailedClosed。
4. SubjectState/Timeline/ApplicationFacade/Desktop 全链；Medium 与 Situated 独立保存、独立投影、不得自动晋升或组合发送。
5. fake 全链、原子失败、重启、对抗输入、跨能力隔离、全量回归。
6. 新隔离身份完成真实 DeepSeek、Windows UI、关闭重开和多轮门槛验收；不读取或修改正式身份。

## 范围外

- 人格发展、长期情绪诊断、Agency、Relationship Narrative、提醒、后台行为、effect。
- Situated → Medium 自动晋升、跨能力合并投影、隐式 provider fallback。
- 新 guard/mutation/证据 JSON/治理状态机/测试框架类别。
- 旧仓库、私人数据或正式身份的删除、迁移或修改。

## 验收

- 空状态为 settled/v0；一条信号不足，第二条独立逐字证据才允许转换。
- concern/settling/encouragement 路径、冷却、最近窗口、旧证据拒绝与直接命令拒绝可复核。
- Provider failure/invalid output 不写状态且不终止无依赖回复。
- 真实页面显示 baseline/version/decision，重启完整恢复；全量测试绿、commit 并 push 远端。

## 收口证据

- 行为、Provider 边界、跨能力和重启测试齐备；全量 `215 passed`。
- 隔离身份真实 DeepSeek：第一条 concern 证据保持 settled/v0，第二条独立证据转换 concerned/v1，关闭重开后恢复 concerned/v1。
- 隔离 Windows 页面复现相同决策并显示 settled/v0 → concerned/v1；浏览器控制台无错误，未读取或修改正式身份。
