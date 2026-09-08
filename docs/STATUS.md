# 当前状态

- 2026-08-30：新产品仓库从救援仓库提交 `5b94eb5` 完成抽取，旧仓库与私人数据未修改。
- Memory、Knowledge、Relationship、目标承诺、Situated、Medium、Windows UI 和持久身份已迁入。
- 参与者目标/承诺、Situated State 与 Medium State 均完成真实 DeepSeek、Windows UI、持久化和重启验收，状态为 STABLE。
- ModelGateway、ProviderAdapter 能力声明、provider/account credential slot 与 noop-null canonicalizer 已完成；明确目标查询/变化为 Python 路径。
- 已验收 build 为 `dogfood-s29`：旧记忆候选先本地 FTS5/BM25 排序再按原 20 条预算截断；540 passed、39 次真实后台追加及重启见 [报告](reports/2026-09-09-slice-29/REPORT.md)。head89 已召回后表达不稳定、head94 遗忘后误说尚未安排仍待修复；无共同词元/纯指代/窗口内错选及关系历史故障仍有限。当前无执行切片。
