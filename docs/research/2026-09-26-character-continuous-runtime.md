# 连续聊天：从实验回复到持久人物

## 用户结果与已证实缺口

用户可以与已封存人物连续交流，关闭重开能看到同一聊天；规划和表达使用同一人格，以及当前身份最近最多2个完整成功轮、合计4000字符。历史上下文可以关闭。当前S103只完成真实身份，dormant会在Admission前拒绝；S101两阶段是固定实验，保存prompt JSON且依赖实验计划，不能当生产聊天直接复用。

可观察验收：第一轮无历史，下一轮精确取前一完整已提交轮；重启后相同、跨身份隔离、关闭后不外发，超限不截半轮。两阶段最多2次，规划失败不执行表达；Provider输出不改变知识/人格/生活。失败与重试幂等经已有Runtime提交语义处理；界面记录只读canonical Timeline。

## 定向资料核对（2026-09-26）

- [LangChain官方短期记忆文档源码](https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/short-term-memory.mdx)：按thread隔离持久state，并在调用前裁剪上下文。借用“持久历史与本次有限投影分开”的机制。本仓已有Timeline原子提交、完整性链、最近轮投影，不新增LangGraph checkpointer，避免第二权威和迁移成本；不采用文档的删除/摘要代替已授权原文窗口。
- [Pal与Traum，SIGDIAL 2025](https://aclanthology.org/2025.sigdial-1.31/)研究复杂人物对话中的personality grounding与relevance。适用问题是材料要影响回复而不只是封存；本次复用已实测S98/S101常驻core＋有边界解释＋当前相关资料，不添加新人格模型或认为论文证明本角色还原成功。效果看接续、不重复问已答信息、意见有自身依据，以及反例是否虚构经历。
- [Clark与Brennan《Grounding in Communication》作者原文](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf)：本次重读presentation/acceptance、修复误解与理解证据。心理学解释力在于“说过”和“被理解/相信”应区分。设计类比是历史原话帮助理解当前指代，但不直接写成人物相信的新事实、亲密度或生活经历；2轮足够改善接话是待验证产品假设，不是理论给出的窗口值，也不是机器有心理的证明。

已有S98人格和S101实测研究继续适用；新检索补的是持久上下文进入正式运行的缺口。当前公开源码是机制比较，不依赖其API语法；没有安装/复制外部依赖或模型，故无新增许可证或远程数据边界。新增实现仍需本地恢复与投影行为验证。

## 仓库复用与决定

复用ApplicationFacade.submit、Host单写者、Runtime Admission/Publication、canonical ConversationTurn，以及已有通信规划/表达Python裁决。正式输入从S103的已验证封存资产构造，不读EPUB或未封存sidecar。人格是author-interpretation，不写Knowledge或模型状态；前景只依据已有committed对话存在，不解释时间差或关系。

采用新准确聊天manifest、policy decision、后继QRI和binding。保留原dormant QRI及封存资产；在首次事件前通过已有Host切换机制沿用Timeline。同步校验registry与恢复，不直接改dormant实例的Provider。激活失败应可重放，不得留下可跨资格打开的半态。

只复用两阶段的纯投影/裁决和已有DeepSeek transport/gateway；不复用试验runner的prompt落盘/用例一次性状态。真实原文只进canonical Timeline，调用账本仅阶段、指纹、计数和状态。使用已批准deepseek-flash、规划low/表达high、4096 tokens/30秒，无自动重试；费用受现有200次总额度约束，未知送达计次，不能因重启重置。

未采用全量历史、自动摘要、长期记忆模型、独立关系Agent、自由生活生成、旧六Domain拼接器：它们不能解决本次最小闭环，或超出批准用途。生活/主动消息仍待独立决定。数据控制开关影响出站用途，不承诺物理删除；本片不迁移旧身份。
