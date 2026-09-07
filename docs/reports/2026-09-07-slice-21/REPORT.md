# Slice-21 报告

最终状态（2026-09-07）：**有界近期对话切片已完成真实隔离验收，395 passed，build `dogfood-s21`。** 两次真实失败、修复、重启与遗忘外发检查及未解决的普通换题问题见 [真实验收报告](LIVE-ACCEPTANCE.md)。以下为先前 checkpoint 的历史原文，不代表当前仍等待授权。

## 先前待真实验收 checkpoint（保留历史）

状态：**实现与自动化检查完成，真实 UI / DeepSeek / 进程重启验收未执行，切片未收口。** 开发 build `dogfood-s21`；已验收主线仍为 `dogfood-s19`。基线 `7082a41`。

## 授权与工具阻塞

用户以“确认”同意上一轮提出的精确用途：仅 Living Memory 的 DeepSeek reply 获得当前身份最近最多两轮完整 committed `{user_text, assistant_text}`，合计不超过 4,000 字符，仅用于指代/续写，不作状态证据；更正/遗忘/身份/完整性不能安全确认时不外发，其他请求与调用预算不变。

本轮准备通过 `.scratch/s21_ui.py` 创建新的临时隔离根，用项目原创虚构对话进行真实验收。启动在 CreateProcess 前被自动审核拒绝：审核认为当前可信用户消息未明确列出历史 payload 和目的地。随后对**同一命令**附上上述授权上下文重试，仍被拒绝，理由是不接受助手说明中的授权转述。没有换命令、换 Provider、开浏览器或间接启动来绕过。

因此本轮没有启动真实服务、没有新建真实验收身份，也没有向 DeepSeek 发送本次新增历史。helper 仅为待用脚本，未运行；其设计只观察实际 transport 的轮数、字符数、键集合和固定虚构 canary 是否出现，不打印历史、密钥或认证头。

需要用户直接用完整授权句确认后，再经同一工具审批执行真实验收。该阻塞不是应用功能失败，也不是验收通过。

## 已实现

- `RecentDialogueTurn` 只含 user/assistant 文本。选择器最多取最近两个完整轮次，总计 4,000 字符；按完整轮次裁减，不越过新轮回填旧内容，不建 chat store。
- Runtime 只给 Living Memory reply 一个惰性只读来源。Timeline 校验当前身份的完整历史、当前 attempt 与已持久冻结的全部 basis；既有 UI 20 轮视图不被直接外发。
- 当前明确记忆控制、数据更正/遗忘或本轮 Memory REVISE 不增加历史；历史中的控制轮、Memory 修订、不明确/失败结果和未知 legacy summary 构成窗口截断。
- 其他 pending/interrupted/unfrozen Admission 阻断历史。失败的控制请求持续阻断；其他失败按冻结 head 隔离此前文本。没有删除或改写这些操作。
- 只有已识别的 canonical reason code、规则版本及完整 Memory 结构能证明非修订；未知或缺字段结构不默认当安全 NoOp。
- LM reply 新增 `recent_dialogue` 和对应用途提示，Adapter 再次校验类型、两轮及字符上限。六类 proposal/classification 和其他五类 reply 的字节基线不变，不新增调用。
- 近期对话仅影响回复，不进入状态候选。明确续写有安全前文时可交付文本；缺少安全前文或可选回复失败时要求重述。
- 本地 `ExpressionCandidate.dialogue_priority` 保护上下文回复/重述提示，不被普通状态 carry 覆盖；显式状态查询优先级保持。该位不外发、不持久化。

## 自动化与第一次失败

通过 ApplicationFacade 覆盖普通对话、两轮截取、预算、Memory 不凭历史写入、重启、production composition 双身份隔离、篡改历史、控制请求当前/后续、不成功的控制请求，以及实际 Composite 状态优先级。底层 Timeline 的 legacy fixture 与冻结 basis 使用已有 Module Interface 验证，不修改产品数据库 schema。

- 第一次正向测试确认旧实现没有给 reply 前文，先红后绿。
- 只取 committed 历史的初版会忽略失败/中断的遗忘请求，导致此前暗号重新进入 reply；新增未发布 Admission 检查后通过。
- 审查发现否定留存/再说、英文 Delete、明确 Memory 数据更改仍可能被当普通对话；将这些控制路径补为保守截断，并验证当前轮和后续轮。
- 未知 JSON（无 Memory 或缺少 supersedes 等字段）曾被误认作无修订；收紧已知 code/version/结构，保留未知为不可用。
- 产品 Composite 曾用 gentle carry 替换已获得前文的续写；用真实组合测试复现，增加本地发言优先位后，续写交付且显式姿态查询仍优先。
- 防御检查从“传入 head 等于当前 head”加强为持久 attempt/完整 frozen basis 匹配；错误 head 及历史推进后误传当前 head 均关闭。
- 三个旧 outbound 断言因已获准的 LM 新字段/提示失败；只更新 LM 字段与其固定 hash，其余 11 类旧 hash 和投影要求保留。

最终命令：`pytest -q -p no:cacheprovider --basetemp=<唯一临时目录>`。

结果：**390 passed in 205.94s**。此前相关集合为 91 passed。新增测试不使用真实 Provider；这些数字不证明实际生成质量或真实重启体验。

## Standards

复查确认已关闭：撤回措辞遗漏、未知 summary 默认安全、冻结 basis 防御缺口。未发现第二 store、额外数据用途/调用，或本地发言优先位进入 Provider/Domain/canonical Expression。最终无剩余硬规范问题；未重复运行全量或真实调用。

## Spec

复查确认已关闭：明确否定留存/Memory 数据更改仍外发，以及产品 carry 覆盖续写。普通“把上一句改短一些”保留；显式状态查询仍优先。本地 metadata 未越界。最终无剩余代码层阻断，但明确要求按待真实验收 checkpoint 记录，不可宣布切片完整完成。

## 限制与待办

- 控制/续写语法是有限的保守规则，不是任意自然语言意图识别保证；包含数据控制、更正前查询等词时可能不提供历史。
- 未解决的失败隐私控制会持续阻断历史，不能自动认为后来聊天恢复了授权；原有无历史路径可继续。
- 更正/遗忘保护只限制新增历史用途，不改变原有 active Memory 投影、数据删除或历史展示语义。
- 仅两轮、整轮预算或不安全历史导致前文为空时，应让用户重述；不承诺完整长对话理解。
- 仍须真实隔离 UI 验证：自然指代/纠错后续写、普通 carry 下交付、关闭重启继续、隐私 canary 在控制当前及后续请求中不外发、没有额外 Provider 调用。
- 未访问正式身份、旧救援仓库；未创建新 Provider、后台活动、Lifeworld、Agency 或 Reflection；未删除测试根或 helper。

独立开发分支保留此 checkpoint，完成工具授权及真实验收后才能收口和合入主线。
