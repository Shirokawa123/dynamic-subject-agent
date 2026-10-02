# 后续候选开工证据：本轮范围与旧聊天查找

2026-10-02。S132仍是唯一执行；下列是代码证实的缺口与接入建议，未授权并行实施或预定片数。待每个结果成为current后再实施。

## 发送之前能核对本轮范围

当前HTML“这次会用哪些内容”只有固定文字。S128选择器会根据当前文字和两轮用户原话选资料，S132又加入本地边界，用户无法直接知道开关/边界是否使下一次历史窗口为空。S133的人物全部依据也不等于本轮实际选中资料。

Microsoft HAX [G16](https://www.microsoft.com/en-us/haxtoolkit/guideline/convey-the-consequences-of-user-actions/)支持提前/事后解释操作对行为的影响。可借鉴“按需预览后果”，不把预览设成每次必过的审批，也不能把选择资料称为模型解释。研究提供设计理由，实际可理解性仍需入口验收。

复用`projection_for_contract`、当前准确whole authorization、已验证Timeline对话范围与现有≤2完整轮/4000预算。新增Facade只读预览：当前主动草稿经本地计算，显示人物资料选取及实际历史窗口；不claim、不admit、不生成、不存草稿、不写Timeline。明确预览只对应当前快照，发送仍按最新状态重新核验；历史/边界/输入改变时使旧预览失效。来源损坏/权限不确定/pending及时不可用，不能用history-off跳过验证。不得新增远程摘要、第三方分析、前端人物组装或旁路历史。

可观察验收：真实已审资产的本地预览与同快照实际请求digest吻合；off/新边界后历史0、on仅本段≤2完整轮；修改草稿不显示旧预览，打开/关闭/刷新不发送且草稿保持；预览不把模型生成错误变成事实依据。心理理论不适用，纯工程与用户控制足够；不引入新依赖或第三方代码。

## 找回20轮之前的已提交原话

代码缺口：`ApplicationRouter._list_conversation_turns`固定limit=20，现有UI只渲染这一窗口；`TimelineEngine.list_conversation_turns`虽校验canonical全链但上限100。当前“旧记录保留”是存储事实，却不是完整历史可达性。不能让用户靠问模型回忆，或为查旧话扩大Provider窗口。

复用canonical `ConversationTurnRecord.head_sequence`和全链校验，加独立本地只读历史页/搜索Facade：按逻辑序号翻页，明确已返回数量与是否还有更早内容，分隔S132新交流边界但不删旧话。请求固定同一身份；查询词只本地处理，系统回执不是聊天原文。避免offset在并发新提交时跳页，使用已核head及before序号；过期或损坏返回明确状态，不拼接来自两个身份的结果。UI可搜索原话、前后页查看、返回最新，草稿和原请求保持。

HAX [G7](https://www.microsoft.com/en-us/haxtoolkit/guideline/support-efficient-invocation/)支持在需要时让用户主动调用能力；这里采用独立本地查找入口而非让模型猜测。既有[W3C PROV](https://www.w3.org/TR/prov-overview/)分层同样适用：历史只证明当时说过，不证明台词是真实设定。此类比不引入PROV实现。

补核[SQLite官方Scrolling Window Queries](https://www.sqlite.org/rowvalue.html#scrolling_window_queries)：OFFSET需要跳过前面的结果，官方示例用上一页最后的有序键继续；效率结论依赖合适索引。本次只适配稳定键边界这一机制，使用既有head_sequence，仍先完整验证canonical，不据此声称当前全链校验已变成常数成本，也不为分页增加SQLite版本/索引/表。以序号而非位置定位可避免新消息插入头部导致旧页位置移动，这是本仓append-only事实下的设计推论。已按context7技能resolve到`/websites/sqlite_docs`并query；未命中该专题，故回退到上述官方页面。

验收应包含超过20轮的合成canonical、真实本支既有原话只读比对、多页无漏重、同身份边界前后均可查、未结算不冒充已提交/坏链关闭、查询/翻页/刷新0模型且不增加记录。此处读取是用户本地查原话，不是Provider取材；待处理新轮不进入结果，也不必因此遮住已经核实的旧提交，history-off同样不删除本地可查历史。具体pending提示随当前只读合同落实。合成大量历史只用于接口，不当作真实人物体验；真实正文不导出Git。无新库或存储、无更多历史外发；不做全文向量索引、搜索模型或跨root汇总。
