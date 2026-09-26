# S103：已批准派生人物的准确封存与恢复

用户已批准S102精确定义、私人来源用途、创建/进入和后续真实聊天。当前要兑现可重启的同一人物，不能继续停在预览，也不能将小说派生资料声明为原创。

## 本次源码核查

主窗口、Sol实施者及新上下文Sol只读复核一致确认：可复用Studio已有genesis_snapshot.snapshot_json与其整体digest，新增仅新记录带的版本化reviewed-definition envelope，不需新表或旧库迁移。该envelope承载完整自持资产、摘要、来源/用途、完整definition basis和内容mapping承诺；旧payload不添键，旧digest保持。

现有seal的重放检查仅比较FreezeDecision，须额外比较新envelope；现有query_qri/Host._verify_published_qri只验QRI，须对新合同联查snapshot/资产/profile与genesis来源。仅把JSON放进数据库并计算自报hash不足以守住内容绑定。

S102有8组Knowledge映射，而旧Studio旧契约最多6条。新合同的30条认识与4条解释完整留在sealed runtime asset，不能截断、拼塞为6项或把人格写成Knowledge fact；旧空Knowledge载体使用准确的新qualification，旧原创的限制和旧数据不改。只新Studio的DDL允许新资格值。

Profile ID和publication key必须由完整definition basis派生；旧mapping中的Profile ID只对应知识映射，不能直接用于两份不同人格的新身份。显示姓名、身份文字、起点、知识和解释严格保留批准内容，运行时不复用未封存文件。

默认PolicyKernel仍拒非原创/有asset refs；新增精确私人人物合同仅接受匹配的origin/use/rights/basis/refs/private proof及专属manifest。普通publish当前把非M0一律标DeepSeek，必须增加准确的manifest/authority配对，不能借旧accepted-artifact激活路线。新角色先采用独立dormant cognition，旧六Domain Provider装配明确拒绝；本片不启动聊天或网络。

Host.ALLOWED_PROVENANCE控制的是命令来源，并非人物素材来源，本片不修改。无关旧artifact/llama迁移硬码也不改。LocalIdentityAuthority维持唯一注册/选择/Host准备职责，registry顶层v2保留，角色类型从已验证Studio内容推导，不能信任可改的registry标签绕过检查。

## 一手资料与机制取舍

复用并定向核对[W3C PROV-DM的revision/derivation](https://www.w3.org/TR/prov-dm/#term-Revision)：来源派生与新版本须可追溯。工程适配为新内容basis、新身份ID和准确来源，旧定义不覆写；不引入RDF，也不把出处追踪当语义真实性证明。

本次读取[SQLite原子提交机制](https://www.sqlite.org/atomiccommit.html)：事务保护同一数据库的提交边界。适配为让封存资产与Genesis快照同事务、同完整性校验；Studio publication与registry跨文件不能宣称天然同一事务，因此继续采用确定性basis/publication key及既有幂等恢复，测试发布后注册前中断。不是重新发模型请求来恢复，也不新增第二聊天真值库。

比较结论：复用既有深Module与snapshot JSON，增加小而封闭的新合同；不选择新并行数据库、原文路径作为运行依赖、全局放宽来源或冒用旧dormant artifact。没有新外部代码/依赖，许可证与维护成本无新增项；新增逻辑有明确恢复/隔离测试负担，已纳入任务书。

这是来源/持久化工程，没有新心理状态推导，哲学心理学不解释原子提交；四条人格仍沿S98/S101的有边界解释。验证关注相同内容重放、异内容冲突、源文件移走后的恢复、坏资产拒绝和旧路线不变；模型调用及真实聊天均为0。

实施决定：接纳上述最小设计，先完成精确dormant身份的创建/选择/恢复，再在下一切片接生产聊天。后续激活必须继续匹配新合同与既有已批准聊天scope，不能使旧六Provider接管新角色。
