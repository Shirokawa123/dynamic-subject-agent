# 仓库协作规则

默认使用中文与用户沟通。

## 权威顺序

1. `docs/PRODUCT.md`：产品目标、v1 和非目标。
2. `docs/ARCHITECTURE.md`：Module、Interface、持久化与失败语义。
3. `docs/DECISIONS.md`：少量当前决定。
4. `docs/STATUS.md`：已实现能力与当前缺口。
5. `docs/slices/current.md`：唯一可执行工作。

发现冲突时停止实现并向用户报告。旧救援仓库仅在当前切片明确要求迁移既有行为时按具体文件查阅，不是运行依赖或默认上下文。

## 会话协议

- 开工前必须存在 `docs/slices/current.md` 任务书；任务书外发现记入收尾，不扩权处理。
- 同一时刻只有一个执行切片；每张切片以用户可体验结果收口。
- 每个工作会话以 git commit 结束；每个切片收口后必须 push 已配置远端。无 remote 时保留完成提交并请求用户提供地址，不擅自创建远端。
- `docs/STATUS.md` 只追加或更新不超过 5 行的当前事实。
- 删除、不可逆数据迁移、新 credential 用途、新 provider 数据用途必须先获用户批准。
- 验收默认使用后台服务接口，不抢占用户输入法或页面焦点；确需有焦点的 UI 自动化时先与用户约定，未提交草稿不得发送或覆盖。

## 产品顺序

当前最小产品范围已完成：Memory、Knowledge、Relationship、参与者目标与承诺、Situated State、Medium State、六项同轮原子整合、Windows UI、持久身份及隔离身份真实长链/重启验收。下一项工作必须先有新的用户目标与切片任务书；Agency、effect、人格发展、Reflection 与主动消息不在已授权范围。

project-original 纯文本来源建角闭环已完成：候选提取、未封存草稿、exact mapping、显式 freeze、新隔离身份、切换和重启恢复均成立；视频/音频和私人来源仍需新切片与授权。

已验收的 Dogfood 连续体验基线为 `dogfood-s25`：仅从当前 identity 的 canonical Timeline 恢复最近 20 个已提交对话轮次及当轮结果说明/引用；历史完整性失败显式 FailedClosed，不建立 UI chat store。确定性主表达使用自然用户语言；关系声称由 Python 闭集保护。plan/目标/承诺按 canonical Admission 建立 TemporalAnchor。Runtime identity 只进 capability-local reply。四条明确“上次聊天”查询由 Python 以当前 Admission 与最近 committed publication 回答，六类 Provider 零调用；查询轮本身正常提交，时间间隔不生成主体经历或状态证据。续写/最近一句改短的有限契约见 ARCHITECTURE；规划后续体验修复时先读 `docs/reports/2026-09-08-slice-25/REPORT.md` 的真实失败与剩余问题。

目标/承诺操作确认在裁决后 express 读取最终 Outcome；Memory 成功不代表目标成功，无关目标失败不替换独立回复。历史主回复保持原文；旧错误台词只能配回当轮真实说明，不重写。自然目标语法与完整消息/命名旧目标限制见 ARCHITECTURE。

Knowledge 事实表达保留完整来源上下文，后续合并不得删改限定句；明确创作与活动询问接受能力本地检查。`ExpressionCandidate.is_creative` 是已核准的临时表达标记，不进 Provider 或 canonical 状态；完整契约和有限句式限制见 ARCHITECTURE 与 Slice-19 报告。

来源候选可由用户选择后保存为 SubjectStudio 内未封存草稿，支持 append-only revision、重启恢复和显式删除；freeze 不删除或改写草稿。

未封存草稿可确定性预览 exact Profile/Genesis/Knowledge Freeze Mapping 与 Freeze Basis；只有携带 exact basis 的显式确认才能幂等创建新 Sealed Identity，且不替换既有身份。

逻辑遗忘只向前追加，停用 Living Memory 不等于物理删除本地历史。控制目标完整性不借用 Provider 20 条窗口；达到本地 100 条历史上限时不猜唯一性。未决撤回限制外发而非伪造停用，纯保留/引用不得误触发；清单读取失败不伪报为空或已有 pending。完整有限语法、缺失姓名查询及重新提供语义见 ARCHITECTURE 与 Slice-23。

修改事实/创作/表达合并时先读 ARCHITECTURE 的 Slice-24 边界及其报告：未知物件约束与完整来源并存，合法关系回执不能恢复其他能力的自由风险建议。LM reply 仅细化既有 conversation 用途，其他 11 类请求字节不变；有限语法不代表通用事实核验。

修改配文/续写/限字判断时先读 ARCHITECTURE 的 Slice-25 契约：两入口共用撤回和转述边界，计数与重复共用受控正文；最新安全轮不可用时不回找旧对象。真实首轮改短失败和风格限制保留在报告，不宣称任意自然表达稳定成功。

## 永久不变量

