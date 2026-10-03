# S138：普通纠错接续与空白分层定位

2026-10-02开工，2026-10-03接续。源修复已通过最终受影响验证与独立只读复核并提交/push `98964e1`；首次真实链在首轮上游纯空白正文处停止，五步人物链未完成。空白已定位到原HTTP响应正文层，服务内部成因未知；不补抽，立即进入S139本地核心闭环。

## 已证问题与修复边界

最新main80e2276经Facade生产接缝复现“正常聊→指出说错→澄清→换题→重启续聊”：仅首轮进入fake wire，其余四轮均为`original-whole-history-unverified`。初始10.72秒红结果见[BASELINE](BASELINE.md)；两层counterfactual7.12秒证明只改当前判断不足，旧失败前缀会再次阻断。原失败记录保持，不改写为成功。

whole改用独立的出站范围判断。普通纠错、措辞讨论、引用及明确过去转述不撤销聊天许可；真正停止使用/撤回当前不外发，随后普通话仅使用安全cutoff之后的窗口。明确不支持的保存/记忆/目标操作在Admission前返回unavailable，不生成会堵住交流的坏记录。有限本地语法不声称能理解任意自然语言意图。

旧失败只有terminal、已知stage/code、完整frozen四项basis与canonical后继证据都成立才允许向前接续。旧普通误拦/cascade保留原合法交流窗口；真实撤回及已知reply失败保持安全截断。pending、unfrozen、未知或传输结果不明、损坏记录继续关闭。未修改旧v1/FirstLife默认控制、Provider字段/策略、schema或资格；不迁移用户数据。

## 工程证据

接口验证覆盖五步链、旧误拦/cascade原failure rows不变、真实撤回当前0wire与后续cutoff、普通讨论和unsupported执行区分，以及unknown/pending/corrupt/unfrozen保持关闭。最终复核指出两种实际隐私漏判：把既有聊天发给模型的明确禁止、撤回字面引文但引号未闭合；现已按动作/对象结构修复，未闭合的明确控制返回独立unresolved并持续关闭，不假装可以安全跳过。

2026-10-03验证：correction/context完整18项105.19秒通过；复核修复后correction完整10项58.08秒通过；最后补充同根transfer未闭引号后，unclosed三参数3项12.81秒通过（8项未选）。这些是重叠的增量检查，不累计为独立用例总数；最终只读复核无剩余发现，零模型边界探针重跑通过。三次开工setup失败分别为PYTHONPATH、默认临时目录权限和非临时实验root限制，未冒称产品逻辑失败或成功。

已完成的兼容检查包括旧v1近期历史控制、FirstLife分享控制、原whole contract/policy/key/projection字节黄金与scope preview；14项37.98秒通过。主修复与S132/S127受影响接口组11项71.58秒通过，另S132其余10场景通过；此处是修改前最后反例复核之前的工程结果，收口时补最终结果，不累加为互不重叠的总数。

## 真实链及空白证据

2026-10-03在唯一自有s138开发root执行[五步验收消息](../../experiments/s138/chains.json)，同已审人物/DeepSeek/Windows slot/1000字主动文字/可关闭两整轮4000字。第一轮即`original-whole-response-content-empty`，按预先固定规则停链，1请求/0重试/0提交，whole共享账59→60。没有为凑完整五步重新建分支或补抽；真实纠错及重启续聊未验成，工程五步链不冒充实聊结果。正式8788与用户草稿不动，自有失败分支保留。

[原边界metadata](correction-metadata.json)显示HTTP200、finish=stop、单choice且无重复语义键；`content`为字符串，94字符、strip后0，因此是纯空白正文而不是缺字段/null，也不是JSON内部空reply。reasoning只记存在/183字符长度，usage为prompt2457/completion219/total2676、reasoning_tokens124；未读取为替代正文，未存内容。没有另一个final/refusal/tool-call正文。Facade同轮无expression，canonical0→0，未知服务内部触发原因，不能从stop或token数推断成功。

分层观察复用原Transport返回bytes而不改请求或响应，只记存在性、类型、长度、闭集finish/usage、最终reply摘要。raw纯空白、JSON内空reply及有效最终正文可区分，重复语义键有独立标志；不存HTTP body、reasoning值、任意error或凭据。此次1次已定位原响应纯空白，排除重复键覆盖、本地JSON解析丢失非空reply和最终字段误选；没有非空真实回复可比较最终摘要，不宣称另两层的所有情况均已真实验证。按预先上限/停止条件结束诊断，不增加无区分力的调用。开工证据与官方来源见[研究记录](../../research/2026-10-02-s138-correction-and-empty-evidence.md)。

## 立即承接核心闭环

修复及有限诊断阶段收口，立即切换[S139](../../slices/slice-139-shared-experience-activity-loop.md)。[设计合同](../../plans/shared-experience-activity-loop.md)和[三支场景候选](../../experiments/s139/scenarios.json)已准备：先完整LOCAL接口/prepared/源依赖过滤/准确投影，再集中确认新Provider用途；不继续扩辅助功能，不以待审方案声称核心闭环已经实现。源实施/测试与实际QA/文档分别唯一所有者，复核只读；本轮返工来自两个明确隐私反例及同根未闭引号，不用工程结果包装未完成的实聊。

后续启用事实：2026-10-03 S139本地阶段收口后，原8788入口在同root/同身份/业务记录不变、0模型下隐藏恢复，已加载包含本修复的f09eddd源码；未操作或发送用户草稿。见[S139恢复结果](../2026-10-03-slice-139/REPORT.md)。这不补写本片首轮空白，也不代表五步人物链后来通过。
