# S151：截断层定位与最小干预开工证据

用户结果/标准/结束条件见[S151](../slices/slice-151-output-budget-new-continuity.md)。S150成功3请求后第4原final已是空字符串，HTTP200/4096，生产parser仅在finish_reason=length分支发response-truncated；空发生在本地正文JSON解码/Publication之前。原HTTP envelope未保存，原reasoning用量未单独记录，不声称知道内部原因。

Context7实际可用：resolve DeepSeek API→`/websites/api-docs_deepseek`，查询当前chat completions/thinking/JSON/usage，并官方网页核对。初次不带末尾斜杠页面超时，后带斜杠/中文原页成功，不能据资料超时推断产品网络。

| 一手资料 | 本次具体机制与限度 |
| --- | --- |
| [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) | finish length表示请求输出上限到达；usage可含completion_tokens_details.reasoning_tokens。thinking disabled受支持，reasoning_effort控制强度。JSON仍需提示约束；客户端不应把length当成功。 |
| [Thinking Mode](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/) | reasoning与final是不同输出，思考发生在最终回答前；无tools请求不需回传reasoning。本项目继续只保存最终正文和使用量标量。 |
| [Models](https://api-docs.deepseek.com/quick_start/pricing/) | 当前deepseek-flash支持两模式、1M上下文；原prompt2697远低于上下文。模型名/endpoint不换，当前技术无需新库。 |
| [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) | 合理max_tokens防截断，且承认可能空content；当前已有JSON指令，不能把所有空白归因格式缺例，S115旧stop/低tokens与本次length/耗满不同。 |

假设排名已向用户说明：H1思考阶段耗满4K（新预览同消息关闭thinking会消除reasoning开销，非空完整输出留出预算）；H2final JSON本身太长（关闭thinking仍接近4K/截断）；H3本地丢正文（捕获非空而parser/Publication丢失）。S150捕获原字段空及length降低H3可信度，但对上游内部原因仍是推断。固定4格新消息比较，不对旧失败输入重抽。

选择独立direct-final同用途技术候选：只feedback关闭thinking/移除effort、max_tokens4096及所有数据/JSON/policy/编辑边界不变，choice保持原协议。复用typed任务、数据builder、Grant/双重rebuild/ticket/audit与原子Publication；源优先/W1可选保持。新合同/pins/审计隔离，不改旧资格或失败。无需外部代码/依赖，无许可或云集成变动。

未采用：仅拉高全局预算（仍给思考消耗更多，不直接隔离H1且增加等待）；同时改提示/temperature/模型/JSON模式（难归因）；拆两请求（原单请求精确范围且未证必要）；读取CoT、放宽length/补答/重试（不能产生可信完整结果）。新模式可能降低语义质量，必须用真实局部修订和新选择检验，不能预设不思考必然好。
