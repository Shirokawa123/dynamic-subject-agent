# M002现有记录接入：只读观察与合成兼容检查

本轮由独立游戏产品M002驱动，用户允许继续后台接入准备；安装、旧Timeline升级和迁移尚未批准。验收表面为Facade，新增静态`inspect_memorie_continuation_source(MemorieSourceInspectionRequest)`，无sender、Host/Studio实例或写入操作。

## 已证缺口与来源比较

用户结果是沿现有梅莫莉和同一段经历继续点击/文字交流。S160沿schema1、SubjectCommand和同一资格绑定；M002 native沿独立review/schema10和NativeInteractionInput。`LocalIdentityAuthority.activate_reviewed_chat`先拒不同已有chat_activation；`RuntimeHost._replace_binding`在SubjectEvent封存后禁止普通资格重绑。既有ForwardGovernance/CorrectiveSuccessor依赖旧LOCAL专用plan、六库摘要及特定来源资格，不是Memorie历史升级许可。

因此保留这些守卫。新的非空Timeline续接机制需要保旧身份、旧请求/发表证明、单写者和新增记录，不能改旧指纹、复制活跃Timeline或另建开发身份代替。此次不声称已有迁移程序；只读观察永远返回`apply_supported=false`、`publication_prefix_verified=false`，不构成升级批准。

SQLite机制按context7-mcp核[官方URI参数](https://www.sqlite.org/capi3ref.html)和[事务说明](https://www.sqlite.org/lang_transaction.html)：`mode=ro`阻止写入，BEGIN/SELECT建立读事务；不用对变化数据库关闭锁定/变更检测的immutable或nolock。实际engine使用DELETE journal，本轮只接受此模式并复用既有只读连接/正规文件及路径检查；不作checkpoint、改journal或复制文件。连接遇busy/locked返回unavailable，读取完立即关闭。纯工程准备不新增心理/活动机制。

## 观察的含义

只选registry中准确active Memorie，核批准与contract、QRI元数据摘要、Host唯一active binding/记录中的写者、Timeline注册/manifest/gate、schema/头与状态计数。文件路径限定于显式产品目录，registry前后字节变化则丢弃观察。结果仅元数据；不查询用户原话、回复、人物正文或草稿，不验证完整旧Publication内容，也不证明后续静止/停写状态。

产品端只GET原8798 `/health`核原准确entry/version，不请求session/status；可提供实际监听PID与lease记录比对。私有完整观察只存忽略目录，公开报告不含身份ID/路径/聊天正文。当前服务保持。

## 合成检查与限度

用真实Facade/生产S160组合写合成旧交流后：只读观察在禁止正文表读取的SQLite authorizer下通过，文件集合/摘要保持，Host.open与Studio.open被替身禁止仍可检查；缺失源/错写者不创建文件或输出可应用方案；已native源为typed NoOp。

两条合成旧交流可经Facade审阅为typed `kind=text`，新点击仍无text；这仅证明格式可以表达，不是把外部历史注入运行资格。尝试native factory被activation-conflict拒绝，旧文件不变；重开旧入口仍同identity/Timeline、旧UUID只读查询与原记录逐值保持、0额外模型请求。此为兼容与拒绝后恢复检查，不是schema1→10正向升级或回滚成功。

下一工程需设计并实现适用于非空Memorie Timeline的显式资格续接/历史读取合同，再验证成功与中断恢复；完成准确可执行变更方案后才承接用户数据变更批准。本观察不可作为该方案的替代。
