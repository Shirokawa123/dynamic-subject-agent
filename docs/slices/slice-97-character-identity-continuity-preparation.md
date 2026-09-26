# Slice-97：独立角色定义与连续聊天的可审准备

2026-09-26，基线e733697。远程调用0，200额度剩170。依[开工证据](../research/2026-09-26-character-continuity-source.md)推进，当前只读准备，不保存实际Source Draft、不freeze/切换身份、不录入真实聊天或发送历史。

## 用户结果

用户可以看到“将创建谁、起点是什么、哪些知识会成为固定初始定义、哪些未知不会当事实”，并对真实连续聊天的数据用途作一次具体决定。已有单轮台词仍有边界风险，不以正式身份封存将其追认成原作事实。

## 实现范围

- 在现有ApplicationFacade下增加小型只读身份准备Interface；读取经过现有CharacterEvidenceModel验证的主体/起点，复用SourceFreezeMapping算法，不另立身份Authority或第二canonical store。
- 确定性导出一份明确标注“v9派生整理，非小说原文”的source document、候选清单及本地追溯信息。所有eligible知识原陈述、类型/成立/知情范围完整保留，分组/分段不能删限定；belief不得无标记变事实。excluded/待核只作本地说明，不入拟封存Knowledge或Profile。
- 名称来自当前subject对应entity，不凭预训练补职业/年龄。身份内容取已有identity知识且保留限定；起点说明来自已审核stage。不要把“来自某部小说”塞进人物自我认识，使其预知自己是作品角色。不要把产品短消息要求当永久人格/原作voice。
- 适配现有SourceDraft最大16候选、Knowledge内容1000/quote500、source16000等边界，需分段时按完整条目分，超限就明确拒绝，不截断或丢事实。evidence_quote引用派生文档本身，不能伪称直接原作引文。
- 准备对象仅复用拟revision1的内容mapping；必须明确draft_saved=false/identity_created=false。核查发现旧Authority/Policy仅支持project-original，小说派生资料不能走旧通道：save/freeze请求为None，execution_ready=false、blocker=original-only-freezer、content_mapping_only=true。来源声明、受限自持运行资产及其摘要绑定独立definition basis，确认请求保持false，不冒充旧freeze批准。本片不改Authority/Studio来源权限。
- CLI默认只预览或显式输出可读文件，不提供执行freeze/选择身份开关。真实v9预览文件只放Git忽略目录；公开报告不复制完整人物资料。

## 行为检查

通过Facade验证覆盖/类型/限定、排除项不泄露到拟知识、名称及Source引用一致、来源/起点变化的hash/拒绝、不符合上限失败关闭；预览重复/重启稳定，不改变SourceDraft/identity registry/Timeline且Provider0。可复用synthetic fixture，不为测试实际封存v9。

## 具体决策准备

主窗口提供可审定义、准确派生来源声明和后续连续聊天方案：用户确认后先实现并验证来源准确的Authority路径，核对同一definition basis，才创建新identity并进入它（不改旧身份）。聊天原文走原Timeline；拟允许当前消息＋最多2完整已提交轮/合计4000字符供规划/表达接续，不发完整日志/其他身份/时间戳，不把对话当事实权威。权限必须可关闭，新生活推进、主动联系、人格重写和删除迁移不包含。

本片不声称生产接续已经实现。新的身份和历史用途尚未获准，先做到具体可审，再停在用户决策处。

状态：准备完成，19项唯一检查通过、真实v9只读导出成功，0远程调用。见[报告](../reports/2026-09-26-slice-97/REPORT.md)；停在[具体定义与新数据用途确认](../plans/character-continuity-consent.md)。
