# Slice-05：Windows 隔离身份真实长链与重启验收

状态：done（2026-08-31）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用全新隔离产品身份在真实 Windows 页面完成一条覆盖六项能力的连续对话；关闭产品并重新打开后，记忆、关系、目标、短时姿态和中期基线按各自规则恢复，用户可直接体验当前最小产品。

## 安全边界

- 只在新的系统临时目录创建 Studio、Host、Timeline 和身份；输入均为本任务 project-original 文本。
- 只通过生产 CredentialStore/DeepSeek Transport 使用 Windows Credential Manager 中已配置的 credential；不得读取、显示、记录、导出或写入 key。
- 不打开、查询、修改或迁移默认正式身份、旧仓库运行数据、私人来源或用户历史消息。
- 沿用六项既有 Provider 投影授权，不新增字段、用途、Provider 或隐式 fallback。

## 长链范围

1. 启动生产 composition 与 Windows HTTP/UI Adapter，确认初始空状态和 credential configured/verified 状态不泄露 key。
2. 真实 DeepSeek 依次覆盖：Memory 创建与换说法召回、Knowledge 命中、Relationship 正向证据与关系声称拒绝、目标创建与查询、Situated set/carry/consume、Medium 双独立证据迁移。
3. 中途关闭产品并用同一隔离 Host/Studio/Timeline 重开；经 ApplicationFacade 和页面同时核对恢复状态。
4. 检查每轮 typed 决策、表达依据、控制台错误、内部 ID/credential 不出现在页面或返回投影。
5. 全量回归、最终对抗性审查、commit；网络可用时 push 所有待同步提交。

## 范围外

- 正式身份人工验收、旧数据迁移、删除或不可逆操作。
- Agency、effect、人格发展、Reflection、主动消息、提醒或后台行为。
- 新数据用途、新凭据用途、新测试基建、证据目录或验收脚本入库。

## 验收

- 新隔离身份的真实长链每轮终态可解释，六项能力均至少一次产生有效 typed 决策。
- 关闭重开后 canonical 状态一致；Situated 只按一次 carry 规则延续，Medium 只在双独立证据后转换。
- Windows 页面显示当前状态与逐轮决策，无控制台错误、内部 ID 或 credential 暴露。
- 全量测试绿，任务书记录事实，独立 commit 并 push；随后只请求用户一次最终真实体验确认。

## 收口证据

- 两次全新临时身份真实 DeepSeek 长链均完成：Memory create/重启后 recall、Knowledge citation、Relationship 正向事件与声称 no-update、目标 create/query、Situated focused set/重启恢复/carry/consume、Medium concern 双证据 settled/v0 → concerned/v1。
- Windows 页面显示生日记忆、2/3 条 accepted 关系互动、目标、concerned/v1；页面追加 gentle set → carry → neutral，控制台无错误。
- 可视复核发现并修复 memory ID 前缀泄露；Desktop snapshot 行为测试确认不含 `memory_id`，修复后页面只显示类型与内容。
- credential 由 DesktopState 经 Windows Credential Manager 加载，仅传入生产 Transport；未打印、记录、导出或写入仓库。临时身份与临时验收脚本均已清理，正式身份未打开。
- 最终全量 `223 passed`；Slice-03、Slice-04 已推送，当前切片独立提交后推送。
