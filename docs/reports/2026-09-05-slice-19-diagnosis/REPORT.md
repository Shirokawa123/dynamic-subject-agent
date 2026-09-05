# Slice-19 诊断与契约确认

状态：诊断完成，等待用户确认实施契约；产品仍为 `5e484ac` / `dogfood-s18`，没有修改产品代码或发送新 Provider 请求。

## 已复现的真实代码路径

根据独立 UX 报告 T04/T10/T19，以 project-original 南枝背景和单份纸灯节 Knowledge 构造全新临时 fixture，通过 `ApplicationFacade.submit/wait`、实际 cognition 和 Domain/Publication 重放 Provider 提议。Provider 是受控 stub；本轮不是新的真实 DeepSeek 或 UI 体验，原真实证据仍是独立 UX 报告。

命令：`.\.venv\bin\python.exe .scratch\s19_repro.py`。最近一次运行 3.57 秒，退出码 1；7 项输出见 [repro-results.json](repro-results.json)。调试脚本保留在明确标记的 `.scratch` 中，未读取正式身份、旧仓库或 credential。

| 输入/分支 | 结果 |
| --- | --- |
| T04 纸灯节查询，有合法 citation | Knowledge accepted、1 条 citation；“桥头靠下游”“离人群远些”仍进入最终表达，来源没有这些事实。 |
| T10 当前活动 | “你来得正好，我正想歇一歇”原样进入最终表达。 |
| T19 离线活动 | “替你留了个念头”原样进入最终表达。 |
| 已被 guard 识别的当前活动句 | identity reply 过滤后，包含同句的 base reply 重新进入表达。 |
| identity reply 抛出受控失败 | 包含“我刚整理完稿件”的 base reply 直接成为表达。 |
| 对照：明确请求写诗 | 诗句保留；不能把新创作一律视为事实错误。 |
| 对照：正确知识改写 | “纸灯是放在旧桥栏杆上的”保留并有有效 citation；不要求正常改写与原文整句逐字相同。 |

首次尝试将 T04 问句缩得过短，没有提到纸灯节，候选选择未选中该条目，得到 Knowledge FailedClosed；这不是要复现的 bug。恢复报告原问句后，Knowledge accepted 且无依据细节仍通过。T10/T19 与对照复跑结果一致。

## 核验后的原因

1. `domains/experience.py::_knowledge_fragment` 检查候选身份、投影范围和 citation 重复，不接收或证明 reply_text 中每个事实。当前 accepted 的含义是“引用合法”，不是“整段回复获得来源支持”。`knowledge.py` 仍直接使用生成的自由文本。
2. `runtime_identity_reply.py::guard_runtime_identity_reply` 只接收回复字符串，删除少量第一人称时间词形；既看不到用户是否在问离线活动，也没有资料事实/创作/活动声明的区别。“我正想歇”和“替你留了个念头”绕过现有词形。
3. Living Memory 与 Knowledge 先把 base reply 保存为候选，仅在可选 identity reply 通过检查时替换；过滤为空或失败都会恢复 base。基础回复的结构验证并不代表表达事实验证，因此形成回退漏洞。

三项预测分别由有效 citation 的错误回答、两种不匹配词形、仅改变可选 reply 成功/失败的探针支持。没有推断模型真的离线活动，也没有向状态写入新经历。

## 推荐的最小契约调整（尚未授权、未实现）

- 仅调整 **Knowledge 与 Living Memory 两类现有 reply** 的提示和结构化返回契约。仍各调用原任务一次，原授权投影字段/上限和数据用途保持不变；六类 proposal/classification 请求及其状态裁决保持不变，另外四类 reply outbound 保持不变。
- Knowledge 将可核验的资料片段与非资料内容分开；Python 校验片段确实来自本次已选条目，再建立对应引用。不能仅因“模型自报有依据”就把任意改写认作已证明事实。未有依据的细节需要明确不知道；明确请求的创作不得挂成封存事实。
- Living Memory 区分当前对话中生成的建议/创作与对主体已发生活动的声称。离线问题不能用现在生成的内容冒充后台经历；不为此读取或发送历史、时间、其他 Domain 数据。
- 正常与回退表达经过相同的本地限制。可选 reply 失败或不合格不取消 proposal 和状态裁决；如果 base reply 也不合格，改为安全本地表达，而非复活被拒绝的台词。其他既有 required reply 的失败语义不变。
- 这不是统一表达 Provider、新生成阶段、事实验证模型或 Lifeworld。结构证据只能证明相应引用关系，不能声称 Python 解决了任意自然语言语义真实性；仍需对抗回归和真实隔离体验。

需要用户选择的原因：`AGENTS.md` 当前要求非闭集十二类 outbound 保持 Slice-16 byte-equivalent，且指定可选 reply 失败退回同一 proposal 的 identity-free reply。上述修正要明确放开两类 reply 的提示/返回格式及不合格 base 的回退规则；不能用下位任务书悄悄撤销这些要求。

现有限制下也能做全本地逐字摘录或继续扩词形规则；前者会损失正常改写，后者无法形成通用事实依据检查。此次先提交诊断和决策点，没有把局部替换包装成完成修复。

## 后续验收要求

确认契约后，先落正式可执行细节，再实现行为回归：有效 citation 搭配无依据文字、回退绕过、当前/离线活动、明确创作、正常知识回答、其他能力独立提交、Provider 最小投影和请求预算不扩大。随后进行真实隔离 UI/DeepSeek/重启及 Standards/Spec 对抗审查。当前未开始这些实现验收，不重新引用 332 passed 作为本切片通过证据。
