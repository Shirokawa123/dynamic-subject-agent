# Slice-06：既有能力的体验可辨识度与因果解释

状态：done（2026-08-31）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用户在自然对话中不仅能看到 Memory、Knowledge、Relationship、参与者目标/承诺、Situated State 与 Medium State 的结果，还能用产品语言理解本轮哪些既有能力实际参与、依据是什么、产生或保持了什么，以及仍会如何延续；普通 NoOp 不伪装成变化，Provider failure 不伪装成成功。

## 问题假设

当前六项能力、原子 Publication、持久身份和重启恢复已经成立，但短暂体验仍可能主要像普通聊天。先区分三个问题：能力没有被自然触发、能力已触发但页面只显示技术标签、页面可见但回复影响仍不足。本切片只解决前两项；若真实证据最终指向表达强度问题，只记录为后续候选，不在本切片建立统一表达层或改变 Domain 语义。

## 权威边界

- `ApplicationFacade` 仍是唯一产品业务 Interface；桌面 Adapter 只消费已提交 Outcome 和可查询投影。
- 不改变六项 Domain 的候选、证据门槛、状态机、持久化或失败语义。
- 不合并六类 Provider 投影，不新增 Provider 字段、用途、Provider 或 credential 用途。
- 解释只能由 Python 根据 typed Outcome、已提交状态与现有可见内容确定性生成；不得让模型事后编写理由。
- 页面不得暴露 canonical memory/source/record/Timeline/profile ID、credential、数据库行或隐藏历史。

## 实施顺序

1. 使用全新隔离产品身份、生产 composition、Windows Credential Manager 中既有 DeepSeek credential 和真实本地页面，先完成修改前自然流程；如实记录可辨识度痛点和意外行为。
2. 从 `ApplicationFacade`、桌面投影和页面呈现交叉定位问题，只实现能由真实证据支持的最小改动。
3. Interface 行为测试覆盖解释的来源、NoOp/Rejected/FailedClosed 区分、重启投影和内部 ID/credential 不泄露。
4. 全量回归后，以新的隔离身份重新执行真实流程；不得复用修改前状态来制造成功。
5. 对抗性审查直接命令状态、虚假关系声称、模糊目标、Provider 单项失败、过期/消费状态和普通闲聊，发现问题即修复并复验。

## 范围外

- 统一表达层、跨能力统一 prompt、Agency、effect、人格发展、Reflection、主动消息或提醒。
- 新状态、新关系语义、新知识源、视频/文本来源建角或 SubjectStudio 产品入口。
- 正式身份、旧救援仓库、私人资料或用户历史的读取、迁移、删除和修改。
- 新 Provider 数据用途、历史消息投影、跨能力合并投影或隐式 Provider fallback。

## 最小验收

- 修改前和修改后各使用独立临时身份完成真实 DeepSeek + Windows 页面旅程，并保留不含私人数据和 credential 的结果摘要。
- 页面以用户可理解的语言区分：本轮使用了既有内容、形成了新记录、证据不足而保持不变、状态延续/消费/过期、能力 FailedClosed。
- Memory 召回、Knowledge 引用、Relationship 声称拒绝、目标 create/query、Situated set/carry/consume、Medium 单证据保持与双证据转换均能从页面解释，且解释与 canonical Outcome 一致。
- 普通闲聊不会显示虚假变化；直接状态命令和单方面关系声称不会被包装成已接受事实；单项 Provider 故障不污染其他能力解释。
- 关闭重开后页面只显示仍有效的 canonical 状态；全量测试通过；独立 commit 并 push `origin/main`。

## 收口记录

- 修改前隔离真实长链确认：每轮 `no-update · settled` 技术噪声、英文 action/status、关系拒绝与目标查询原因不可见、新记忆提示指向旧记录、Situated 消费不可解释；真实 Provider 波动形成过目标 FailedClosed，未掩盖。
- Facade 新增只读 reason/selected count 投影；目标直接查询的 selected usage 进入 canonical Outcome。桌面只用 Python 将结果翻译为“形成/召回/保持/失败”，不暴露内部 ID，真实失败明确说明其他能力仍有效。
- 真实流程继续发现并修复：自然“我现在的目标是什么”未走 Python、无目标消息仍外发目标分类、单词“必须”误触 Knowledge、Provider NoOp 让直接状态命令绕过 Python 拒绝、Situated 命令污染 Medium、目标查询混入 Memory/Knowledge、跨能力缺失声明回退以及高相似状态回复重复。
- 最终隔离 Windows/DeepSeek 长链验证直接状态命令双层拒绝、Situated set/carry→neutral、Medium 独立证据→concerned/v1、目标 create/自然 query、Knowledge citation；关闭重开后目标、计划记忆和 concerned/v1 恢复，页面无技术枚举或内部 ID。全量 `225 passed`。
- credential 仅由 Windows Credential Manager 交给生产 Transport；未读取、显示或记录 key，未打开正式身份、旧救援仓库或私人资料。9 个验收根均经检查只位于系统 Temp，但主机安全策略拒绝递归清理，现保留为可删除临时数据。剩余事实：无通用对话表达任务时仍可能保守 unavailable；语义相近但低字面相似的多状态回复仍可能并列，留给后续独立表达校准决定。
