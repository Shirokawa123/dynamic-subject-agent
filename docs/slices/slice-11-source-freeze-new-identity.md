# Slice-11：来源草稿封存并创建新隔离身份

状态：done（2026-09-01）。规模预算：≤ 3 个工作会话。

## 已授权不可变操作

用户明确授权以完整 Freeze Basis `e99264f690cc278d702ecf0470a3cf5b1e06fd43060b645db02cb2a902311343` 封存真实 Source Draft revision 1，并创建新的隔离身份。该操作不得覆盖现有 Avery 身份，不删除或改写 Source Draft，不读取旧救援仓库、私人数据或正式身份；若提交前重新计算的 basis、revision、source digest、selection 或映射内容任一不符，必须在任何不可变写入前 typed 拒绝。

## 用户可见结果

用户确认 exact Freeze Mapping 后，产品原子地封存其 Profile、Genesis 与 Knowledge，发布对应 QRI，并注册一个新的本地隔离身份。用户可切换到该身份并启动真实 Windows runtime；重启后仍加载同一身份、同一封存内容和独立 Timeline，Avery 的身份、QRI、Timeline 与运行时状态保持不变。

## 封存契约

- Freeze 命令必须携带 exact basis 和预期 draft revision；SubjectStudio 在写入事务内重新校验完整 Source Draft revision 链并重算 mapping，不信任客户端回传映射。
- 同一 basis 重试返回同一 sealed identity 与 QRI，不重复创建身份、snapshot 或 Timeline；不同 basis 不得复用该身份。
- Profile、Genesis snapshot、Knowledge members 与 QRI 必须来自 Slice-10 exact mapping；未选择候选、原文、运行时历史或现有 Avery 状态不得混入。
- 新身份的初始 Relationship 固定为空，Timeline 从 head 0 开始；来源不能预写已赚取的 Memory、Relationship、目标、承诺、Situated State 或 Medium State。
- Publication 必须原子且可崩溃恢复；不得出现“已注册身份但 snapshot/QRI 缺失”或“QRI 可见但身份不可打开”的半发布状态。
- Source Draft 仍是未封存草稿记录，保留 revision 与删除能力；Sealed Identity 只保存获选映射及其 provenance，不把整份来源复制进 runtime authority。

## 架构宿主

- `ApplicationFacade` 提供一个高层 freeze Interface；SubjectStudio 深 Module 在事务内完成 basis 复核、snapshot/QRI 发布和幂等裁决，Desktop 不自行编排写入步骤。
- `open_local_product` 继续作为 production composition root；本地身份注册只保存打开隔离产品所需的最小引用，不让 Desktop 直接持有 Studio、QRI、provider 或 canonical store。
- Knowledge snapshot/QRI 必须真实承载 mapping 中的多个 Knowledge member，并成为该身份 Knowledge runtime 的 sealed authority；不得以代码内 Avery fixture 或仅显示预览冒充生效。
- 现有一条 RuntimeTimeline 一个写入者/一个 canonical store、模型只提议 Python 裁决、typed NoOp/unavailable/FailedClosed 区分均保持不变。

## Provider 与 Credential 边界

- Freeze、identity registry 与本地切换不调用 Provider，也不重新发送来源文本。
- 新身份启动后沿用已授权 `default` DeepSeek cognition 用途及现有六类最小投影；不新增 Provider 数据用途、provider profile 或 credential slot。
- 如果实现需要超出现有 Provider 投影，停止并请求新授权，不随本切片扩权。

## 实施顺序

1. 只读核对真实草稿 revision、完整 Freeze Basis、现有 Studio seal/Knowledge snapshot/QRI 与本地身份组合链；若当前持久化不能真实承载多 Knowledge member，先在同一深 Module 内补齐封存语义和 Interface 行为测试，再触发真实不可变写入。
2. 建立 exact-basis freeze 命令与 typed 结果，覆盖 stale/tampered basis、重复重试、半发布恢复和现有 Avery 不变。
3. 经 `ApplicationFacade` 完成新隔离身份注册与切换；Windows 页面只呈现可理解的封存确认、身份选择和启动结果。
4. 对正式授权的真实 basis 执行一次 freeze，验证 Profile/Genesis/Knowledge/QRI、独立 Timeline、真实 DeepSeek 对话和产品重启恢复。
5. 对抗性审查未选择候选泄漏、关系预写、fixture 回退、跨身份串线、重复 freeze 与崩溃窗口；发现问题先修复再全量回归。
6. 更新权威文档、commit、push；记录仍不在范围内的内容。

