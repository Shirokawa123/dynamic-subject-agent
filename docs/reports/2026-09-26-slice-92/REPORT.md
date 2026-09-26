# Slice-92：两阶段生成试验准备完成

2026-09-26，基线b91d59c。完成独立受限trial、Adapter、composition与CLI，默认prepare，真实调用0。没有解除S91普通入口的local-only限制。

## 可执行范围与实际约束

六题第一阶段投影/出站字节、两阶段policy/参数、derive规则、每题2阶段及总12次上限被同一plan绑定。只有新用途的精确批准且重新prepare一致才能装配远程Adapter；凭据在实际发送时延迟解析。

第一阶段发送前写attempt，返回规划经闭集裁决且审计成功才构造表达。第二阶段Gateway传本地绑定对象，Adapter从冻结context和已审计合法规划重新构造投影，并核对发送前记录的实际request/body指纹；它不接受外部随意提供的表达投影。case/attempt/digest等内部信息不进入模型body，参考标签、旧candidate、历史或生活状态也不发送。

每阶段单次，任何技术/裁决/审计故障全批停止；缺凭据unavailable，已知校验失败FailedClosed，明确投递不确定unknown。恢复严格联查attempt/result/派生请求/来源，缺失或篡改不重发、不续发表达。合法候选仍required/persisted=false，不成为事实或正式聊天。

## 验证与复核

73个唯一用例通过：

- 新trial初组34项（119.17秒）；完整六题成功与严格index缓存补验2项（7.97秒，其中新增1项）。
- S91本地行为和Gateway34项（40.24秒），确认普通入口、默认路径与抽取共用表达校验保持。
- 新增投递不确定4组合最终闭集版本（24.37秒）；之前同4项初次通过不重复计数。

覆盖审批前零调用/零凭据、6题12次上限、两阶段最小派生与完整限定、计划非法无表达、源变更、故障/崩溃/审计、部分或跨case/阶段缓存篡改、未知引用、重复操作与重启不续发。Fake Transport及文件快照验证，没有真实网络请求。

独立Sol high发现明确投递不确定最初被记成FailedClosed；修复后unknown只接受transport-delivery-ambiguous/transport-timeout且value=None，FailedClosed反向排除两码。复核者纯fake定向验证停止/缓存及普通网络故障区分，无遗留发现；未重复全套测试。新规则不回写旧S86记录或推断其真实原因。

## 真实资料仅prepare

精确plan `47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0`，实际六题prepare后再次重建，指纹不变，run目录不存在。第一阶段投影与S91逐项相同，body6101–11516字节，合计58524字节；max_calls=12。

本地`.local_indexes/eromanga-sensei/s92/preflight.json`记录核对；`expression-examples.json`是明确标注的合法人工选择示例，不是实际第二阶段请求或模型回复。真实第二阶段须等合法规划后才确定，不能预先声称其body已冻结。

本片不验证语义收益、自然度或MVP完成。执行与保留依[六题/最多12次新用途方案](../../plans/communication-plan-generation-trial.md)取得新批准；S90已消费的16次审核许可不可替代。
