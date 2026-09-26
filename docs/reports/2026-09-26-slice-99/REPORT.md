# Slice-99：人格对照冻结执行准备

本片为S98同一人物底稿准备实际可执行对照，不增加材料。真实Provider调用0，没有读取真实凭据、创建正式角色或保存真实聊天；额度仍30/200、剩170。当前尚未获得新增人格投影用途许可。

## 交付

复用既有两阶段试验与FrozenAttemptRun，增加封闭的人格投影变体及专用Adapter。旧基线计划、DTO/policy/wire保持原样，新旧计划版本和Adapter不能互用。人格表达由已落盘合法规划重建，core/personality原样保留；支持ID、资料摘要和路径留本地，不进模型。

两个实际计划已经prepare，均无started目录：

| 条件 | plan digest | 次数上限 |
| --- | --- | --- |
| 旧两阶段high基线 | `90f6e31ac854f1eee0867fdd96f931b2b2a4c7b8e3dc1c3d67484cbde041e824` | 12 |
| 常驻核心＋人格候选 | `44cbc4b1f02682ea9948b9751bf406c8a81e1d26b44d4f7315a469742e79dfb4` | 12 |

本地根目录分别为`.local_indexes/eromanga-sensei/s99/baseline`与`personality`。共同cases SHA为`43711c9c0a624c44c1a13d6a1876508b843e672fb93021c868d18dac9e1cf327`。操作人按基线→人格串行执行，任一失败即停止整个对照，不开启另一条件；不会声称已有账户级总预算锁。

`s99/exact-outbound-preview.json`包含12份实际规划body和12份明确标记的表达派生示例，SHA `19934b0c06abb955b957ce96175cd629bdc642a4e45449004d2f071a64446c2b`。示例使用固定空fact_refs，只用于检查常驻资料，不是模型规划/台词或真实审计。最大规划wire为13801字节；字节不是计费token。

## 已核行为

默认prepare零发送；错误/旧approved digest拒绝，真实凭据仅在阶段claim之后按原槽惰性解析。人格侧文件在各次调用前检查摘要。每阶段先claim，技术/裁决/审计失败停计划；超时保留unknown，重启读取完整可验证结果，缺失/损坏不重发，也不补发表达。响应推理被丢弃，不进入审计；仍是required候选，未增加语义正确保证。

主窗口已审最终代码主要差异、12份规划wire与派生示例，核对high/4096/30秒/no temperature、无外发引用/ID字段；重新prepare旧基线仍完全同digest。实现复用已有副作用/恢复契约；[研究适用性与官方资料](../../research/2026-09-26-personality-behavior-grounding.md)已记录，未新增依赖或通用工作流框架。

28个唯一用例通过：新人格trial13项＋旧兼容15项。包含完整六题/12阶段、旧standard/high完整流程、未知投递恢复、8种旧缓存损坏、不匹配Adapter/计划拒绝、规划后sidecar变更阻止表达、惰性凭据与未获准零发送；补跑不重复计数。git diff --check通过，无运行残留。主窗口直接复核，受线程总额限制未新增独立reviewer；这些检查不构成真实人物效果结论。

## 下一动作

向用户交付[可审用途方案](../../plans/personality-behavior-trial.md)及本地人格底稿，确认新增人格输入用途后即可按固定计划执行，首轮最多24次从剩余170扣。之后同材料/用途与总额度内的常规验证不逐批询问；新资料、真实历史、生活或通知仍不在本次范围。
