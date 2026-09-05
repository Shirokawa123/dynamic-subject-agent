# Slice-19：角色表达的事实依据

状态：completed（2026-09-05）。用户明确确认两类 reply 契约及不合格基础回复回退调整；`dogfood-s19`，全量 364 passed，真实隔离浏览器 UI/进程重启及两轴审查完成。[验收报告与限制](../reports/2026-09-05-slice-19/REPORT.md)，[原始诊断](../reports/2026-09-05-slice-19-diagnosis/REPORT.md)。

## 用户结果

对来源事实的回答不借有效 citation 补造细节；询问当前或离线活动时，不把角色口吻、故事起点或临时生成的想法说成已经发生的主体经历。保留明确请求的诗句等创作，不把所有表达降为拒答。

## 当前可执行范围

1. 通过既有 ApplicationFacade，用独立报告 T04、T10、T19 的输出重现错误，并加入正常改写/创作对照；只用新临时测试根和原创虚构资料。
2. 定位 Knowledge citation 裁决、capability-local reply/fallback、现有 identity expression guard 的职责；提出最小修正契约。
3. 保持六类最小投影、Provider 数据用途、credential 和状态裁决不变；不读取正式身份，不更改历史，不新增 Lifeworld/Agency/会话上下文。
4. 已授权仅更新 Knowledge/Living Memory reply 的提示和结构化返回；原最小投影及上限不变，不新增调用。六类 proposal/classification、另外四类 reply outbound byte-equivalent；其他 required reply 失败语义不变。
5. Knowledge 事实答复从已选资料中的完整句定位，并展开所匹配条目的完整上下文；Python 验证 quote 与 title 确实来自所选条目，保留跨句否定/条件以及后续合并中的原文。正常问题继续有事实答案，但不承诺保留未经语义证明的任意改写。明确创作另行标明当前创作，不当作资料事实。
6. Living Memory reply 区分 conversation/creative/activity；模型标签不能单独证明活动真实。对明确当前/离线活动询问本地给出真实能力边界；基础回退也经过相同检查。正常聊天和明确创作需正向回归。
7. 不改变合法 state-bearing proposal、citation 裁决和原子 Publication；不合格表达使用本地安全回退，不将表达失败升级为其他能力状态失败。旧历史不重新生成。
8. 逐条先红后绿；完整最小投影和十类 outbound 字节回归；真实隔离 UI/DeepSeek/重启及独立 Standards/Spec 审查。记录第一次失败与未覆盖部分，不把有限规则宣称为任意自然语言真实性证明。

## 非目标

本切片不实现用户经历的开放式润色验证（T07）、省略上下文续写（T09）、新现实观察或后台活动。语义验证不能被包装成 Python 已证明任意自然语言真实。
