# Slice-04：六项既有能力同轮整合

状态：done（2026-08-31）。规模预算：≤ 2 个工作会话。

## 用户可见结果

同一条消息可在一个原子 TimelineOutcome 中同时使用或更新 Living Memory、Knowledge、Relationship、参与者目标/承诺、Situated State 与 Medium State；任一 Provider 子能力失败只显示该能力的 FailedClosed，其他无依赖能力仍可裁决、提交和回复。

## 权威宿主

- `ApplicationFacade` 是唯一产品与行为测试 Interface。
- `ControlledCompositeCognition` 只组合六个深 Module 的候选、失败和表达，不拥有状态或写权。
- 四个 Domain 独立裁决，`SubjectRuntime` 保持唯一写入者，`TimelineEngine` 原子 Publication。

## Provider 数据边界

沿用 `AGENTS.md` 已授权的六类最小投影；每个 Adapter 单独构造请求，组合层不得合并、复制或旁路投影。该切片不新增任何 Provider 数据用途，不改变 credential 用途。

## 实现范围

1. 经 Facade 行为测试证明六项能力可在同轮并存，Outcome 与 UI 投影逐项可见，表达去除互相矛盾的“无相关信息”子句。
2. Living Memory、Knowledge、Relationship 增加与目标/Situated/Medium 等价的 typed FailedClosed 片段；单项失败不携带候选、不写该项状态、不终止其他无依赖能力。
3. 组合层只处理候选/失败合并和表达优先级；Domain 保留所有状态变化裁决，模型回复不得决定持久状态。
4. 覆盖同轮六能力、每类失败隔离、原子 Publication、幂等、关闭重开与最小投影不串线。
5. 全量回归、对抗性复核、commit；网络可用时 push 当前及本切片提交。

## 范围外

- 新知识源、新记忆/关系/目标/状态语义或新 Provider 数据用途。
- Agency、effect、人格发展、Reflection、主动消息、提醒或后台行为。
- guard、mutation、证据 JSON、治理状态机或新测试框架类别。
- 旧仓库、私人数据或正式身份的读取、迁移、删除与修改。

## 验收

- 一个 Facade 操作产生一个原子 Outcome，六项状态/决策均可复核；重放与重启不重复写入。
- 任一子能力 Provider 故障时，该项为 FailedClosed，其他可用能力仍为 accepted/rejected/no-update 并正常表达。
- 六类请求分别满足现有字段上限和禁止字段约束，无跨能力投影。
- 全量测试绿；任务书记录验收事实；独立 commit 并 push。

## 收口证据

- Facade 同轮测试以一个 head 同时验收 Memory accepted、Knowledge accepted、Relationship accepted、目标 create accepted、Situated gentle accepted、Medium evidence rejected/settled；表达包含各项有依据内容且无互相矛盾的缺失声明。
- 相同 command + idempotency key 不增写；关闭重开后 Memory、Relationship、目标、Situated、Medium 均从 canonical Timeline 恢复。
- 六类任务全部经 ModelGateway；六类单项故障逐一验证为局部 FailedClosed，其他能力仍可提交与回复；桌面投影显示旧三类 failure 状态。
- 对抗复核修复了多分句目标吞并和关系声称误删无关目标候选；全量 `223 passed`。
