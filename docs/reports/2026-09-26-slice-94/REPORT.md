# Slice-94：相同表达输入的high配置准备

2026-09-26，基线674b910。新增单阶段有界表达试验，真实调用0；S93失败与原答案保持，不做重复规划或资料补齐。

## 实际约束

prepare以当前Facade重新构建整个S93父计划，并联查完整六题的规划、派生请求和表达结果；绑定父计划文件与31份相关审计指纹。不能输入任意projection、补F30或发送旧答案。重复表达digest在准备阶段拒绝，避免不同来源case落入同一账本键。

六个表达投影和EXPRESSION_POLICY原样冻结，只改为thinking enabled/high、4096总completion、无temperature。每题一次、总6，规划0；新精确批准才装配Gateway，发送前再次核对父审计，先记录attempt再延迟读取凭据。故障全停，投递不确定unknown、凭据缺失unavailable、已知校验失败FailedClosed；重启只读严格缓存，不重发。

Facade仍是业务Interface，复用既有冻结账本/安全Transport/表达校验。普通S91 local-only和S92两阶段语义未改变。最终候选required/persisted=false，不写正式聊天或生活状态。

## 验证

42个唯一用例通过：新试验首组22项（101.98秒），新增合法父记录但表达digest重复的准备拒绝1项（3.04秒）；有限S91/S92相关回归19项（58.51秒）。涵盖新/旧批准隔离、完整源审计、内容不变与规划0、6次上限、未知/失败/凭据状态、审计损坏、恢复和重复调用。

新上下文Sol high按code-review独立检查，未发现可行动实质问题，未重复跑测试或读取私人资料/凭据。静态差异检查通过，测试进程均结束。

## 真实资料仅prepare

新plan `3f2cf4f198aa26825639e96d45e9737285fc777f129aa05726b1e39573808de5`，parent `47f119a43d2e7be1dc57b5d183e6e9f12cd94b061c13c91921cd72e457c32ea0`。实际prepare成功，run未启动。

主窗口逐项比较实际源projection、原HTTP body摘要和新body：messages/policy完全相同，除max_tokens/thinking/reasoning_effort/temperature外所有字段一致。旧答案、参考标签、context/parent/audit标识不在模型body。新body5139–5889字节，合计33856字节。记录仅本地`.local_indexes/eromanga-sensei/s94/preflight.json`。

新6次与预算尚未批准，见[具体方案](../../plans/expression-thinking-comparison.md)。效果尚未知，不能用这些本地测试宣称high已修复S93错误，也不能据此否定独立的规划漏选问题。
