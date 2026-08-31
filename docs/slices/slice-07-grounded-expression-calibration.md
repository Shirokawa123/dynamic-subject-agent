# Slice-07：既有能力的有依据表达校准

状态：done（2026-08-31）。规模预算：≤ 2 个工作会话。

## 用户可见结果

当 Memory、Knowledge、Relationship、参与者目标/承诺、Situated 与 Medium 在同轮并存时，最终回复保持一条清晰主干，只让确有补充价值的能力发言；状态仍可裁决和提交，但不再因每项都生成完整回复而重复安慰、重复目标、互相矛盾或暗示未授权执行。

## 修改前判定标准

先以全新隔离身份和真实 DeepSeek 固定下列场景，不根据修改后结果倒推标准：

1. 普通闲聊：只诊断当前保守 unavailable，不在本切片增加基础表达用途。
2. Memory + Knowledge：事实答案不得夹带“没有记录/没有相关信息”等跨能力矛盾。
3. 明确目标 create/query：query 保持 Python 独占；create 不重复三次确认同一目标。
4. Situated + Medium：同轮至多一个状态回复片段，短时姿态优先于中期基线发言；两项状态仍各自裁决并在页面解释。
5. 关系声称和直接状态命令：拒绝表达不得被其他能力改写成接受或顺从。
6. Provider 单项 FailedClosed：失败项不得发言，其他有依据能力仍完成回复。

## 权威边界

- `ApplicationFacade`、单写入者、原子 Publication 和四 Domain 裁决不变。
- 六类 Provider 请求继续独立构造既有最小投影；不发送其他能力回复、历史消息或跨 Domain 状态。
- 只调整各能力何时参与最终表达、能力本地 reply contract 与 Python 组合/去重；不建立统一表达模型任务。
- 不把“页面解释”当成回复质量，不为通过验收隐藏 FailedClosed、Rejected 或 NoOp。
- 若普通无能力对话被证明是主要问题，停止扩权并记录为新的 Provider 数据用途候选。

## 实施顺序

1. 修改前使用真实 Windows 页面跑预定场景，逐轮保存可见输出和 typed 解释摘要。
2. 区分 Provider 局部回复问题与 composite 选择问题，只修改实际复现的缺陷。
3. 以 Facade 行为测试守护发言预算、主干优先级、局部失败、跨能力矛盾和持久状态不回归。
4. 使用新的隔离身份完成修改后真实长链、关闭重开和对抗性复核；发现问题继续修复，不选择性报告。
5. 全量回归、更新权威文档、commit 并 push `origin/main`。

## 范围外

- 通用对话基础表达、统一表达层、跨能力统一 prompt 或把一个能力的输出发送给另一个 Provider。
- Agency、effect、人格发展、Reflection、主动消息、提醒或后台执行。
- 新 Provider、历史消息、正式身份、旧救援仓库、私人资料和来源建角。
- 用随机语气、固定口头禅或无证据拒绝制造主体感。

## 最小验收

- 修改前后各使用独立临时身份、生产 composition、真实 DeepSeek 和本地 Windows 页面；不使用测试 Provider 代替真实流程。
- 同轮 Memory/Knowledge/目标/状态最多形成一个主回答和一个非重复补充；Situated 与 Medium 同时 relevant 时只一个状态片段发言，但两个 typed 结果都提交可见。
- 目标直接查询无 Memory/Knowledge 混入；关系声称和直接状态命令保持拒绝；Medium 回复不承诺现实执行。
- 单项 FailedClosed 不发言、不写该项状态且不阻断其他能力；重启后 canonical 状态与页面一致。
- 页面无内部 ID/credential，控制台无错误；全量测试通过并独立提交推送。

## 收口记录

- 修改前隔离真实基线确认：普通对话、Knowledge、目标直接查询和拒绝表达已有单一主干；Situated+Medium 同时 relevant 时重复生成完整安慰，目标 mutation 又把 Python 样板、Memory 确认、Knowledge 建议和 Medium 提问叠加。
- composite 建立确定性发言预算：目标 mutation 有其他主干时不说样板句；Memory/Knowledge/目标主干存在时状态只裁决不追加；状态独占时 Situated 优先，显式 Medium 查询可覆盖 Situated carry。六能力同轮仍全部提交，表达不再靠每项发言证明集成。
- 真实修改后流程继续发现并修复 Living Memory 提议未授权提醒、Medium 补充重复提问、当前“请温柔”边界请求误写为已尊重边界，以及直接状态查询暴露 `concerned`。Provider 局部合同、Relationship Python 回顾证据和确定性中文映射均增加行为测试。
- 最终隔离 Windows/DeepSeek 验收：双状态只一条回复但两项解释均可见；目标 create/revise 无样板重复或提醒提议；事实主干抑制状态复述；当前边界请求不写关系；显式 Medium 查询回答“关切”并保持 carry 裁决。关闭重开后目标、计划记忆、空关系与 concerned/v1 一致，控制台无错误，全量 `227 passed`。
- credential 仅经 Windows Credential Manager 进入生产 Transport；未读取或显示 key，未打开正式身份、旧仓库或私人资料。3 个 Slice-07 验收根只位于系统 Temp；主机策略预计仍会拒绝递归清理。剩余边界：本切片未增加通用对话任务，Memory+Knowledge 主干可保留多个互补事实段落，但不再追加无上下文状态复述。
