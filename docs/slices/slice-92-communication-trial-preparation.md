# Slice-92：两阶段生成试验的冻结与恢复准备

2026-09-26，基线b91d59c。仅实现和本地验证[六题新用途方案](../plans/communication-plan-generation-trial.md)的可执行准备，真实调用0；未经新批准不能读取凭据或发送请求。

## 结果与范围

用户需要比较真实两阶段生成是否减少近期心理活动/习惯/频率的虚构，同时保留正常话题、职业事实和条件观点。S91已实现本地流程；现在补齐其远程试验的精确范围与一次性执行，避免授权时仍有未明确的动态第二阶段输入。

复用S91纯规划/裁决/表达构造、现有Facade/Producer、ModelGateway、DeepSeek Transport、安全诊断与FrozenAttemptRun。新增显式trial composition及CLI，默认prepare；普通S91入口继续local-only。不要以allow_remote布尔绕过原型限制，不修改旧Provider默认路径。

## 固定计划

六题文件version=character-communication-plan-cases-1，每项exact id/message/context_mode，消息无旧candidate。只接受6个唯一case。冻结v9草稿、subject/anchor、knowledge预算、每项Facade stage-one投影/请求及outbound指纹、两阶段固定policy/生成参数、动态派生规则版本、数据保留、最多12次与故障停止规则，绑定单一精确plan digest。

规划deepseek-flash thinking enabled/high、4096总completion；表达同模型非思考600、temperature0.3；JSON、不流式、无tools、30秒。第一阶段字段来自S91；第二阶段只准由本地QualifiedCommunicationPlan重建的最多4个完整已选事实、合法动作和本次固定交际前景/消息，不能接入任意自由文本计划或其他来源。内部digest/账本/ID/参考标签不进两个模型输入。

## 执行与失败

只有approve-plan精确匹配且重新准备一致才装配远程Adapter，凭据继续在发送时延迟读取。每题最多规划1次、表达1次；每个stage发送前独占写attempt，记录受限输出/安全失败，不保存推理/raw response/headers/异常原文。只有合法规划结果完成本地裁决且审计成功后才允许表达；表达实际请求及指纹在发送前记录，须能由冻结输入与合法规划结果重建。

任一来源/凭据/传输/格式/裁决/记录故障停止全部六题；缺凭据typed unavailable、已尝试但结果/记录不确定为unknown、校验失败FailedClosed明确区分。结构有效的自由台词保持required/persisted=false，不自动审核、修订或写canonical状态。诊断码只在闭集内，不传任意异常文本。

重启只读完整有效缓存，任一阶段缺失/损坏均不重发、不续发第二阶段，不以新root/CLI选项重置。跨case/阶段审计或规划引用篡改不能被当有效缓存。单进程重复也不得重复发送；整体上限12。CLI固定实验root，无循环重试参数。

## 验证

实际Facade加Fake Transport走成功两阶段与授权/动态来源约束；预览/旧批准/未批准零调用，非法规划零表达；第二阶段无未选源/内部digest/任意模型字段，完整限定保留；格式/截断/审计/凭据失败、任一阶段崩溃恢复不重发，重复调用与源变更关闭。保留原直接生成及S91相关回归，不造新测试类别。

实际六题仅prepare并导出第一阶段精确请求和第二阶段受限示例，检查计划未启动。模型真实收益仍待用户批准后验证，不能把预览或假响应当效果。该片是已研究机制的执行准备，无新依赖/心理学推论；参数和Transport复用已核实协议。

状态：受限trial实施、73项唯一用例及独立复核完成，0真实调用；真实六题plan `47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0` 重建一致、未启动。见[报告](../reports/2026-09-26-slice-92/REPORT.md)，等待[新用途具体批准](../plans/communication-plan-generation-trial.md)。
