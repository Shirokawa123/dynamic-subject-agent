# S126开工证据：原人物整体回复用途的本地准备

用户结果与可观察验收见[S126](../slices/slice-126-original-whole-use-preparation.md)：从既有已审完整定义得到一份精确绑定的用途审核清单，仍不能执行或获得远程资格。已证实缺口是S102只准备定义与旧两阶段用途，S119整体回复资格固定合成小林；不能用其scope外发原人物。

本次核对[已有S102准备研究](2026-09-26-complete-character-definition.md)、`ApplicationFacade.preview_character_identity_preparation`、完整定义的纯校验、`reviewed_character_chat.sealed_model`及`prepare_context`。复用已审定义/起点/人格、结构与basis核验、现有核心及相关材料选择；不重新提取小说、不打开用户运行root、不读私聊。

定向读取[RFC 8785原文](https://www.rfc-editor.org/rfc/rfc8785)摘要及3.1：稳定表示用于可重复散列，重复对象属性不应成为含糊对象。本仓继续使用既有`canonical_json`与SHA-256，未宣称实现RFC的全部JCS数值排序规范；新增用途basis独立于旧definition basis，绑定定义/资产/persona及精确用途字段、策略、输出格式和参数。只在新输入边界拒绝重复JSON键，不全局修改旧解析或旧basis。

复核[S122](2026-10-02-s122-experience-choice-evidence.md)及[S123](2026-10-02-s123-proposal-source-evidence.md)适用性：完整双轮/说话者/原话与世界事实的区分仍适用，但本片只准备字段范围，不评价生成回复或人的心理。纯工程用途审核不需要新增哲学/心理学解释；它也不能证明LLM的记忆、人格或交流理解。

最小接入为Facade上的纯作者准备入口：只读显式本地完整包，逐项核对expected definition/asset/persona与subject/anchor，返回独立review DTO；公开导出仅摘要、数量、字段清单和自写合成消息/空历史/无生活事件示例。真实最小人物投影只在内存中复用选择并计算摘要，不复制人物正文到review。远程授权与execution始终false，不构造ModelTask或freeze/select/activation请求，不触碰Gateway、Credential、Authority或canonical store。

不采用新建角API、第二定义库、原用户root查询、把旧scope改为whole或将preview包装成可发送ModelTask：现有资产与准备机制足够，缺口只是新的用途绑定。没有引入外部代码或依赖，许可/维护新增成本为零；RFC只作设计依据。未引入S1、生活生成、云端、人格重写或迁移。

验收通过Facade检查稳定basis、对象/资产/用途不符关闭、缺文件unavailable、确认不授予权限、无正文导出及旧定义兼容；断言0模型/凭据/身份写入，现有远程Adapter拒绝review DTO。真实S102包只本地0调用校验，公共记录只摘要/数量，工程准备完成不等于新用途获准或人物体验通过。

## 实际接线与验证

Facade新增纯static `preview_original_character_whole_use_preparation`，无需实例router或产品root。`reviewed_character_definition.validate_character_preparation`共用原完整内容校验、保持包内确认值；旧`prepare_reviewed_definition`仍先检查真实freeze命令确认，再按原位置生成signed副本。新review不构造freeze型对象，现有Authority验证仍默认要求rights确认。

新Interface/CLI与旧完整定义、身份准备、封存兼容共77项通过（22项新用途准备、55项兼容），`git diff --check`通过。最初未配置PYTHONPATH无法收集；补齐后默认系统Temp ACL拒绝，显式仓库basetemp又因temporary权威未对应而被产品路径保护拒绝。最终只在独立测试进程配置专用temporary目录，未放宽产品路径规则或修改系统配置。

主窗口实际S102包0调用预览成功：30条认识/4条人格、实选core4/related0共864个JSON字符；实际包字节、旧definition basis与runtime asset SHA保持。review/scope/实选材料均独立摘要，返回不含原人物正文；remote、execution、rights/use标记均false。精确实际结果与拟用途方案由[S126报告](../reports/2026-10-02-slice-126/REPORT.md)接纳，不将hash或这些测试当作新用途批准或人物体验验收。
