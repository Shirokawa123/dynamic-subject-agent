# Slice-44：转述与引用的Memory归属裁决

状态：完成。用户2026-09-17批准继续，基线a915eeb / dogfood-s42。

用户结果：Slice-43第22轮“小夏说：……”不再将引号内第一人称摘录写成无归属active Memory；拒绝截取时回执与实际结果一致。先用ApplicationFacade复现create/revise候选，核对引用/嵌套/条件/混合自述边界，合法当前自述仍可保存。

调研成熟项目如何绑定说话者、引用范围与文本位置，优先复用current_message与memory_evidence_scope。只加强当前候选在完整消息内的证据裁决；不新增模型字段/提示/调用/历史用途、归属实体或store，不合成原文。完整保留来源归属的原文沿原Memory契约，不能把完整引用当引用内命令授权；不清洗旧错误记录、不删除历史。

正反Interface回归、原五条不变量、代码复核和全量测试；新隔离合成身份后台真实原文、新题材与重启对照。既有DeepSeek用途不变，不读正式身份或抢焦点。记录首次失败和有限范围，STATUS最多5行，commit/push收口。

收口：22a0901 / dogfood-s44；837 passed、11轮真实后台和两次重开一致。原真实转述本次模型NoOp，新题材create最终拒绝；原强制create/revise在Interface被拒绝，完整归属、自述与既有更正保持。旧数据未清洗。见[报告](../reports/2026-09-17-slice-44/REPORT.md)。