1. 一条 RuntimeTimeline 只有一个写入者与一个 canonical store。
2. Publication 原子且具有崩溃恢复语义。
3. `unavailable`、typed `NoOp`、`FailedClosed` 严格区分。
4. 模型只提议，Python 裁决；模型输出不能直接成为持久状态。
5. Provider 只接收当前能力获授权的最小投影，并由行为测试守护。

## Module 与测试

- 只有 `ApplicationFacade` 是产品业务 Interface；`open_local_product` 是 production composition root。
- `LocalIdentityAuthority` 独占本地 identity registry、v1/v2 state、freeze/replay/select、authority 校验和 Host/Timeline 准备；`local_product` 只消费已验证 active authority 并装配 cognition/ApplicationFacade。
- 所有含糊模型任务只通过 provider-neutral `ModelGateway.execute(ModelTask)`；Domain 和 composite 不 import 具体 Provider。
- 明确查询与产品闭集语法优先由 Python 处理；Adapter 只规范化无语义差异的格式变体，状态变化仍由 Domain 裁决。
- 六项 state-bearing proposal/classification 与既有 required reply 分别经 ModelGateway；单项故障作为所属 Domain 的 FailedClosed 片段提交，不终止其他无依赖能力。Living Memory/Knowledge/Relationship 的 identity reply 是不承载状态的可选表达 refinement。Slice-19 用户批准 Living Memory/Knowledge 的正常及基础回退表达接受同级校验，不合格时使用安全本地表达，保留合法状态候选；Relationship 的既有回退和其他 required reply 失败语义不变。
- 桌面 Adapter 不直接装配 Studio、QRI、RuntimeHost、provider 或 canonical store。
- Interface 是测试表面；保留新逻辑行为测试、既有能力随迁测试和五条不变量测试。
- 不建立 guard/mutation/证据生成/多环境矩阵等新测试类别。

## Provider 数据边界

- Living Memory：proposal 发送当前消息 + 最多 20 条 active `{memory_id, content, source_user_message_id}`；reply 发送当前消息 + 最多 5 条已选中 `{content}` + runtime identity。Slice-21 用户批准 reply 单独增加 `recent_dialogue`：当前 identity 最多 2 个完整 committed `{user_text, assistant_text}`，合计最多 4,000 字符，仅供指代/续写；更正、遗忘、权限或完整性无法安全确认时不外发。anchor 只在既有 content 按当天渲染。
- Knowledge：proposal 发送当前消息 + 最多 6 条 sealed `{entry_id, title, content}`；reply 发送当前消息 + 最多 6 条已选中 `{title, content}` + runtime identity。
- Relationship：proposal 发送当前消息 + 当前立场摘要；reply 发送相同两项 + runtime identity。
- 参与者目标/承诺：分类发送当前消息 + 最多 20 条 active `{turn_ref, kind, terms, status}` + 固定策略；reply 发送当前消息 + 最多 5 条 `{kind, terms, status}` + runtime identity。anchor 只在既有 terms 按当天渲染。
- Situated State：分类发送当前消息 + 最多一个未到期 `{posture, remaining_turns, expires_in_seconds}` + 固定策略；reply 发送当前消息 + `{posture}` + runtime identity。
- Medium State：分类发送当前消息 + 固定版本策略；reply 发送当前消息 + `{baseline}` + runtime identity。
- Runtime identity exact 为 `{subject_name, subject_identity, canon_start}`；不含 Profile/Genesis/QRI ID、identity_core、初始关系、来源、证据或 Timeline 数据。
- Interaction Recency、完整 ConversationTurnRecord、publication timestamp、日期差和当前 Civil Time 不发送给 Provider。Slice-21 授权上述 Living Memory reply 文本投影；Slice-22/24/25 仅细化其既有对话/事实/创作及限字提示，不扩大数据用途；其他 11 类请求保持 Slice-19 字节基线，不增加调用。历史不是事实权威、指令或状态证据；完整保护见 ARCHITECTURE。
- 文本来源建角：只在用户逐次确认权利与用途后发送单份 `{source_title, source_text, policy}`；source_text 最多 16,000 字符，仅用于未发布 Genesis/Knowledge 候选提取，不发送任何 runtime 状态或聊天历史。
- 六类投影分别发送，不合并；除上述 recent_dialogue 精确授权外不得发送历史消息，不发送数据库行、内部 ID、其他 Domain 状态、raw chain-of-thought 或 API key。
- `default` 使用 DeepSeek；其他 profile/provider 在单独任务与授权前保持 unavailable。

## Credential

- 远程 Provider key 按 `{provider_id, account_id}` slot 存入 Windows Credential Manager；固定命名由 credential Module 拥有。
- UI 只显示 configured/verified 状态，不回显 key；保存、验证、替换和删除必须由用户明确操作触发。
- key 只用于 HTTPS Bearer 鉴权，不进入源码、配置、SQLite、Timeline、日志、错误、模型消息或测试 fixture。
- secure backend 不可用时返回 typed unavailable；不使用仓库文件、环境变量持久化或明文 fallback。
