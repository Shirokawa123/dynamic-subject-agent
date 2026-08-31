# Slice-09：来源候选人工选择与未封存草稿

状态：done（2026-09-01）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用户从 Slice-08 的结构通过候选中逐条选择 Genesis/Knowledge，明确确认“本地保存来源草稿”后，将来源文本、digest、候选和选择结果保存为一个未发布、未封存草稿。关闭重开后可继续查看和调整选择，也可通过显式按钮删除；草稿不修改 Avery、不进入 Timeline、不创建身份。

## 用户授权

2026-08-31，用户在获知新增本地持久化用途和显式删除能力后回复“继续吧”，批准本切片。授权仅覆盖用户逐次确认保存的一份来源草稿及其本地删除；不覆盖自动保存、正式/私人来源、封存、身份创建、runtime 注入或新的 Provider 外发。

## 草稿不变量

- 最小产品同一时刻只有一个 active 来源草稿；draft revision 单调递增，保存选择只追加新 revision，不原位改写旧 revision。
- 原文、source title、source digest、结构通过候选和 selected 状态绑定同一 revision；Server 重新校验逐字证据、类型、项数和 digest，不信任浏览器提交。
- 至少选择一条 `identity` Genesis；Knowledge 可选。未选择候选仍保留在草稿中供后续调整，但 rejected Provider 候选不得保存。
- 草稿属于预封存 authoring 状态，不是 Profile、GenesisSnapshot、KnowledgeSnapshot、QRI、Timeline 或 runtime 状态。
- 删除只由用户显式按钮触发，删除整个草稿及 revisions；不删除 Avery、credential 或聊天数据。

## 架构宿主

- 优先复用 `SubjectStudio` 的 unsealed draft/provenance Interface；若现有 Interface 不能表达预封存人工选择，则在 Studio Module 内新增 draft seam，不在 Desktop、Timeline 或并行产品数据库建立第二个 canonical 身份。
- `ApplicationFacade` 仍是 Windows Presentation 唯一 Interface，提供 save/query/delete 三个有界 authoring 命令；运行时 submit/query 语义不变。
- 草稿 persistence 只在 `open_local_product` 的显式 product root 下；源码仓库、环境变量和 credential store 不保存来源。
- Slice-08 DeepSeek 预览用途不变；save/query/delete 不调用 Provider。

## 实施顺序

1. 审计 SubjectStudio draft、preview、freeze、provenance 和恢复 Interface，确认唯一写入位置。
2. 建立 draft request/result、候选复核、append-only revision、恢复和删除行为测试，全部经 ApplicationFacade。
3. 接入 Slice-08 页面：结构通过候选复选、保存用途确认、保存/加载/调整/删除；刷新仅清除临时预览，已保存草稿由显式加载恢复。
4. 使用全新 project-original 文本完成真实 DeepSeek preview → 选择 → 保存 → 关闭重开 → 调整 revision → 删除；核对 Timeline/Avery/credential 不变。
5. 对抗性复核伪造候选、非逐字 evidence、错误 digest、无 identity、重复保存、并发 revision、未确认保存和非显式删除；全量回归、commit、push。

## 范围外

- freeze/publish、创建或替换身份、启动候选角色、runtime Knowledge 注入。
- 候选自由编辑、无证据改写、自动选择、自动保存和多草稿列表。
- PDF、视频、音频、私人来源、目录扫描和新增 Provider 数据用途。
- Agency、effect、Reflection、主动消息或提醒。

## 最小验收

- 未确认本地保存、无 identity、候选被篡改、证据非逐字、digest 不匹配均拒绝且磁盘零写入。
- 首次保存生成 revision 1；调整选择生成 revision 2；重放同一 request digest 不重复增写；stale base revision 冲突。
- 关闭产品重开后 query 只返回当前草稿的可见来源标题、digest、candidate 内容/证据/选择和 revision，不暴露内部 ID、路径或原始 Provider response。
- 显式删除后 query 为 absent；Avery Timeline head、runtime 状态、credential 和其他数据不变。
- Windows 真实流程、控制台、全量测试、commit 和 push 均完成；任务书如实记录遗留限制。

## 收口记录

- 审计确认既有 Genesis draft 已要求完成映射的 Profile/Premise，不能承载预封存候选选择；因此在 SubjectStudio root 内 lazy 创建 `source-character-draft` sidecar，不迁移现有 ProfileStore，也不建立 runtime/身份第二真相。
- `ApplicationFacade.source_draft` 提供闭集 save/query/delete；首次保存 revision 1、相同 request digest 幂等重放、selection-only revision 2、stale base conflict、完整 revision 链 digest 复核、显式级联删除均由行为测试覆盖。未确认保存、伪造 evidence、basis 偷换、无 selected identity、错误 command 形状均拒绝且不创建 sidecar。
- 首次真实 HTTP 保存暴露 SQLite writer 跨线程错误：测试同线程通过，ThreadingHTTPServer 失败关闭且零草稿写入。修复为每个请求线程按 StudioRootRef 打开/关闭 SubjectStudio，并新增真实 threaded HTTP 回归。
- 真实 project-original Windows 流程完成 DeepSeek preview → 人工选择 3 Genesis + 1 Knowledge → 保存 revision 1 → 关闭重开恢复 → selection-only revision 2；页面不回显原文，Avery 所有状态不变，Timeline head 为 0，控制台无错误。
- 用户在删除前获知精确数据范围并明确回复“确认删除草稿”；真实删除后 `draft_rows=0`、`revision_rows=0`、空 manifest 保留，Timeline head 仍为 0。隔离 product root 已确认只位于系统 Temp，但主机策略拒绝递归清理，现保留为空草稿的可删除临时运行结构。credential、Avery、聊天、正式身份、旧仓库和私人资料均未读取或修改；全量 `240 passed`。剩余边界：草稿尚不能映射、freeze、发布或启动新身份。
