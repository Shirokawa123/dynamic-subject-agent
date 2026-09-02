# Slice-15：现实时间锚定基础

状态：active（2026-09-02）。规模预算：≤ 3 个工作会话。

## 用户可见结果

用户在 `Asia/Shanghai` 时区于某日说“我后天要学习 LLM”，系统保留原始逐字证据，同时封存目标日期；次日 Memory/目标卡与召回 Provider 看到“我明天要学习 LLM”，目标日看到“我今天要学习 LLM”。重启不重新解释原句，旧记录不迁移、不猜日期。

## 时间契约

- 一轮 Experience 的现实时间观察只取 canonical Admission `admitted_at_us`；不得使用 QRI 发布时间、页面时间、Provider 时间或模型推断。
- `TemporalAnchor` 绑定原始时间表达、Admission 所在本地日期、固定时区、目标日期、day 精度和策略版本；原始 Memory content/goal terms/evidence 永不改写。
- 本切片只解析每条消息中唯一的 `今天/明天/后天` 或完整 `YYYY-MM-DD`、`YYYY年M月D日`；无表达、多表达、无效日期和模糊表述均 typed NoOp/unanchored，不猜测。
- 当前投影按目标日期与当前现实日期重新渲染：今天/明天/后天/昨天/前天，其他日期显示绝对日期。渲染不产生 Timeline 写入。
- 旧 canonical 记录没有 TemporalAnchor 时保持原文；不回填、不迁移、不根据当前日期重新解释。
- 离线时间只改变投影，不生成 Experience、完成状态、提醒、主动消息或虚构经历。

## Module 与 Interface

- 新 `TemporalGrounding` 深 Module 是纯 Python：`anchor(text, observed_at_us)` 与 `render(text, anchor, observed_at_us)`；Admission 时间由 Timeline 提供，因此不新增第二个 Clock store/port。
- `AdmissionSnapshot`/`ExperienceBasis` 携带 typed `admitted_at_us/observed_at_us`；`ExperienceRecord.experienced_at_us` 改用该轮 basis，而不是 runtime/QRI 启动时刻。
- ExperienceDomain 仅在 accepted Living Memory `memory_kind=plan` 和 accepted participant goal/commitment create/revise fragment 中附加 anchor；模型仍只提议原始候选，Python 解析并裁决时间。
- Timeline 从既有 decision reason JSON 重建 optional anchor，不修改 SQLite schema；LivingMemoryRecord 与 ParticipantGoalCommitmentRecord 保留 canonical 原文与 optional anchor。
- SubjectRuntime 与 ApplicationFacade 对 Provider/UI 构造当前时间投影；canonical Timeline 查询仍可重建原文和 anchor。

## Provider 与数据边界

- 不新增 Provider task、字段或用途。Living Memory 仍发送 `{memory_id, content, source_user_message_id}`，目标仍发送 `{turn_ref, kind, terms, status}`；其中 content/terms 可由同一 canonical anchor 按当前日期渲染。
- 不发送时区、anchor date、target date、Admission timestamp 或 TemporalAnchor 结构。
- 不调用 Provider 解析时间，不发送历史消息或系统 Clock。

## 实施顺序

1. 建立 TemporalAnchor/TemporalGrounding 纯 Module，覆盖支持语法、无效/多表达、跨日渲染和时区日界线。
2. 将 canonical Admission 时间加入 AdmissionSnapshot/ExperienceBasis，并修正每轮 ExperienceRecord 时间；随迁原子 Publication/重启测试。
3. Living Memory plan accepted fragment 写入 optional anchor，Timeline 重建，Runtime Provider 投影和 Desktop Memory 卡按当前时间渲染。
4. participant goal/commitment create/revise 同样封存 anchor，查询/Provider/Desktop terms 动态渲染；transition 保持目标原 anchor。
5. 使用 fake observed time 完成 9 月 1 日→2 日→3 日→4 日 byte-equivalent/restart 验收；对抗旧记录、模糊时间、两处时间、Provider 乱提议和时间篡改。
6. Windows/DeepSeek 隔离 root 真实验收“后天→明天”，两轴审查、全量测试、文档、commit、push。

## 范围外

- 时区切换、系统时间回拨、夏令时策略、重复日程、时间段、农历或自然语言任意日期解析。
- 到期自动 transition、提醒、调度、后台运行、主动消息或 effect。
- Lifeworld、World State、Identity/voice Provider Projection、Agency 或人格发展。
- 迁移或重写既有 Memory/目标/TimelineOutcome。

## 最小验收

- 固定 2026-09-01 `Asia/Shanghai` 接受“我后天要学习 LLM”后，canonical content/evidence 保持“后天”，anchor target 为 2026-09-03；9 月 2/3/4 投影分别为明天/今天/昨天。
- 同一 anchor 跨关闭重开 byte-equivalent；旧无 anchor 记录始终显示原文；多时间表达和无效日期不附加 anchor。
- 每轮 ExperienceRecord 时间等于该 Operation canonical Admission 时间，连续轮次不再共享 QRI 发布时间。
- Living Memory/participant goal Provider outbound schema 不变且不含 anchor/timezone/date 字段；模型不能覆盖 Python anchor。
- UI Memory/目标卡显示当前投影，Timeline head/Publication/六能力状态语义不变；全量测试与两轴审查无阻塞。
