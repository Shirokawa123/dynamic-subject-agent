# Slice-94：冻结实际表达输入的算力配置对照准备

2026-09-26，基线674b910。只做离线准备，新增真实调用0。S93的12次许可已用完，不能转用。

## 结果、缺口与依据

S93先规划/再表达流程结构正确，但06近期活动、08习惯、19插画年限仍被表达器扩大；19还独立漏选参与设计的F30。现在要区分“给表达更强计算是否有帮助”和“内容计划/资料是否有缺陷”，而不是继续增加字段或改提示。用户结果仍是自然但不捏造的回复。

复用[交流计划研究](../research/2026-09-26-communication-plan-boundary.md)中规划不保证表面文本忠实的结论，及S85/S88/S90实际核对过的[官方thinking参数](https://api-docs.deepseek.com/guides/thinking_mode/)与[接口协议](https://api-docs.deepseek.com/api/create-chat-completion/)。high/4096已在同一接口规划/审核运行，本次只移至同schema的表达任务，无新SDK/依赖或心理学理论。S90的配置改善是动机，不是本表达任务的效果证明。

## 最小实现范围

- 从S93完整且经原校验函数联查的6份实际expression request提取投影。先验证源parent plan、两阶段attempt/result、derived request及原context，不能接任意手写projection或缺失/损坏的审计。
- 新单阶段有界expression诊断Producer/Adapter/CLI复用Facade、Gateway、冻结账本、S91表达结构校验与安全Transport。可以小型独立实现，勿修改旧两阶段语义或构建通用实验框架；普通local-only入口不变。
- 冻结6份原样实际表达投影、EXPRESSION_POLICY、源parent/审计指纹、源资料依赖、模型、thinking/high/4096、无temperature、JSON/非流式/30秒、6次总限额。只发送原selected_facts/action/前景/消息；本地parent/审计/digest不发送，不增F30、不发旧答案或评分标准。
- 每题只表达一次，没有规划、额外审核/重写。只有具体新批准与重新prepare一致才调用；任一故障全停，先claim再鉴权，重启只读严格缓存、未知不重发。闭集code及unknown/unavailable/FailedClosed沿既有规则。
- 最终候选仍required/persisted=false，不成为新生活事实。保留原失败，不替换S93答案。

## 验收与限制

通过Facade/Fake Transport证明规划0、每题表达1、总≤6、未批准/旧批准0调用；HTTP投影/policy与原S93完全相同，只变生成配置；源审计/资料变更或篡改拒绝；失败和恢复不重复。旧S91/S92相关行为回归适量复用，不重复无关全量测试。

用真实S93资料仅prepare，核对六份表达内容逐项一致和未启动，提供精确可审方案后再申请6次新调用。不能先试后补批准。

若有改善，只能支持该固定输入上的配置判断；它不修复规划漏选，也不证明一般单阶段生成或日常聊天已可靠。若仍无改善，停止在本方向追加相同试验，转向明确产品取舍，不以无限提高预算代替设计。

状态：离线实施、42项唯一用例及独立复核完成，0真实调用。实际plan `3f2cf4f198aa26825639e96d45e9737285fc777f129aa05726b1e39573808de5` 未启动，新旧messages/policy逐项相同，见[报告](../reports/2026-09-26-slice-94/REPORT.md)。等待[6次表达配置对照](../plans/expression-thinking-comparison.md)的新次数/预算批准。
