# Slice-13：Dogfood 发行与连续体验基线

状态：done（2026-09-01）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用户从仓库双击 `启动Avery.bat` 后，可以确认当前 dogfood build、当前隔离身份与封存 Knowledge 数量；完成对话、关闭产品并重新启动后，页面恢复当前身份最近最多 20 个已提交对话轮次。启动、身份打开或提交失败时，页面提供可行动的中文说明，并明确“未提交/既有状态保持”，而不是只显示内部错误码。

## 体验契约

- 历史只来自当前 active identity 的 canonical RuntimeTimeline；不新增 UI chat log、SQLite sidecar、浏览器存储或跨身份 transcript。
- 只恢复已原子提交的 `SubjectCommand.utterance + Expression.text`；pending、interrupted、FailedClosed 无 outcome 的操作不显示为完成对话。
- 默认最多 20 轮，按 head sequence 升序；切换身份立即清空旧 DOM 后加载目标身份历史。原身份与来源身份不可互见。
- 页面显示固定 dogfood build identity，不读取 git、环境变量或网络；build 文本不得伪装成发布版本。
- 错误文案由 typed status/stage/code 的闭集映射生成；未知错误显示失败关闭，不推断原因，不泄露内部路径、ID、credential 或 source digest。
- 本切片不改变 cognition、Domain 裁决、Provider outbound、Timeline Publication 或现有持久化 schema。

## Module 与 Interface

- `TimelineEngine` 深 Module 新增一个只读 conversation-history Interface，内部验证 command fingerprint、Expression digest、authority、head sequence 与 published outcome 完整性。
- `SubjectRuntime → RuntimeLease → ApplicationFacade` 只转发 typed history projection；Desktop 不查询 SQLite、RuntimeHost 或 Timeline。
- build identity 是产品常量，经 AppState 投影到页面；不新增独立 version store 或运行时探测 seam。
- 现有身份切换仍由 `ApplicationFacade`/`LocalIdentityAuthority` 裁决；Desktop 仅在新 composition 可用后重载 canonical history。

## Provider 与数据边界

- history/build/error 查询完全本地，不调用 Provider。
- 历史 Projection 只包含用户可见 utterance、assistant expression、language、head sequence 和 published time；不包含 operation/outcome/plan/experience/memory/source ID。
- 不增加遥测、反馈上传、日志上传或 credential 用途。

## 实施顺序

1. 建立 canonical conversation turn 类型和 Timeline 查询，覆盖 limit、顺序、pending/interrupted 排除、command/expression 篡改与跨身份隔离。
2. 经 RuntimeLease 和 ApplicationFacade 暴露 History query；Desktop snapshot 不直接读取下层 authority。
3. 页面在启动/切换后恢复 history，并显示 dogfood build 与当前身份标签；发送新轮次不得重复渲染。
4. 将 credential、product-open、turn、authoring/freeze/select 的常见 typed failure 映射为可行动中文，并保留原始 code 仅供本地诊断字段，不直接作为主文案。
5. 使用全新 dogfood root 和既有 Slice-11 双身份 root 做 Windows 真实流程：启动→两轮→关闭→重启恢复→切换隔离→切回；检查控制台与数据边界。
6. 两轴审查、全量测试、文档、commit、push；停在首次用户体验前给出明确启动步骤。

## 范围外

- 新聊天能力、统一表达层、历史搜索/编辑/删除/导出、Markdown 富文本或附件。
- 安装器、自动更新、崩溃遥测、反馈收集或云同步。
- 视频/音频/PDF、私人来源、正式身份迁移、Agency、effect、人格发展、Reflection 或主动消息。

## 最小验收

- 关闭前 1～20 个已提交轮次在重启后 byte-equivalent 恢复；第 21 轮只淘汰最旧的显示项，不改变 Timeline。
- pending/interrupted/FailedClosed 不伪装成已完成；command、Expression 或 head 链篡改导致 History query FailedClosed。
- 两身份各自恢复自己的 transcript；切换后 DOM 不残留上一身份内容。
- 页面显示 dogfood build、身份来源标签和 Knowledge 数；控制台无未处理错误，主错误文案不出现裸 code/path/ID/source digest。
- Provider 零新增调用/字段；全量测试与两轴审查无阻塞，真实数据不删除、不迁移。

## 收口记录

- 新增 `ConversationTurnRecord` 与 `TimelineEngine.list_conversation_turns(limit=20)`；History 每次按 head 1..N 重建全部 committed outcome，经既有 `query_outcome` 验证 plan/domain/Expression/outcome/receipt digest，再验证 previous digest 全链及最终 digest=head，最后只返回最近 20 轮。Runtime/Lease/Application 只转发 typed projection，Desktop 没有 SQLite/chat store 写权。
- 专项测试覆盖 21 轮窗口与重启 byte-equivalent、pending/FailedClosed/interrupted 排除及 interrupted 恢复、command/Expression/head/outcome/previous digest 篡改、两身份 transcript 隔离、history 查询零额外 cognition、Desktop canonical 20 轮响应和 history FailedClosed status；实时成功响应携带 canonical window 重建 DOM，第 21 轮不会无限 append。
- 页面显示固定 `dogfood-s13`；启动、credential 后和身份切换后加载 canonical history。主错误文案使用 exact `(stage, code)`/stage 闭集，未知值统一 FailedClosed；fetch 与身份切换异常使用固定中文，不显示浏览器 error/path/code，并且只有目标 history 成功加载后才关闭建角页。网络中断真实对抗显示“切换状态尚未确认”，控制台无未处理错误。
- 真实 Slice-11 双身份 root：来源身份启动恢复 4 轮，切原身份显示 0 轮，切回恢复 4 轮；新增第 5 轮保留 Knowledge 引用且无重复，关闭重启恢复 5 轮，原身份 head 0、来源 head 5。全新 `dsa-s13-fresh-real-...` root 首启显示 build，完成两轮真实 DeepSeek 对话后关闭重启恢复两轮，head 2；两处控制台均无错误，临时数据保留未删除。
- 两轴初审发现 outcome/head 链未验证、实时第 21 轮不裁剪、substring 错误分类、fetch 泄漏、失败类型/双身份证据不足和切换 Promise 无异常边界；全部修复后 Standards/Spec 复审无阻塞。全量 `265 passed`。`dogfood-s13` 现已达到首次 20～30 分钟用户体验点，本切片未增加 Provider 字段、调用或 credential 用途。
