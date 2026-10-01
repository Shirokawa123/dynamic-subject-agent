# S119开工：已确认的新文字用途

用户结果与可观察验收见[唯一任务书](../slices/slice-119-approved-free-input-chat.md)。本次明确“同意”承接S118已具体展示的自由文字/本身份最近两完整轮范围，不复用旧固定句授权digest，也不为已确认次数再设置门禁。

2026-10-02针对新增自由输入再次打开[Streamlit官方chat_input](https://docs.streamlit.io/develop/api-reference/chat/st.chat_input)，核对明确提交、文字长度、处理中禁用和默认无附件的交互机制；只借机制，复用本仓HTTP/草稿nonce/Facade接口，不引入Streamlit或其session聊天store。所有聊天仍从canonical Timeline选取，不允许UI提供历史数组；新server不暴露附件/生活/文件effect route。没有第三方代码或依赖，许可与维护无新变化，实际代码不依赖Streamlit API行为。

复用S118及S117的`TrialConversationAdapter`、生命周期回调、guard、完整两轮/4000与S1/400来源验证、strict JSON/echo拒绝、无限审计及一次性票据。缺口是这些接缝当前exact类型/策略绑定S117白名单；本次新增FreeInputReplyTrial和独立策略/用途见证，保持旧reader和旧字节，不原地删白名单。新输入的观察器仅留目的/摘要/用量等metadata，不在实验观察列表另存私人prompt或正文；成功内容仅canonical。

心理学对授权/HTTP本身不适用；人物表现仍使用S118已逐输入核对的来源监控/grounding验收。定向复核[Anthropic上下文工程经验](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)仍强调围绕任务组织材料与减少不必要上下文；作为工程经验使用，不据此证明两轮足够或自我事实候选有效。S118两段替换候选先保持为独立假设，若实测则同材料/参数/schema对照，不能把习惯定义补写为真。

新用途仅普通当前文字<=1000，以及history开启时当前身份完整最近<=2轮/<=4000，原合成人物、固定活动/event/S1边界保持。新的活跃frame核授权、用途/root/slot和typed投影，ModelGateway前再检查当前消息和来源界限；旧S117构图/用户句契约保持，新B/生活/其它purpose不能由新free入口发送。仅用新本机服务/根，保留8780及旧用户服务，避免停止旧进程。

未采用：仅放宽旧白名单、让UI提交历史、env/file持久化key、重新分配旧有限账、自动重试、绕过上次进程停止审核拒绝。验收以后台HTTP实际Facade新消息/双击/关闭历史/reset/冷恢复/失败原文及必要UI检查为准，合成与真实分别报告；范围外输入在Admission前拒绝，私聊证据不自动导出到仓库。

独立复核的实际反例改变审计装配选择：已运行S118进程的旧PURPOSES不识别free-input-character-chat，若同库加入新purpose，旧reader会将其判作integrity failure。故新用途另用`free-input-audit`（仍limit=None、目录外初始化见证），旧开发审计不写入新purpose、不重置或迁移。统计分别记录旧累计与本用途实际次数，不把新库说成新额度；该metadata库不是第二canonical聊天store。sender固定路径随typed新用途核验。
