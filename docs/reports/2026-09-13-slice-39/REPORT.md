# Slice-39：自然目标操作

状态：实施验收中。基线b981478 / dogfood-s38，来源为独立验收第6/7轮。

## 调研与复用

2026-09-13查阅 [Rasa Command Generator](https://rasa.com/docs/pro/customize/command-generator/) 与 [LLM Command Generators](https://rasa.com/docs/reference/config/components/llm-command-generators/)，借鉴把自然表达绑定为明确动作和参数、纠正时定位字段的机制；对照 [LangChain结构化输出类型](https://reference.langchain.com/python/langchain/agents/structured_output)，本仓库已有ModelGateway、typed candidate和输出验证，故直接复用，不引入第二套Agent/依赖或复制源码。偏好澄清的跨轮权限不泛化给目标，本轮仍仅使用当前完整消息与已有目标状态。

## 诊断和实现

原样“周六我准备请两个朋友来吃早餐；我也给自己定个目标：在周五前把菜单想清楚。”在Interface得到Goal rejected，1 failed in 0.97s。原创建前缀在路由、冲突检查与Domain各有表达差异；命名修改没有结构化对象；整句被Memory接收会覆盖安排。

统一自述目标前缀，支持“我也给自己定个/一个目标”；named_goal_changes解析“〔名称〕这个/这项目标我想/希望改成/改为/换成〔内容〕”，输出名称、内容、逐字证据及原消息跨度。名称在当前活跃目标条款或该目标当前修改证据中显式名称里匹配，必须全库存唯一；不是任意语义别名或永久名字库。模型挑选的引用子串不能冒充当前修改指令。

允许逗号后仅附明确“〔安排/计划〕不变”说明，新目标只取修改内容，Memory将整个操作及不变说明视为无新记忆依据。其他混合变化/条件不能被截掉，明确拒绝后要求分开说明。引用/假设/他人目标/多操作/撤回仍受完整消息检查。

本地目标库存读最多100条active，达到上限不能证明完整，拒绝状态变化；Provider继续只接收原20条窗口，字段/提示/调用预算不变。完整库存同供路由、预检查与最终Domain，目标引用索引在同一有序库存中对应；不额外外发证据或历史，不清洗旧记录。

## 验证进度

原两轮修复后1 passed in 1.27s。初期相关26 passed in 29.32s，扩大相关53 passed in 46.45s，含目标/记忆分工、旧目标语法与时间/Provider基线63 passed in 51.22s。最新自然专项13项通过，覆盖其他题材与动作、同名/未知/引用/条件/撤回，以及模型窗口遗漏但完整本地库存存在的对照。最终全量、独立复核和真实结果待回填。
