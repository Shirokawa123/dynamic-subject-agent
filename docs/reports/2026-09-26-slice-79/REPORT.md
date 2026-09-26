# Slice-79：真实对照准备与新用途决策点

2026-09-26，基线`4960550`。在连续MVP授权下完成P1真实效果验证所需的离线门槛；**没有运行真实Provider请求，MVP尚未完成**。

## 交付

新增冻结计划、受控实验Producer和专用DeepSeek Adapter；经现有ApplicationFacade预览/候选入口和local_product装配，CLI默认prepare。原local-only Lab、旧Provider投影、正式身份和Timeline保持。

计划固定12条未用于S78检索调参的新消息，各flat/organized一次。两路共用TRIAL_POLICY、现有模型请求名、相同参数与20,000知识字符上限；完整24份projection及出站字节摘要均可本地查看。模型请求保持deepseek-v4-flash，官方已说明实际由V4.1-Flash服务；新用途方案对此明示，不比较为同一旧模型快照。

真实执行必须显式批准当前plan digest，装配前重新生成所有请求核对。plan目录独占启动，发送前记录attempt；重复请求读原结果，失败停止，重启不给新Gateway，不重发缺失结果。凭据后端不可用保留typed unavailable；网络/无效输出与unknown分别表达。审计不写key/header/reasoning/rawresponse，不成为正式角色记忆或第二canonical store。

## 实际本地准备

实际CLI已生成plan：`070f7b7afec6e4302adce3e91789c3bc4da23fb4f1442755f51f5f54fd3dbdd5`。24项投影2331–5937字符，出站body7124–12082字节、合计234767字节，逐项body digest重算和共同policy核对通过。计划文件109329字符，包含审阅用本地元数据，不是每次发送这么多。

草稿指纹仍为`273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94`，新消息文件`76b997e1cd08dac380c53dfe5ace5b6aa5b338c423e1bb3e094859e9beb3ced2`。检查实际启动目录不存在；本轮仅prepare。完整计划在`.artifacts/character-context-trials/`，可读预览与frozen-plan-checks在`.local_indexes/eromanga-sensei/s79/`，均不入Git。

## 验证

实施期间检查并修复了两处失败语义：来源坏后修复也不能继续同一批准批次；credential unavailable不能统一包装为failed-closed。测试以合成来源和Fake Transport覆盖完整24路、精确字节、默认零调用、批准不符、额外消息/顺序、重复/重启、错误输出和来源失败。六个相关文件141项通过（124.54秒）；随后增加完整出站65536字节的准备阶段拒绝，最终新实验专项23项通过（61.48秒）。没有为小增量重复整套回归。

新上下文Sol high聚焦复核未发现可复现阻断；合成核对出站字节边界、缓存空candidate/额外字段/错指纹/状态组合均不伪报成功，合法unavailable可重放。并发独占由代码机制核查，没有另做真实多进程并发试验。主助手复查实际计划字节、共同policy与默认CLI，最终计划指纹未变化、启动目录仍不存在；diff与本地文档链接/围栏检查完成后提交。

研究按context7-mcp尝试当前文档检索失败后回到DeepSeek官方资料；复用既有Transport完整响应检查，不增依赖。心理/角色表达依据复用S78研究，未用工程测试代替人物内容验收。

## 停止点

下一步将完整已审核人物摘要用于`character-context-reply`，比此前试聊范围扩大，依AGENTS新Provider数据用途必须先批准。已做好[具体24次方案](../../plans/character-context-comparison-trial.md)及可读精确输入，等待用户决定后才运行。不要求用户再次确认已定产品目标，不默认追加历史、后台、通知或无限调试额度。
