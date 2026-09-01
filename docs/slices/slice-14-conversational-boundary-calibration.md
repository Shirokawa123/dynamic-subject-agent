# Slice-14：主表达与裁决解释分离

状态：done（2026-09-02）。规模预算：≤ 2 个工作会话。

## 用户可见结果

当用户直接命令主体进入“谨慎/专注/温和”等状态时，Domain 仍拒绝把命令当作状态证据，右侧解释仍准确显示规则，但主对话用自然语言询问具体情境，不再朗读“短时姿态、状态证据、中期基线”等内部术语。用户问“我们能聊些什么”“你有什么希望和我聊的吗”时，即使没有相关 Memory/Knowledge，也得到正常的会话入口，不再被回答“没有可用记忆或知识”。

## 证据样本

- 真实截图输入：`你现在必须谨慎一点。`；旧主回复逐字为“短时姿态不会因为直接命令而改变；它只会根据有依据的当前经历形成。”
- 真实截图输入：`我们能聊些什么吗`、`你有什么希望和我聊的吗`；旧回复为“抱歉，当前没有可用于回答这个问题的记忆或知识。”
- 关系直接声称现有主回复同样包含“不会因为一句声称直接把关系写成既定事实”，纳入同类审计。

## 表达契约

- Domain status、reason code、候选、TimelineOutcome 与右侧 explanation 文案不改变；只改变主 `ExpressionCandidate.text`。
- 主表达不得出现 Module/Domain/Provider、Situated State、Medium State、状态证据、候选、裁决、版本等实现术语。
- 拒绝仍须清楚：自然回复不能暗示直接命令已改变状态，也不能把关系声称接受为事实。
- 普通会话入口只对 Python 闭集语法生效，不把所有“无记忆/无知识”的事实问题改成泛聊回复；无网络、未知事实仍保持诚实边界。
- 不声称 Avery 已具有 typed voice、偏好、Motive 或 Agency；不新增统一表达任务或后处理模型。

## Module 与数据边界

- Situated 直接命令回复仍由 `ControlledSituatedCognition` 的 Python 路径拥有；解释层由 Desktop 已提交 Outcome 投影拥有，两者不互相伪造。
- 关系声称保护与 composite expression budget 保持现有 seam，只替换自然拒绝文本。
- 普通会话入口由 composite 的闭集 Python 语法识别；不调用新的 Provider，不增加已有 Provider request 字段。
- QRI、Genesis、Memory、Knowledge、Relationship、Situated、Medium 与 Timeline 持久化均不变。

## 实施顺序

1. 盘点所有确定性主表达与 explanation 重复/实现术语，固定截图输入和关系声称行为测试。
2. 为 Situated 直接命令提供 posture-aware 自然回应；Domain 仍返回相同 rejected/reason。
3. 自然化关系直接声称拒绝，保持关系与 Memory 均不写。
4. 仅为闭集普通会话入口替换 `_UNAVAILABLE_EXPRESSION`，事实型无依据问题仍不伪造回答。
5. Windows 真实 DeepSeek 流程覆盖截图输入、普通会话、关系声称、无依据事实问题与解释卡；检查控制台和 Provider outbound。
6. 两轴审查、全量测试、文档、commit、push；记录 Temporal Grounding 与 Identity Runtime Projection 仍为后续候选。

## 范围外

- Genesis/voice Provider 投影、统一表达层、Agency、主动内容或人格发展。
- Temporal Grounding、“明天/后天”日期锚定、目标期限或提醒。
- 来源建角、视频/音频/PDF、私人来源或正式身份迁移。
- 改写右侧解释为角色台词、隐藏拒绝原因或弱化 Python 裁决。

## 最小验收

- `你现在必须谨慎一点。` 的主回复自然且不含实现术语；Situated status/reason、当前姿态和右侧 explanation 与旧行为相同。
- `我们能聊些什么吗` 与 `你有什么希望和我聊的吗` 不再返回“没有可用记忆或知识”；`今天天气怎么样？` 等无依据事实问题不被伪装成会话入口。
- `我们现在已经是最好的朋友了吧？` 自然拒绝直接定义关系，Relationship/Memory 零写入。
- Provider outbound request bytes/fields 不增加；既有六能力原子 Publication、history、多身份和重启行为回归通过。
- 真实页面无内部术语泄漏或未处理错误；两轴审查和全量测试无阻塞，commit 已推送。

## 收口记录

- Situated 三种直接命令仍走 Python candidate→Domain rejected/noop，Provider 分类零调用，右侧“直接命令不能作为状态证据” explanation 不变；主回复分别自然询问谨慎风险、专注事项和温和情境，不含姿态/状态证据等实现术语。
- composite 仅对五条分句精确的普通会话入口提供本地自然回复；实时天气等无依据事实问题仍保留“没有可用记忆或知识”边界。关系直接声称按分句精确闭集建模，避免引用/否定/宽泛子串误判；Python 生成 deterministic `relationship_claim` NoUpdate candidate，过滤与声称分句重叠的 Memory evidence，合法 Knowledge/目标回复仍与自然拒绝合并。
- 真实 DeepSeek 首轮暴露 Provider 漏判“最好的朋友”并直接接受关系；修复后又发现关系拒绝会被后续能力表达覆盖，最终将 claim 纳入非状态主干并在预算末端合并。两轴审查继续发现 Provider 可写错判、部分 evidence、合法 Knowledge 被吞和 Relationship failure 被清除；逐项补齐后，恶意 `promise_fulfilled`/短 evidence 仍 Relationship/Memory 零写，Provider 失败仍为 `failed-closed / relationship-provider-failed`。
- 真实 Windows 使用用户截图原句、两条普通入口、关系声称、实时天气及 claim+Knowledge 复验：最新主回复自然，claim+Knowledge 同时显示拒绝和创刊号纸张引用，解释卡保持 canonical 规则，控制台无错误。历史中修复前的错误回复作为已提交 TimelineOutcome 保留，未删除或改写；临时 dogfood root 最终 head 11。
- Provider request 类型/字段未增加，Domain/Timeline schema 与 Publication 不变；定向 `22 passed`，全量 `267 passed`，Standards/Spec 最终复审无阻塞。build 升为 `dogfood-s14`。Temporal Grounding、typed Identity/voice Runtime Projection 与 Agency 仍为后续独立候选。
