# Slice-29：连续对话参考对照与首个改进闭环

状态：实施及验收中。基线 `b41874c` / `dogfood-s28`；候选 build `dogfood-s29`。不把本报告中的阶段性证据当作最终全量通过。

## 问题与根因

ApplicationFacade 对照先保存星砂手册计划，再保存其他资料夹记录，关闭/重开后换一种说法询问计划。19 条干扰记录通过，20 条失败：canonical 查询仍有 active 原计划，但 Memory proposal 未收到它。首次 `tests/test_memory_retrieval.py` 为 1 failed in 13.55s；加入阈值和持久化检查后 1 failed、1 passed in 23.32s。失败定位在进入模型之前的固定最近 20 条截断，而非恢复丢失或该次模型选择失败。

原 Slice-28 两条记录情况下的模型错选不是同一原因，本切片不宣称解决它。

## 参考与实施

一手机制对照见 [REFERENCES.md](REFERENCES.md)。学习 Letta 的存储/上下文分层、SillyTavern 的匹配先于预算、Graphiti 的词面检索路径。本次实际复用现有 Python SQLite 内的 FTS5/BM25，不安装完整外部 Agent 框架，也不自行实现 BM25 公式。[SQLite FTS5 官方说明](https://www.sqlite.org/fts5.html#the_bm25_function)明确越好的匹配分数越小；本地 SQLite 3.52.0 已检查 FTS5 可用。Context7 SQLite 检索结果不充分，补查官方原文。

`memory_retrieval` 只在 active 超过 20 条时对当前已读的最多 100 条历史中的 active 内容作词面排序；原文不改写，最多 20 条入 proposal，最多 5 条已选内容入 reply。中文双字片段和英文/数字词元不依赖题材词表；MATCH 参数受控、确定性打破同分并限制 128 个查询词元，内存连接当轮关闭。未匹配的槽位按最近顺序补齐。FTS 错误与无匹配分开，所属 Memory FailedClosed，不取消其他能力；本地完整库存与 exact 状态不依赖排序成功。

## 真实后台对照（阶段记录）

仅使用原授权合成林柚根 `C:\Users\30252\AppData\Local\Temp\dsa-ux-retest-20260908`；先验证 display_name 与隔离 authority。production DesktopState/HTTP `{text}` / ApplicationFacade / 原 Windows Credential Manager DeepSeek 用途；无新增远端模型、embedding、凭据操作或正式身份访问。

- 基线进程加载未修改代码：head56 保存星砂计划，head57–76 提交 20 条资料夹事实；这些轮次的实际 accepted/失败以 raw 为准，不能仅用 HTTP ok 证明记忆创建。
- head77 原问题回答「抱歉，当前没有可用于回答这个问题的记忆或知识。」；快照包含 25 条 active，原计划仍 active。见 raw/baseline-after.json 与 raw/baseline-turn-21.json。
- 停止基线服务，同一根以修复代码重开。head78 同一问题回答「你之前提到计划周六整理星砂手册。」；head79 改述回答「你之前说的是周六整理星砂手册。」。见 raw/fixed-turn-00.json 与 raw/fixed-turn-01.json。

## 尚需完成

控制边界回归、更正后与隔离重启真实复验、独立两轴审查、最终全量回归及 commit/push。自然文风、纯指代、无词面重合的同义表达和窗口内模型错选不属于已证明改进。
