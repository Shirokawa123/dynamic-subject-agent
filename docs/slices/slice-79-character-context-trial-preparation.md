# Slice-79：组织人物上下文真实对照的离线准备

2026-09-26，基线`4960550`。按连续MVP授权推进；本片停止点是具体新数据用途的用户批准。

## 用户结果与缺口

能核实P1组织后是否改善人物回答，而不把较短输入或测试通过当人物效果。Slice-78已有实际组织投影和local-only候选，尚无此投影的远程Adapter/一次性验收门槛；S73草案明确旧试聊和提取额度不覆盖完整背景摘要。

## 研究与复用决定

研究依据复用S78的TimeChara/ReverieMem评估限制：固定未用于选择调参的消息，比较完整策略，分别核对事实/知情/披露/自然度。为减少混杂，本次flat/organized使用同一实验policy、模型、生成参数及资料字符上限；两种知识表示内容不同，结果只能说明本批策略效果，不直接证明长期语义能力。

Context7检索DeepSeek失败后，已于2026-09-26打开[官方首次调用](https://api-docs.deepseek.com/guides/harness)和[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。旧deepseek-v4-flash名仍可用但由V4.1-Flash提供服务；thinking disabled、json_object和max_tokens为当前支持参数，JSON模式仍需明确格式指令且可能截断。保持项目现有请求模型名、endpoint与Transport，不改旧Provider字节契约；在用户方案明确实际服务已重定向。

本片主要是实验权限与执行控制工程，心理学不额外决定实现；角色内容检查沿既有研究。复用ModelGateway、既有DeepSeek Transport/安全凭据Resolver和Facade，不加依赖、框架或第二人物事实库。

## 实施范围与契约

- 准备一份冻结计划：新v9草稿指纹、12条固定消息×flat/organized两路共24个精确请求、统一实验policy、endpoint/model、知识预算、生成参数和保留策略；精确请求可本地查看并有plan digest。
- 新实验Producer经原Facade.propose_character_reply进入Gateway；保留原CharacterReplyLab拒remote行为，普通产品默认不启用。装配只在local_product；桌面CLI不自行读凭据或拼Provider。
- 远程Adapter只处理CHARACTER_CONTEXT_REPLY与此计划允许的精确projection。目的地沿用DeepSeek，max_tokens=600、temperature=0.3、thinking disabled、json_object、stream=false，reply_text/language、zh、<=1200字符。
- 默认prepare/检查仅本地；真实执行必须显式提供当前计划digest并匹配当前草稿/所有请求。参数只是操作人声明，不能替代用户批准。
- 一次性实验记录在独立Git忽略运行目录，发送前先保留本次计划已启动记录；同计划重启不能静默重跑。每项至多一次尝试，无自动重试；缺数据/credential/网络/输出故障立即停止，预算不能因失败补回。
- 同一输入重放缓存已得结果，不重复发送；崩溃后的未决结果显示unknown/已用，不自动重发。记录只包含计划/请求标识、脱敏状态与获准回复，不保存key、header、reasoning或raw transport响应。
- 试验不包含用户私人聊天历史、原文、来源路径/ID/未来排除项；无长期记忆、关系更新、生活或通知。没有第二canonical聊天store，因为此实验不形成正式运行状态。

## 验收

Fake Transport经同一装配和Facade检查完整24路、精确字节、默认0调用/0凭据、digest或草稿不符0调用、额外消息被拒、一次性重启、重复请求、故障停止及泄漏边界。实际v9生成计划并纯本地核验；用户可批准前已能看精确范围，不先调用再报告。

## 分工

原Sol实施者独占新增trial/Adapter、现有composition与必要Facade类型、CLI和tests；主助手负责本地消息/计划产物、用户批准方案和docs。独立Sol做必要聚焦复核。源码之外发现记报告，不扩大执行。

状态：离线准备已收口；141项相关回归、增量后23项专项及独立复核通过，实际24项精确计划已生成且未启动，真实调用0。见[报告](../reports/2026-09-26-slice-79/REPORT.md)与[待批准用途](../plans/character-context-comparison-trial.md)。
