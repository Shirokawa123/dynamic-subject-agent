# Slice-73：人物上下文到回复候选

基线e6973e1。本片将明确人物上下文接成单独的回复候选请求和离线执行路径，不再只有资料预览。未调用真实Provider或改变实际聊天。

## 实现

Facade新增preview_character_reply/propose_character_reply。前者返回精确projection及确定性digest，不执行模型；后者要求显式装配CharacterReplyLab，默认unavailable。Lab仅接受local=true的typed ModelGateway，通过独立ModelTaskKind.CHARACTER_CONTEXT_REPLY执行，旧角色回复与证据提取Adapter不接受此新任务。

所有来源仍每次经既有Facade人物模型核验；subject/anchor/消息沿S71/72验证，来源损坏时不调用Gateway。六个白名单字段为本人适用知识、明确阶段、分支情境、披露规则、当前消息和固定任务规则。CLI --reply-request只预览，不执行。无历史字段，未将作者View整体转发。

Gateway返回值只接受exact reply_text/language，非空且<=1200字符、language=zh；格式错误、额外状态字段、异常或任务类型错配均failed-closed，不自动重试，不回显异常细节。成功只返回candidate/semantic_review=required/persisted=false；没有Timeline或Memory写入。语言标签检查不证明正文实际中文，更不证明角色语义正确。

复用既有Gateway、production composition和[S70上下文组织研究](../../research/2026-09-24-coherent-character-context.md)，不引入依赖。小模块只做白名单投影与候选输出检查，不新增人物状态存储；旧路径行为不变。

## 验证与真实限度

77项相关测试通过（48.75秒）：人物模型、Facade、local_product、旧角色聊天及Gateway。覆盖离线替身同一装配路径、请求字段与digest、错误输出/附加状态、异常/错配、来源失效不调用、默认缺失、关闭及remote声明拒绝。替身返回只是工程测试文本，不作为人物样例或质量证明。

两位助手分别复核规格与接线，未发现阻断问题；确认RLock嵌套与关闭串行、旧Adapter不会误接新任务。未声称独立真人审查或外部模型验收。

实际v8资料经CLI生成请求，30项知识仍完整；样本紧凑JSON为5739字符。请求指纹62dec47353e0b9b5b37fe6dec0303011a6562c51c7fa8ec2faff021c9b48b28e。产物仅本地`.local_indexes/eromanga-sensei/s73/exact-reply-request-preview.json`及`回复候选请求预览.md`；未发送原文、出处、正式身份历史或凭据。

## 后续

新Lab是无缓存的单次本地候选实验，不是幂等远程会话；重复显式请求会再次执行本地Adapter，只有内部自动重试为0。无共同历史、持久接续或真实Provider路由。下一片应完成真实Adapter的离线契约、固定验收消息/停止条件和新投影批准入口，再集中请求真实调用范围，详见[范围草案](../../plans/character-context-reply-trial-scope.md)。当前不需要用户工程试聊。
