# Slice-19：角色表达的事实依据

状态：awaiting-contract-confirmation（2026-09-05）。[诊断报告与待确认范围](../reports/2026-09-05-slice-19-diagnosis/REPORT.md)；错误已通过 ApplicationFacade 重现，尚未修改产品代码。

## 用户结果

对来源事实的回答不借有效 citation 补造细节；询问当前或离线活动时，不把角色口吻、故事起点或临时生成的想法说成已经发生的主体经历。保留明确请求的诗句等创作，不把所有表达降为拒答。

## 当前可执行范围

1. 通过既有 ApplicationFacade，用独立报告 T04、T10、T19 的输出重现错误，并加入正常改写/创作对照；只用新临时测试根和原创虚构资料。
2. 定位 Knowledge citation 裁决、capability-local reply/fallback、现有 identity expression guard 的职责；提出最小修正契约。
3. 保持六类最小投影、Provider 数据用途、credential 和状态裁决不变；不读取正式身份，不更改历史，不新增 Lifeworld/Agency/会话上下文。
4. 若有效修复需要改变当前文档要求的 reply outbound byte-equivalence，先列明范围并取得用户选择；本任务书不自行撤销上位约束。
5. 契约边界确定后再落实产品代码、行为回归、真实隔离 UI/Provider 验收与独立对抗审查。所有失败和剩余限制入报告；未实现前不升级 build 或标记完成。

## 非目标

本切片不实现用户经历的开放式润色验证（T07）、省略上下文续写（T09）、新现实观察或后台活动。语义验证不能被包装成 Python 已证明任意自然语言真实。
