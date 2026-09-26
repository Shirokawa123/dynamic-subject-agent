# Slice-98：人格底稿及本地两阶段接入

已交付本地可读人格底稿、六项原作研究和能够贯穿规划/表达的只读人格候选流程。原v9没有改动，没有Provider调用、正式建角或真实聊天。200次额度仍用30、剩170。

## 用户能检查的结果

本地`.local_indexes/eromanga-sensei/s98/personality-review.md`说明四组候选：创作和交流的意义、渠道差异、审美取舍与具体能力局限、对参与设计角色的投入。每组写明情境、选择、表达及外推界限，不当作完整人格或事实批准。公开博客调侃和跨对象表达差异另留作者说明，后锚场景不倒灌为起点经历。

Sol核查第一卷及既有回忆依据，形成六项结论和21处短摘录。主窗口独立读关键博客归属、既往工作争执及线上体验回忆窗口；逐项重算文件/成员/段落/摘录摘要并核对子串，21处一致。这证明定位完整性，不自动证明性格解释正确。心理学/成熟项目调研与取舍见[开工依据](../../research/2026-09-26-personality-behavior-grounding.md)；只借机制，无新增依赖。

## 实际接入

沿Facade.preview/propose_character_reply，新增local-only Producer读取独立sidecar并绑定同一v9、人物和起点。解释只能引用当前known认识，携author-interpretation与belief支持标记；不混入fact_refs。常驻core从已核组织核心取得，无组织时保留identity，与人格同时进入两个新typed envelope。旧DTO、policy与远程Adapter不变，旧wire拒绝新类型。没有新聊天数据库、人格状态机、模型任务种类或第三次调用。

预览默认零调用，显式demo才用固定本地替身。缺sidecar为unavailable，篡改/非法/超限为FailedClosed，不丢失一半人格后继续。候选始终required/persisted=false：测试故意让表达器输出无据近期活动，结果仍只是待核候选，不能宣称语义保护已完成。当前采用本轮已验证快照，不声称跨进程即时撤回无竞态。

## 验证与限制

16项人格行为检查通过，2项旧规划/远程完整流程兼容通过，共18个唯一用例；补跑1项不重复计数。主窗口检查最终差异并修正有界读取和缺失状态问题，git diff --check通过；工具线程总额限制下没有新上下文独立reviewer。

实际v9/人格底稿通过Facade导出：四条core、四条人格；六个情景各跑基线与新流程的固定替身，空fact_refs下仍完整保留core/personality。最大规划JSON为11465字节。固定替身只是接线检查，真实语义结果尚未运行。

关键本地指纹：人格sidecar `e1340c3ba240190e530d969166e37b2740c911a521582900112df58a5d8e85c8`；两阶段本地对照包 `5e24debba6fe578f0582144412385e99b662aec0a1f8291e0ba13e0ce8ffab54`。本地全文及实验输入不上传Git。

下一步准备[24次有界真实对照](../../plans/personality-behavior-trial.md)的冻结执行路径，让确认针对可立即执行的具体输入；尚不请求运行，也不沿用S97旧basis封存包含人格的新定义。
