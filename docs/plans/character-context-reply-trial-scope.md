# 新人物上下文回复：真实验收范围草案

2026-09-26接续：S78已实现组织人物输入，下一次真实用途以[Slice-79精确对照方案](character-context-comparison-trial.md)为准。下面S73平铺草案留作历史，不作为新的调用授权。

2026-09-24，Slice-73。本文只列可审数据和下一实现约束，尚未请求批准或执行。现有新Lab只支持local替身，没有真实Adapter。旧试聊和原文提取的授权不自动覆盖本草案。

## 已准备的确切内容

本地`.local_indexes/eromanga-sensei/s73/exact-reply-request-preview.json`由实际CLI生成；projection包含：self_knowledge、stage_description、encounter、disclosure、current_message、policy六项。样本projection共5739字符（JSON紧凑序列化），30项适用知识，指纹62dec47353e0b9b5b37fe6dec0303011a6562c51c7fa8ec2faff021c9b48b28e。可读版本为同目录`回复候选请求预览.md`。

新增知识不是小说原文，是经过阶段审核的本人背景摘要及其维度/事实或信念/直接或关联推断/相对时间标签；包含职业身份作品、家庭与学画经历、具体专业局限、创作取舍和线上活动。阶段说明与相识动机/时间为已列明的分支提案，不能冒充用户逐字确认或原作既有事件。

无出处、文件路径、证据或实体ID、作者审查解释、未来排除项、正式身份历史、此前自由试聊、共同聊天历史或credential。当前消息最多1000字符；没有历史字段。此片知识本地上限20,000字符不是拟外发任意资料的许可，首次真实范围应固定到具体v8快照。

## 下一步实施与批准点

拟目的地沿用DeepSeek HTTPS chat/completions、deepseek/default槽，任务用途为character-context-reply。正式模型名、采样/输出token、固定验收消息与轮次停止规则需在真实Adapter离线验收时一起固定；不能先填旧计划digest就放行新投影。

单次返回只能是reply_text/language；候选可供内容审核，不改变身份/关系/记忆。验收要看跨领域本人认识、错误前提、隐私保留、开放邀请与初识缘由，不以JSON成功或禁词消失代替人物体验。

第一次真实验收先用新隔离实验，不追溯导入旧聊天。若需要连续两轮，需要另把历史来源与撤回契约实做并纳入具体外发范围；不能让当前无历史单轮入口假装已能接续。准备完真实Adapter及精确消息后再集中请求新数据用途批准，目前不向用户重复索要试聊或模糊许可。
