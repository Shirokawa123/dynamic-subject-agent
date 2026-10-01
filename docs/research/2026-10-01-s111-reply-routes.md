# S111开工依据：事实、表达选择与披露分开

2026-10-01。用户结果与验收见[S111任务书](../slices/slice-111-grounded-reply-routes.md)。本轮只实现local-only运行路线，真实Provider调用0；S109请求预览与S110连续恢复作为起点，不再以静态JSON或人工下一轮台词证明真实连续链。

## 已有能力与缺口

源码确认`first_life_followup.life_chat_expression`在use_life=False时删除activity/plan/event，却可保留旧assistant来源；`FirstLifeCognition._chat`又以同一bool建立disclosure记录。前者决定表达是否还有判断依据，后者决定本轮披露，两种职责耦合。v4真实策略/字节已绑定，不能原地更换其字段或policy。

现有Facade、FirstLifeCognition、ModelGateway、ChatAuthorization的history/policy/identity revision、FirstLifeBudget和prepared Publication可复用；新建并行聊天store或从测试脚本拼接历史均无必要。现有local_product远程入口只接v1–v4，保留该白名单。

## 定向一手核查

| 来源 | 具体机制与适用性 | 项目取舍/验证 |
| --- | --- | --- |
| [Anthropic：Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | 上下文是有边界资源；应清楚区分背景、指令和历史，提供足以支持任务的材料；机械截短不等于正确最小化 | 保留同一已核验活动三字段供判断，仍限制两完整轮/4000字与一条share/400字，不扩大整库资料。实测字符量/调用数与错误，不假设越长越好 |
| [SillyTavern官方Context Template](https://docs.sillytavern.app/usage/prompts/context-template/) | 将人物、场景、例句与聊天历史按明确位置组织，能作为简单整体回复的成熟对照思路 | A同源整体回复；B维持选择后表达的可对照路线。不复制其代码或引入其存储；历史仍不是本项目事实权威 |
| [Chen等，EMNLP 2022：Rich Knowledge Sources Bring Complex Knowledge Conflicts](https://arxiv.org/abs/2210.13701) | 检索内容与模型先验存在冲突，矛盾对模型置信度影响有限；仅提供多个来源不能保证正确处理矛盾 | 明确当前已提交事实与旧话的地位，保留含错话的连续场景；结构检查与语义质量分开，不以合法JSON证明纠错成功。论文QA任务不等同本人物任务，不搬用其分数 |
| [S109已核对的来源监控研究](2026-10-01-s109-offline-route-evidence.md) | 说过/想过/发生过的来源归属可不同，适用于本轮旧话与事实混淆 | 作为心理学设计类比，区分当前方案、已提交事件、历史话语与新想法，不引入心理Agent，也不据此声称AI有意识 |

本轮实际搜索了上下文组织、知识冲突的一手论文及成熟角色聊天项目官方文档，打开以上前三个原页；已有多轮错误延续和来源监控结论核对仍适用。没有新第三方代码或依赖；标准库和现有Module复用，无新增许可/维护或外部数据来源成本。

## 实施决定

1. A一次返回`reply_text,language,use_life`；B规划保留原五字段，表达仍返回两字段，但其获准的current_activity/current_plan/related_event始终存在。bool仅为有限披露提议；无本请求committed event时True拒绝，False不记disclosure。A/B采用同一语义，不能因为A看到了事实就把它记为已披露。布尔通过不证明正文真的披露，语义仍待真实验收。
2. A/B有独立local-only策略版本和完整digest，沿现有identity registry保存，同ChatAuthorization快照及COMMIT guard保护。新Gateway任务/typed payload与v4隔离，旧Adapter拒绝新任务；Cognition在计次前再次核对local能力，不只依赖装配。
3. 独立local composition接受显式local ModelGateway，不创建DeepSeek transport/resolver。仅新dormant生活身份可绑定；分支固定其路线，不能切到v4远程复用实验历史，也不能把已运行用户身份改成实验。原远程打开入口遇本地策略在零调用处拒绝。重开须同策略、同digest、显式local gateway。
4. 单次A用既有expression计次，B用planning＋expression，按1/2检查余量；不新建预算schema或真实grant。所有验收只用隔离合成账本；明确合成种子的生活/share若经本地Gateway建立单独记数，之后暂停自动活动/分享，不计作未来真实试验生成成功。
5. 连续验收各自使用真正提交的本路线回复，S110明确新上下文动作作为共同控制，重启从canonical恢复；既有v4丢依据作为保留对照，不将B改进版冒称旧B。失败、撤回、坏输出和恢复同等适用。

不采用：修改v4全局policy或偷添字段、隐藏route开关、A永不记披露/B继续记、拿到事实即自动披露、直接扩长历史、引入RAG/Agent框架，以及在真实性未验收前开放用户真实分支。技术选择是本次可验证假设，真实路线优劣与数据用途批准仍待后续。

## 实施时核对

纯投影/裁决与Provider草案分为`first_life_reply_routes`和`first_life_reply_drafts`，Cognition不依赖具体Adapter。新local身份除了策略版本，还在既有activation metadata使用精确`local_reply_route`见证；缺失任一个标记均失败，旧reader也不能把本地实验读成普通远程身份。旧身份/metadata字节不增加字段，新实验才使用该变体，无SQL迁移。预算路径包含检查不是“专用账本”的充分证明；本轮实际调用者明确创建隔离合成账本，没有读写真实共享额度。

为准备准确调用合同，另按context7-mcp查DeepSeek配置：Context7 resolve返回fetch failed，web打开原页超时后，通过标准库只读GET成功获取[官方Chat Completions参数页](https://api-docs.deepseek.com/api/create-chat-completion)与[官方Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)。现有draft配置的deepseek-flash、thinking enabled、low/high、max_tokens4096及JSON object在官方文档所列范围内；JSON模式仍需提示JSON且可能截断，不证明回复结构/语义通过。这里只核文档，不发送任何项目内容或凭据，未调用模型服务、未验证账户可用性。
