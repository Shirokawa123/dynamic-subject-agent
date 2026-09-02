# Slice-17：Subject Time Continuity

状态：active（2026-09-02，真实验收与全量通过，等待最终复审）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用户明确问“我们上次什么时候聊的？”或“我们多久没聊了？”时，当前身份依据自己的 canonical Timeline 给出 day-precision 答案。关闭重开后答案不变；切换身份后只看目标身份自己的最近已提交对话。首次对话明确说明没有更早的 committed turn。

这只是时间定向：现实经过三天不等于角色经历了三天生活，不生成离线事件、感受、关系变化、提醒或主动消息。

## 时间事实与语义

- 当前观察取本轮 canonical Admission `admitted_at_us`，固定按 `Asia/Shanghai` 转为 Civil Time 日期。
- “上次聊天”严格指当前 identity 最近一个完整 `TimelineOutcome` 的 `ConversationTurnRecord.published_at_us`；它是该轮完成 Publication 的时间，不是 QRI 创建时间、页面打开时间或当前 query 自己。
- pending、interrupted、FailedClosed、尚未 Publication 的 Operation 与仅启动/关闭页面均不算上次聊天。
- `InteractionRecency` 是当前 Admission 与最近 committed turn 的日期差；它不是 Memory、Experience、TemporalAnchor、提醒计划或 Lifeworld event。
- 当前 Admission 早于最近 committed publication 时 FailedClosed，不输出负天数或猜测系统时钟回拨。
- 旧 Timeline 不迁移；现有 canonical conversation history 已有的时间即为唯一来源。

## 明确查询闭集

只对去除空白和末尾中英文问号/句号后恰为以下文本的独立消息启用本地路径：

- `我们上次什么时候聊的`
- `我们上次是什么时候聊的`
- `我们多久没聊了`
- `距离我们上次聊天多久了`

以下不进入本切片：

- “上次聊了什么”“你还记得上次吗”等内容回忆；
- “以后每隔几天提醒我”等调度请求；
- 复合消息、模糊时间、任意自然语言日期解析；
- 主动提及用户离开多久，或把间隔解释为想念、等待、孤独和离线活动。

## 确定性表达

- 无更早 committed turn：`在这条身份时间线上，还没有更早的已提交对话。`
- 日期差 0：说明上次是今天；差 1/2：分别使用昨天/前天；差 3～6：使用 `N 天前`。
- 日期差 ≥ 7：显示 `YYYY年M月D日（距今 N 天）`。
- “什么时候”与“多久”可使用不同句式，但答案只由 Python 闭集模板生成，不调用模型，不把内部 ID、timestamp、Timeline 或 Publication 术语说给用户。

## Module 与 Interface

- 新 `SubjectTimeContinuity` 为纯 Python 深 Module，唯一 `evaluate()` Interface 接受 `{query_text, current_admitted_at_us, load_last_committed_at_us}`，返回 typed `Answer | NoOp | FailedClosed`；history loader 只在闭集命中且当前时间有效后惰性调用。Module 隐藏闭集路由、上海日期换算、首次互动和渲染规则。
- `TimelineEngine.list_conversation_turns(limit=1)` 继续验证完整 canonical outcome chain 后返回最近 committed turn；不增加新查询表、缓存或 recency store。
- `SubjectRuntime` 只在明确查询时从完整 canonical history 派生最近 `published_at_us`，把 typed result 放入 internal context；非明确查询不读 history，也不使用、表达或外发 recency。
- `ControlledCompositeCognition` 在任何 Provider 子任务前调用该 Module；命中时形成全 Domain NoOp 的本地 grounded Expression，未命中时现有六能力路径 byte-equivalent。
- `ApplicationFacade` 和 Desktop 不新增业务 Interface 或第二份 history；结果仍作为普通已提交 conversation turn 出现在当前 identity 的 canonical history。

## Provider 与授权边界

- 本切片 Provider 零新增调用、字段和数据用途；明确查询命中时六类 Provider 调用数必须为 0。
- `last_committed_at_us`、日期差、历史文本、ConversationTurnRecord 和 current Civil Time 均不发送给 Provider。
- 非时间查询的既有 Provider outbound 必须 byte-equivalent，不得顺便加入“上次聊天”上下文。

## 实施与验证顺序

