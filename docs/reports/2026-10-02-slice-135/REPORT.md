# S135：找回更早的已提交聊天

连续十片8/10，2026-10-02。新增同一人物分支的本地已提交聊天分页/字面查找，摆脱原入口仅最近20轮的可达性限制。完整双方原话与SYSTEM交流边界分开，查询不发模型、不改变近期参考窗口或新交流cutoff，也不把台词当人物事实。

Facade `query_whole_chat_archive`通过当前whole权限及首末fresh scope核验；Host独立readonly/query_only单事务验证manifest/schema/gate与完整Publication链，不进入worker/admit/恢复。每页最多20项按稳定head_sequence游标读取，query保留空格、%与_的字面意义；无新表/索引/schema。pending只标记，不冒充已提交，也不遮住可核旧轮；history-off仍能本地查原话。legacy只读不因此恢复Sender。每页仍全链验证，未声称常数成本。

实际自有8787：5轮原话与现有canonical历史逐项hash一致，2条边界准确可见；before游标返回5项较早记录，旧段字面匹配2轮、当前段匹配1轮，空查询结果与百分号字面匹配正常。关闭历史与重开后查读不变，canonical/边界/最终开关保持，模型账58未增加。见[metadata](archive-metadata.json)。超过20轮的跨页/追加新提交无漏重由21轮＋2边界、再追加第22轮的合成Interface证明，未把开发分支灌成大量真实聊天。

隐藏实际UI验证全部5轮/2边界、旧段查找、无匹配、返回最新、收起；自有草稿原文、history=true与5条主聊天保持。最后仅清自有测试草稿。8个不同核心重点场景、19项入口Interface/HTTP/Node及独立稳定core复核通过；坏链、foreign、设置竞态、pending并发及legacy/S134/S131兼容均有必要覆盖。来源见[研究](../../research/2026-10-02-local-chat-control-gaps.md)。

![本地查找控件，不含聊天正文](archive-controls.png)

本片真实模型调用0，批次仍50真实/37提交/13空白/0重试。完整历史只在本机查看，Provider仍最多两完整轮/4000，原素材、凭据、生活/S1与人格关系边界保持。下一片把新context能力做成可重复打开的独立空历史入口，不替换旧入口或迁移记录。
