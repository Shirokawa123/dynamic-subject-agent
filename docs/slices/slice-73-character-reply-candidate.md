# Slice-73：人物上下文到回复候选

状态：已完成，基线e6973e1。

结果：Facade能将S72已核验上下文转换为精确、只含必要字段的角色回复候选请求，经ModelGateway离线替身完整验证返回与失败。输出只称candidate，结构合法不代表角色语义正确；不进入Timeline、Memory或身份背景。

复用既有ModelGateway、production composition和S70/71核心背景/场景分区结论；单独typed task避免旧角色reply Adapter误接新投影。只允许显式local Gateway的实验装配，默认unavailable；不加真实Provider路由/凭据用途、不复用旧试聊。单请求不带历史，不自动重试。公开开场不进请求，本人知识/阶段/分支/披露/当前消息显式白名单。

输出exact reply_text/language，中文、非空<=1200字符，额外状态字段/错误类型/异常失败关闭；不宣称Python已判断人物语义。CLI提供精确请求预览，不伪造角色体验。实际v8请求落盘，并准备新增外发内容说明；只有可执行真实Adapter和具体批准完备后才真实验收。

测试覆盖同一Facade/production路径、Gateway任务与字段、异常/额外字段/不匹配、源失效不调用、默认缺失/关闭、remote gateway拒绝、旧聊天不回归。报告与commit/push。

收口：[报告](../reports/2026-09-24-slice-73/REPORT.md)。77项相关测试及两路代码复核完成，实际v8请求预览成功；真实Provider调用0。
