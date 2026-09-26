# Slice-99：人格对照的可执行冻结准备

2026-09-26，基线b9f9873。S98本地底稿与接线完成，当前用户授权继续至可体验MVP或具体新用途决策处。用户结果：确认[已写清的四条人格/常驻核心用途](../plans/personality-behavior-trial.md)后即可执行同一六情景对照，无须确认后才开始搭执行路径。

## 范围与证据

继承S98研究与实际原作结论，不新增人格解释、素材或Provider目的地。纯工程问题是把两个新envelope纳入已有冻结计划、逐阶段裁决和恢复机制，保持旧远程入口不接受新用途。开工适用性核查写入S98研究文末；不安装外部工作流库，不改变API配置。

复用已有CharacterCommunicationTrial/FrozenAttemptRun及DeepSeek单次transport；必要时以小型内部契约变体承载新projection。默认旧计划/字节及旧Adapter保持；新增用途必须有独立plan标识、资料/sidecar/policy/config绑定和明确approved_plan，不能从旧批准开启。

准备基线6题×2阶段与人格6题×2阶段共最多24次；两条件high/4096、30秒。本片真实调用0，不预留/消耗200额度、不读取credential，批准前不装配真实发送。输出exact规划请求、表达派生规则/示例与计划摘要；真实表达必须来自当轮成功规划审计，不能手写替代。

## 必须成立的检查

- 新envelope保持四组core/personality到表达；严格引用/动作裁决和候选required继续。
- 未批准、旧批准/旧Adapter、资料/sidecar/policy变更、越界输入在出站前拒绝；输入日志不带推理或凭据。
- 发送前claim；失败/未知投递停整个计划；重新启动只读可验证结果，缺失/损坏不重发或补发表达；两阶段审计与派生请求绑定。
- 真实Provider用fake transport验证准确wire和credential lazy行为；不触发Windows实际凭据访问。
- 旧默认行为必要回归通过。真实v9只prepare形成两个固定计划，不执行。

主窗口负责docs、真实本地准备及最终接纳；Sol负责明确实现/测试文件，单写者。完成提交push，停在新增人格输入用途确认；同范围调用额度不重新申请。

状态：完成。28项唯一检查通过，两实际计划prepare成功且未启动，旧high基线digest完全保持。见[报告](../reports/2026-09-26-slice-99/REPORT.md)。真实调用0，停在[新增人格输入用途确认](../plans/personality-behavior-trial.md)，首轮对照最多24次从既有余量扣。
