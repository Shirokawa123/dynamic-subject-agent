# S101：闭集规划的思考量与4096预算适配

用户结果：同一六题对照能完成，并减少用于选择action/最多4个引用的无效消耗。S100基线第4题真实出现HTTP200、completion_tokens=4096、response-truncated；未形成可用规划，已按契约停止。人格条件尚未开始。源输入、语义policy和额度不扩大。

## 已取得证据

实际命令`.venv/bin/python.exe .local_indexes/eromanga-sensei/s100/run_comparison.py`已运行一次；第7次尝试为demand-agreement规划，22.651秒、prompt1273/completion4096、HTTP200，Facade返回FailedClosed/response-truncated。代码只有finish_reason=length产生该诊断。旧计划停止且不重发。没有保存reasoning或原响应，不能断言全部4096都是思考、服务为何在此题耗尽、或重试必然成功。

Context7 resolve DeepSeek API返回fetch failed，依context7技能转用官方资料。[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)明确reasoning_effort的low/high/max及medium/xhigh映射high；length可能发生于输出预算/上下文上限，JSON模式仍需明确要求JSON。已核当前PLAN_POLICY含明确JSON格式要求，因此不能将此次归因为缺少JSON指令。[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)官方检索正文一致；直接打开一度失败，结论由已打开的API参考交叉核对。

仓库现有protocol将规划固定high4096，表达已有standard/thinking-high变体，实验绑定wire/plan摘要且故障停。S95/S96已见表达high的部分收益，故本次不同时改变表达。S99冻结/恢复机制仍适用；复用已有transport、诊断与账本，不加入重试框架或SDK。

## 取舍与验证假设

新增显式planning_effort=low，默认仍high且原计划/字节保持。只降低选择action/fact_refs阶段的思考档，不提高4096上限，不动知识、人格、两段policy、表达high、30秒、JSON或失败语义。这是降低触顶风险/成本的工作假设，不保证模型一定更快或正确。medium并非降低，不能用它冒充对照。

未采用：将上限增到8192或更大（超出现有单次预算且更贵）、全流程关闭思考（同时丢掉表达已有收益）、旧计划原样盲重试（违背停止契约）、手工替模型预选拒绝动作（会把本次问题硬编码掉）。

先以Fake transport检查只有planner wire的reasoning_effort变化、两条件都绑定新配置、旧high计划可重建、表达wire与恢复/拒错不变。然后重新冻结同一六题的两个low规划/high表达计划，最多24次；全局200额度已授权同材料/用途常规配置验证，当前余163，不逐批询问。旧S100的三条及截断保留，不混成新的成功样本。

新真实观察：第4题能否在预算内给出合法规划、全六题是否完成、actual usage和延迟、选材是否退步；任一故障再次停止整个新计划，不循环降低/提高配置。人格效果仍须同配置的两条件比较，技术修复不替代内容验收。

此为工程资源分配，心理学不解释这次服务截断；S98人格研究仍仅支持输入内容。没有引入外部代码或依赖，无新增许可证/维护负担，无新Provider/凭据/历史用途。
