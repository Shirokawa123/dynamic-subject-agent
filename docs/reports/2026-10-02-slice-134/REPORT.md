# S134：发送前看清本轮范围

连续十片7/10，2026-10-02。用户可按需查看当前草稿实际参考的人物核心、相关资料、作者解释范围及最多两完整轮原话。预览不发送、不修改草稿或原请求，不作为发送许可；编辑、开关、边界/scope或新状态变化使旧内容失效，迟到响应丢弃。内部digest/fingerprint、system policy与ID不呈作产品正文。

Facade `preview_whole_message_scope`从真实readonly basis读取，与正式发送共用whole前缀/控制/终态失败证明/cutoff/完整窗口选择；正式wrapper仍要求真实admitted/frozen attempt，预览不虚构operation、不admit/claim/恢复、不进worker。Authority短锁取fresh授权后释放，两次只读快照比对及末次权限复核丢弃变化。history-off仍先核完整性，legacy receipt-only不能预览可执行请求；正式send仍重新裁决。

实际两次明确预览→发送，Provider observation的request_digest均与预览projection_digest完全相同，边界后历史窗口分别0/1。第一条正常提交，第二条`response-content-empty`失败保留，0重试；预览展示不保证模型能完成或说得忠实。第一条仍把当前绘画取舍说成一般习惯，未因此写入人物权威。off/on实测1→0→1、旧snapshot随history revision失效，composition重开得到相同projection；这些操作0模型且canonical不变。首条后发生的普通终态失败使既有保守上下文选择缩小，后续UI如实显示当时0轮，不冒称从未交流。

隐藏实际页面验证按需查看、编辑后旧内容清空并提示重新查看、重查对应新草稿、收起保留草稿；没有触发发送，最后只清理自有测试文字。5条已提交聊天与history=true保持，账58未增加。证据见[metadata](scope-metadata.json)；正文只留canonical，截图仅控件。

![本轮范围只读预览控件](scope-controls.png)

必要29项兼容组及最终5项新源码检查、入口17项Interface/HTTP/Node与独立稳定core只读复核通过。包括正式frozen校验、preview零写入、pending及时关闭、切换/损坏无旧结果、最小发送内容旧行为与S132原子性；并发与损坏分支是合成验证，不冒充真实故障。来源见[研究](../../research/2026-10-02-local-chat-control-gaps.md)与[实际计划](../../experiments/s134/CONTRACT.md)。

本片2真实/1提交/1空白/0重试；whole账58，批次50真实/37提交/13空白。下一片补较早已提交聊天的本地查找；不扩大Provider历史窗口、素材/slot、生活/S1、人格关系写回、云、删除或迁移。
