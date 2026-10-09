# S147已授权用途内的独立技术候选

本轮继续开发依据见[用户决定](../../plans/character-chat-direction.md)。沿S146已批准basis `e87c9db1f6f52409faee497ca05f0852362add519e461d48f50bee27d760977c`的三个用途、材料、字段上限及Provider/Windows默认slot；本文件不是新增人物资料或后台运行的批准对象。

[候选合同](fact-faithful-contract.json)独立锁定三策略与协议、authority/audit及`fact-faithful`标记。对应范围段区分既有事实与新设计，不从角色名猜属性，也不将资料缺项当作属性不存在。S145/146的原grant、策略和contract保持。新增候选资格只供独立新入口，schema仍7，不升级旧记录。

[首轮场景](live-entry-scene.json)冻结8个首次请求：两次普通交流、独立初稿、两原话/实际初稿形成理解、名称外形澄清和故事换题、实际关闭服务器/product重开、据有效理解推进、原nonce只读、结果接话。每阶段1请求0自动重试，首技术或完整性失败/无方案/依据不足/无实际变化停止，不补抽。形成后先由主窗口只读canonical核范围和出处再放行；这个语义判断不是模型审核或自动人物重写。

脚本`run_s147_entry_acceptance.py --self-check/--preflight`不创建产品资源、不读取凭据、不调用模型；`--execute`才在固定独立开发root用新的HTTP入口逐阶段执行，临时loopback随机端口，关闭结束。正式8794持续服务另按具体启动动作确认；不碰旧8793及用户草稿。

完整metadata与真实正文只保本机各自ownedroot/canonical。仓库公开仅阶段/总量及结果汇总，不发布完整AppData路径、凭据读取计数、逐请求或输出hash/audit链、模型推理或正文副本。工程通过与真实人物内容分别评价，单次成功不能证明长期或真实跨天质量。
