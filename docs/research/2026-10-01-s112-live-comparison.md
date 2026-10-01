# S112开工证据与实现取舍

用户结果、缺口与验收见[当前切片](../slices/slice-112-live-reply-comparison.md)。本次要得到真实连续回复，S111的程序替身只证明接线成立。用户已明确批准合同中的新用途、现有DeepSeek凭据用途及42次/0重试。

复用[S111研究](2026-10-01-s111-reply-routes.md)与冻结投影，人物判断/话语来源的心理学解释仍仅作设计类比，不推导AI心理或意识。本轮只接真实执行与预算，不增加人物心理机制，因此不再扩展心理研究。

定向核验：Context7查DeepSeek失败，按skill回退核对[官方Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)及[思考模式](https://api-docs.deepseek.com/guides/thinking_mode)，deepseek-flash、thinking enabled、reasoning_effort high/low、JSON object、非流式与4096输出上限为支持参数。仓库现有DeepSeek transport/解析器已有丢弃reasoning、完整finish检查与安全错误码，可直接复用，不引入依赖或复制外部源码。请求前仍须验证真实账户返回，不把文档可用当实测通过。

仓库证据：CharacterChatBudget支持42/0初额、持久claim与链完整性；FirstLifeBudget已有阶段/每日及开发审计，四分支各需11或19次本地阶段（含程序seed），均低于原24。S111的LOCAL资格不可转远程，故增加固定的LIVE资格及activation见证，保留原LOCAL合同。复用Facade/Timeline、历史与身份fence及prepared恢复。

选用一个独立共享42真实账，四分支另用原格式作本地阶段审计。旧200账只读得到129已用/71余、开发44、schema2；不改变它或重启用户服务。未采用扩旧grant：会牵涉旧reader与用户运行，却不改善本实验。两账非跨库事务；任一步失败保守耗额、停止，不返额不重发。只有本进程刚成功claim产生的一次性票据可发送；重启不从claimed补发。

seed和live分别构造Gateway；live仅接受聊天，不接受生活/share真实请求。固定本机实验根、批准manifest与冻结材料摘要绑定用途；每次重新打开核对，不给任意路径一个新42额度。完整链包含重置与重启，保留错误语义，技术失败停受影响路线。验证预算、防重复、资格隔离与完整链后执行真实样本；评分基于完整原文而非字段合法或测试数量。