1. 以 `ApplicationFacade` 为 seam 写红测：首次、同日、昨天、前天、N 天前、绝对日期、重启与两身份隔离；再实现纯 `SubjectTimeContinuity`。
2. 将最近 committed turn 只读投影接入 Runtime internal context；验证 query 自己不被当成“上次”、pending/FailedClosed/interrupted 排除、history 完整性篡改 FailedClosed。
3. 证明四条明确查询 Provider 零调用，近似/复合输入仍走原路径且所有 outbound byte-equivalent。
4. 对抗系统时间倒退、极大时间值、上海午夜前后、21 轮 history 窗口与跨身份切换；recency 必须使用完整 canonical history 的真正最后一轮，而不是 UI 20 轮窗口。
5. 使用新隔离 root 完成 Windows 流程：首次询问 → 普通对话 → 受控跨日询问 → 关闭重开 → 切换空身份；检查页面、history 与 console。全量测试、两轴审查、文档、commit、push 后收口。

## 最小验收

- 固定当前 Admission 为 2026-09-05：最近 committed publication 为 9 月 5/4/3/1 与 8 月 20 日时，分别产生今天、昨天、前天、4 天前和 `2026年8月20日（距今 16 天）`。
- 当前 query 前没有 committed turn 时返回首次对话文案；query 提交后重启再问，新的答案以上一条已提交 query 为最近 turn，这是 canonical 行为，不跳过“时间查询轮”。
- pending、FailedClosed、interrupted 和 UI 裁剪窗口不改变最近 committed turn；identity A/B 的日期完全隔离。
- 四条闭集查询全部 Provider 零调用；非闭集输入的六类 outbound 与 Slice-16 byte-equivalent。
- 时间倒退与 history integrity 失败显式 FailedClosed；无 timestamp、内部 ID、裸错误码或虚构离线经历进入用户表达。
- Windows/重启/身份切换通过，全量测试与 Standards/Spec 复审无阻塞。

## 主要风险

- `published_at_us` 比该轮 Admission 稍晚；本切片有意把“聊天完成”定义为 committed publication，不能混称消息发送时间。
- 闭集过窄可能让近似问法仍像普通聊天；先以可证明语义收口，不用扩大 NLP 解析来美化覆盖率。
- 时间查询本身会成为 committed turn，因此连续追问的“上次”就是上一条查询；跳过查询轮会建立第二套选择性历史，本切片禁止。
- 系统时区切换、夏令时、手工改钟后的恢复策略与小时/分钟级措辞不在范围；异常只 FailedClosed。

## 范围外

- 将 Interaction Recency 发送给任何 Provider，或让角色在普通回复中自发提及时间间隔。
- Lifeworld、World State、离线事件、人格发展、Reflection、Agency、effect、提醒、调度或主动消息。
- 聊天内容摘要、跨身份历史、关系叙事、长期情绪与“想念用户”推断。
- 任意日期解析、时区设置 UI、小时/分钟精度、系统时钟修复或数据迁移。

## 真实验收记录

- 隔离 root `dsa-s17-real-602fr_ou` 使用 production composition、Windows Credential Manager 与真实 DeepSeek：首次查询返回无更早 committed turn、Provider 0 调用/0.242 秒；普通对话保持既有 6 调用/4.341 秒；受控次日查询返回昨天、0 调用/0.342 秒。
- 关闭重开后的连续查询返回今天、0 调用/0.376 秒；切换到空来源身份后返回无更早对话、0 调用/0.263 秒。查询轮自身成为下一次上次，legacy/source Timeline 未混合。
- Windows 页面显示 `dogfood-s17`、来源身份唯一时间查询历史和首次文案，重启恢复一致，console 无 warning/error。身份切换按钮的原生 confirm 使自动化结果不确定，因此该次 UI 点击未计为成功；身份切换证据只采用 production authority 返回与重开后的页面权威状态。
- 自动测试覆盖四条闭集、同日/昨天/前天/N天/绝对日期、上海午夜、极大时间、时钟倒退、pending/FailedClosed/interrupted、history 篡改、21 轮 UI 窗口、重启、连续查询和双身份隔离；六类 proposal/classification 与六类 reply outbound 均锁定 Slice-16 SHA-256 baseline。
- 全量 `310 passed`。两轴初审发现时区常量重复、Module Interface 未 typed/lazy、测试夹具误缩进导致 Relationship 假绿、non-committed/byte baseline/Windows 证据不足；逐项修复后等待最终复审。

## 已确认授权

用户确认 Slice-17 仅实现上述四条明确查询的本地 day-precision Subject Time 答案，Provider 零新增数据用途；连续时间查询会像任何已提交对话一样成为下一次查询的“上次聊天”。
