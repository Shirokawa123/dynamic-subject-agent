# S150 新用途集中审阅：自然反馈准确修订

用户要求的LOCAL闭环已实现，实际已审人物包已用Facade完成；工程证据及首失败见[报告](../../reports/2026-10-11-slice-150/REPORT.md)。这份审阅只请求以下两项新Provider用途，准确机器合同/策略哈希见[review.json](review.json)。准备和纯wire不表示获批或真实人物通过。

| 用途 | 触发与精确数据 | 返回与Python裁决 |
| --- | --- | --- |
| natural-activity-feedback | 用户普通提交消息一次：current≤1000；可关闭最多2完整轮合计≤4000；已批准Sagiri30事实/4解释既有最小background；单有效E1≤400可选；唯一有效current_plan `{subject≤160,composition≤800,focus≤400}`可选；activity_revision一个整数；最近有效反馈F1逐字原话≤400可选。无ID/日期/旧before/diff/decision_note/隐藏推理/其他内部状态 | 一次JSON `{intent:chat/clarify/revise,activity_revision,edits,reason_code,reply_text≤1200,language:zh}`。chat/clarify typed NoOp不修改活动；revise最多4项field/before≤160/after≤240，Python核当前有效plan、精确basis/版本/权限、唯一匹配/不重叠/实际变化、边界和剩余文字原样后原子发表。只有明确修订的完整当前原话≤400可成为反馈来源。 |
| shared-activity-choice新投影 | 本次首先只手动明确推进：沿已批最小background、单有效E1、phase/allowed_actions、有效current_plan，增加最近有效反馈F1≤400。无当前聊天或近期窗 | 沿原choice JSON与动作合同；Python实际裁决和来源闭包。新取舍可不采纳/暂缓，失败0retry，不放宽rework/null约束。 |

同DeepSeek HTTPS endpoint/现Windows default slot，key仅原HTTPS Bearer鉴权，正文仅最终content；协议thinking-high/JSON object、max_tokens4096、timeout30、每用户消息/推进最多1请求、0自动重试。工程/诊断开发次数沿现授权，无新循环或用途；真实首景固定≤10次、第一技术失败停止、全部首次原文只在本机保存，无raw reasoning/key。

使用独立新LIVE资格/分支和审计，不把LOCAL资格或旧schema/root自动转换；当前LOCAL只有拒绝远程的Pending Adapter，准确body与LOCAL输入同源。获批后还须实施精确LIVE claim/consume/final publication再验，不声称现在已有LIVE sender。当前保留最多8条反馈来源闭包，出站只最近F1；上限是本轮可观察范围，不是长期人物产品限制。

不新增人物资料、Provider/credential slot、后台活动/通知、系统服务、8796持续入口、云、迁移删除、永久偏好写入、自动人格重写或Reflection；不操作8793/8795或用户草稿。一次真实隔日未请求，本次先证退出近期窗口后的实际活动选择。

需要确认的原因是[AGENTS.md](../../../AGENTS.md)“删除、不可逆数据迁移、新 credential 用途、新 Provider 数据用途必须先获用户批准”；旧reply只有自然正文，旧choice没有本次反馈，本次新增反馈裁决和F1投影不能由旧技术调整批准代替。你此前已批准自主实现，此处只集中确认这两项新用途。