## 范围外

- 编辑或替换 sealed identity、合并身份、覆盖 Avery、删除 Source Draft 或迁移旧救援/正式身份。
- PDF、视频、音频、私人来源、自动抓取、来源再解释或模型二次补写。
- Agency、effect、人格发展、Reflection、主动消息、身份间共享 Memory/Relationship 或后台主动运行。
- 新 Provider、新 credential 用途或扩大现有 Provider 最小投影。

## 最小验收

- 写入前完整 basis 与 revision 精确复核；任一篡改或 stale 请求零 snapshot、零 QRI、零身份、零 Timeline 写入。
- 首次 freeze 只创建一个新 sealed identity；相同 basis 重试 byte-equivalent 且各类计数不增长。
- 新身份的 Profile/Genesis/两条 Knowledge 与 Slice-10 mapping 一致，QRI 引用全部 sealed authority；Knowledge runtime 不使用 Avery fixture。
- Avery 的 Profile/QRI/Timeline head/运行时状态前后不变；新身份 Timeline 初始 head 0，真实对话后只推进自己的 canonical store。
- Windows 真实流程可选择新身份、启动、对话并重启恢复；控制台无未处理错误。
- 全量测试、对抗性审查、commit、push 完成；未通过时诚实保留失败证据，不把部分封存报告为身份完成。

## 收口记录

- 只读审计先证实现有 `seal()` 将 Knowledge 强制为空、runtime 固定读取 Avery fixture；在真实不可变写入前把 ProfileStore 升为 migration-free 双读（v1/v2），v2 KnowledgeSnapshot 封存最多 6 条带 member digest/evidence/source provenance 的内容，并由 composition root 按当前 QRI 注入 runtime。只有旧 publication key 使用兼容 fixture；来源身份 0 member 明确保持 0。
- exact freeze 命令在 source Studio 重读完整草稿链并重算 basis；目标 Studio、Profile、draft、FreezeDecision 和 QRI 均由 basis 稳定派生。相同 basis 重试不增量；QRI 后 registry 写失败可恢复，已封存 snapshot 可由同一 exact PolicyQuestion 重新授权 QRI 发布。registry 保留原 authority，首次选择才创建独立 Host/Timeline。
- 对抗性用例覆盖 tampered basis、registry 中断恢复、草稿 revision/delete 后 basis 回放、freeze 期间并发 revision 锁、单次 authority load、registry label 篡改、Host/QRI 绑定、Desktop composition 失败回滚、Knowledge member 直接篡改、0 member fixture 泄漏和跨身份切换；直接篡改 member 摘要失败关闭。真实切换发现页面 DOM 残留上一身份对话，已改为切换成功后清空会话画面并标记“原有身份/来源封存”。
- 两轴独立代码审查最初发现 exact mapping→write 竞态、DeepSeek 双次 authority load、registry/Host 未绑定、Desktop 绕过 Facade 读取 Knowledge/source digest 和切换失败语义；全部修复后复审无阻塞项。Knowledge 数量/引用标题现在只经 Facade 投影，UI 只显示“封存来源”。
- 真实 Windows 流程以完整 `e99264f690cc278d702ecf0470a3cf5b1e06fd43060b645db02cb2a902311343` 创建 profile `4415a65d-77e8-55b2-a539-e21ed3899709`，封存两条 Knowledge；新身份 initial head 0，四次真实 DeepSeek 对话（含重启和最终修复后复验）引用截单时间/样张确认，最终 head 4。原 Avery Profile/QRI/Timeline `eb9cd030-...` 保持 head 0，Source Draft revision 1/source digest 保留；两个 Studio 各 1 Profile/Genesis/Knowledge/QRI，控制台无错误。
- 全量 `252 passed`。当前真实隔离根保留两身份并以“来源封存”身份为 active；本切片未删除草稿或测试根。范围外仍是视频/音频、私人来源、身份编辑/合并、Agency、effect、人格发展、Reflection、主动消息及新 Provider 数据用途。
