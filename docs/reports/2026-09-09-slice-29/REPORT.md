# Slice-29：连续对话参考对照与首个改进闭环

状态：completed。基线 `b41874c` / `dogfood-s28`；实现 `c63c24c`、最终代码 `28707c9`，build `dogfood-s29`。**540 passed in 468.01s**。本切片完成有词面关联的旧记忆候选截断修复，未宣称连续对话或最终表达普遍稳定。

## 问题与根因

ApplicationFacade 对照先保存星砂手册计划，再保存其他资料夹记录，关闭/重开后换一种说法询问计划。19 条干扰记录通过，20 条失败：canonical 查询仍有 active 原计划，但 Memory proposal 未收到它。首次 `tests/test_memory_retrieval.py` 为 1 failed in 13.55s；加入阈值和持久化检查后 1 failed、1 passed in 23.32s。失败定位在进入模型之前的固定最近 20 条截断，而非恢复丢失或该次模型选择失败。

原 Slice-28 两条记录情况下的模型错选不是同一原因，本切片不宣称解决它。

## 参考与实施

一手机制对照见 [REFERENCES.md](REFERENCES.md)。学习 Letta 的存储/上下文分层、SillyTavern 的匹配先于预算、Graphiti 的词面检索路径。本次实际复用现有 Python SQLite 内的 FTS5/BM25，不安装完整外部 Agent 框架，也不自行实现 BM25 公式。[SQLite FTS5 官方说明](https://www.sqlite.org/fts5.html#the_bm25_function)明确越好的匹配分数越小；本地 SQLite 3.52.0 已检查 FTS5 可用。Context7 SQLite 检索结果不充分，补查官方原文。

`memory_retrieval` 只在 active 超过 20 条时对当前已读的最多 100 条历史中的 active 内容作词面排序；原文不改写，最多 20 条入 proposal，最多 5 条已选内容入 reply。中文双字片段和英文/数字词元不依赖题材词表；MATCH 参数受控、确定性打破同分并限制 128 个查询词元，内存连接当轮关闭。未匹配的槽位按最近顺序补齐。FTS 错误与无匹配分开，所属 Memory FailedClosed，不取消其他能力；本地完整库存与 exact 状态不依赖排序成功。

## 真实后台对照

仅使用原授权合成林柚根 `C:\Users\30252\AppData\Local\Temp\dsa-ux-retest-20260908`；先验证 display_name 与隔离 authority。production DesktopState/HTTP `{text}` / ApplicationFacade / 原 Windows Credential Manager DeepSeek 用途；无新增远端模型、embedding、凭据操作或正式身份访问。

- 基线进程加载未修改代码：head56 保存星砂计划，head57–76 提交 20 条资料夹事实；这些轮次的实际 accepted/失败以 raw 为准，不能仅用 HTTP ok 证明记忆创建。
- head77 原问题回答「抱歉，当前没有可用于回答这个问题的记忆或知识。」；快照包含 25 条 active，原计划仍 active。见 raw/baseline-after.json 与 raw/baseline-turn-21.json。
- 停止基线服务，同一根以修复代码重开。head78 同一问题回答「你之前提到计划周六整理星砂手册。」；head79 改述回答「你之前说的是周六整理星砂手册。」。见 raw/fixed-turn-00.json 与 raw/fixed-turn-01.json。
- head80–81 两轮无关短诗清出两轮近期窗口，head82 未参与设计的「星砂那本东西，我当时想哪天动手？」正确回答周六。head83 更正为周日，canonical 原计划成为 superseded；head84–85 再以无关短诗清出近期窗口，head86 正确回答周日。见 raw/continuity-*.json。
- 重启前后 display_name、build_id、memories、conversation_history_status 和 conversation_history 完全一致，见 raw/restart-comparison.json。head87–88 清出近期窗口后，head89「再说说星砂的安排，当时定的是哪天？」回答「这个我不清楚，当时定的具体日期没有记录。你记得是周日吗？」。当轮说明召回了 1 条，记录仍 active；**这是表达不稳定，不能计为完整承接成功**。现有日志仅说明选中数量，不将其夸大为对选中对象的独立逐字核验。
- head90 显式遗忘更正后原文，head91 普通询问未复述旧安排，head92 正常答出独立资料夹 archive-19。遗忘确认与实际 forgotten 状态一致，旧 superseded 版本未复活。见 raw/forget-*.json。
- 28707c9 最终代码重开后，五个投影字段仍与遗忘后完全一致。head93 问纸张颜色，正确答出当前最近 20 条以外的浅绿色偏好；head94 再问星砂安排，未复述旧内容，但回答「还没定具体时间。你希望安排在什么时候？」——**未复述是披露边界通过，断言“还没定”则不是可确认事实，不算表达通过**。见 raw/final-*.json。
- 共 39 次真实后台追加（head56–94），分别保留基线、修复与最终回归修复的阶段，不拼成单版本成功率。最终服务经本地停止标记关闭，执行 `server_close` / `state.close` 并返回 CLOSED，运行数据保留。

## Standards

独立规范轴对 c63c24c 初审未报问题。全量回归随后发现姓名查询回退被非必要改动破坏：原姓名在候选窗口外时，改为检查全库存会放行未收到姓名的 Provider，出现「你之前没有告诉过我你的名字」。既有 test_name_query_outside_reply_window_cannot_claim_no_historical_report 独立复现为 1 failed、22 passed in 51.67s。28707c9 撤回该改动，并让 FTS 错误在姓名判断之前作为所属 Memory FailedClosed。规范轴增量复核无新增问题，并明确纠正初审遗漏；不把静态审查当作完整验证。

## Spec

独立需求轴确认修复针对已证实的窗口截断，不扩大 Provider 字段、调用、历史用途或引入题材规则。28707c9 增量复核无新增问题；head89 保留为最终表达失败，不计入完整连续对话成功。

## 自动化与剩余边界

- 首轮相关测试 30 passed in 50.56s；新增控制场景曾有一处测试文案断言误写，改正后 8 passed in 113.46s。这不是生产代码故障。第一次全量运行发现上述真实姓名回归后停止，不记为通过；28707c9 相关回归 31 passed in 162.06s，最终全量 **540 passed in 468.01s**。命令：`.venv/bin/python.exe -m pytest -q --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s29-final-full`。
- Interface 对照覆盖 19/20 阈值、改述、更正并重启、逻辑遗忘、未决/不可读披露、无匹配最近窗口回退、FTS 故障与独立 Knowledge 成功及本地清单/exact 状态。生产代码不修改 DeepSeek 提示、字段或序列化方法。
- 本地最多 100 条历史、无共同词元、单字中文或范围外字符、纯指代、候选窗口内模型错选、reply 最多 5 条的选择与表达仍可能失败。排序不是通用语义理解；head89 的具体日期/星期解释不稳定、head94 从不可用误说尚未安排均需后续独立体验任务，不为这两句再加特例。未实现统一表达层、Reflection、Agency、主动消息或角色文风升级。
- 本轮只有合成林柚身份的真实连续/重启验收，没有在正式身份或其他 Provider 上重复，也不声称本次新增了跨身份长链真实验证。已有身份隔离行为由全量回归守护。
