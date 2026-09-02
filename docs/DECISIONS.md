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

## D-012：来源建角先做短文本临时预览

2026-08-31，用户批准把逐次确认授权的单份 project-original 文本发送给 DeepSeek，仅提议 Genesis/Knowledge 候选。Slice-08 不复用旧 authoring ledger，不发布或创建身份；所有候选需逐字证据和 Python 结构裁决，UI 明示“结构通过仍需人工确认”。视频、多模态、私人来源、持久草稿和 SubjectStudio freeze 后置。

## D-013：预封存选择由 Studio sidecar 持久化

2026-09-01，用户批准逐次确认保存来源原文、候选和选择，并由显式操作删除。为避免迁移现有 ProfileStore 或建立平行身份真相，SubjectStudio root lazy 创建单草稿 sidecar；candidate basis/source 不可在 revision 间偷换，只允许 selection-only 追加。ApplicationFacade 是唯一入口，Timeline 与 Avery 不参与。

## D-014：Freeze 前必须展示 exact deterministic mapping

2026-09-01，Source Draft 不直接 seal。用户先提供有 identity evidence 的 display name，Python 按固定策略映射 Profile/Genesis/Knowledge，并展示完整 Freeze Basis；来源不能预写已赚取关系，初始关系固定为空白。映射重复稳定且只读，真正 freeze/新身份创建等待下一次明确授权。

## D-015：exact Freeze Basis 创建独立 runtime authority

2026-09-01，用户明确授权 basis `e99264f...311343`。Freeze 在写前重算 basis，以稳定身份幂等封存 Profile/Genesis/Knowledge 并发布 QRI；本地 registry 只选择完整隔离 authority，不合并 Timeline。Knowledge runtime 改从当前 QRI snapshot 注入，代码 fixture 仅兼容旧 Avery；0 member 不继承旧知识。真实切换发现 Presentation DOM 会残留上一身份消息，已在切换成功时清空并标记“原有身份/来源封存”。Freeze、registry、切换均不调用 Provider，真实对话继续使用既有六类授权投影。

## D-016：本地身份 Authority 从 composition root 提炼为深 Module

2026-09-01，Slice-11 后 `local_product.py` 同时承担 registry/state/freeze/select/Host 生命周期与 cognition 装配，虽行为正确但 locality 不足。提炼 `LocalIdentityAuthority`，以 `load_active/freeze/list/select` 四方法 Interface 隐藏本地持久化与恢复复杂度；`local_product` 只消费 `LoadedLocalIdentity` 并完成唯一 production composition。该重构不迁移数据、不改变 Provider 投影或用户行为，真实 v2 双身份 state 无迁移复验。

## D-017：Dogfood 历史只投影 canonical TimelineOutcome

2026-09-01，为让用户首次体验能感到跨重启连续性，页面恢复当前 identity 最近 20 个已提交 user/expression 对。History 不建立新 store，不展示 pending/interrupted/FailedClosed；TimelineEngine 每次验证完整 outcome digest 链与 head 后再裁剪窗口。实时第 21 轮由服务器返回的 canonical window 重建 DOM，身份切换只在目标 history 成功加载后关闭选择页。build 为固定 `dogfood-s13` 常量；错误主文案使用 exact typed 闭集，未知值统一 FailedClosed，不显示裸 code/path/ID。

## D-018：主表达不朗读裁决规则

2026-09-02，真实体验证明直接姿态命令的硬编码主回复像状态机说明书，普通会话入口会错误退化为“没有记忆或知识”，关系声称在 Provider 漏判时甚至被直接接受。Slice-14 保持 Domain/Outcome/explanation 不变：Situated 自然询问具体情境；五条精确普通会话入口使用本地自然回复；关系声称按分句精确闭集生成 Python `relationship_claim` NoUpdate candidate，并与合法 Knowledge/目标表达合并。该保护不覆盖 Relationship Provider FailedClosed，不新增统一表达层、Identity 投影或 Provider 字段。build 升为 `dogfood-s14`。

## D-019：相对日计划绑定 canonical Admission

2026-09-02，Slice-15 将新 plan/目标/承诺中唯一的今天、明天、后天或完整日期由 Python 绑定为 `Asia/Shanghai` day anchor；原文和逐字证据保持不变，UI 与既有 Provider content/terms 字段按当前日期渲染。旧记录不迁移，模糊或多时间表达不猜测；离线经过时间不产生 Experience、完成、提醒、主动行为或 Lifeworld 事实。每轮 Experience 时间同步改用该 Operation 的 canonical Admission，而非 QRI 发布时间。

## D-020：封存身份只约束 capability-local reply

2026-09-02，用户授权把当前 sealed identity 的 exact `{subject_name, subject_identity, canon_start}` 发送给六类 DeepSeek reply，不进入 proposal/classification。为避免身份影响状态候选，Living Memory、Knowledge、Relationship 拆为各自两阶段；Identity 只形成表达，Python 过滤无来源的第一人称当前活动句，reply 无效时使用原 proposal 已验证的 identity-free 回复。真实对抗曾暴露模型虚构“刚收到稿件”、把 voice 示例当口头禅和新 failure code 升级整轮失败，均按上述边界修正；不建立统一表达层、人格发展或 Lifeworld。
