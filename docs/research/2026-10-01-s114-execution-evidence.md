# S114开工证据与执行接线

用户结果与已获批准范围见[任务书](../slices/slice-114-approved-candidate-comparison.md)。本轮不再修改语言候选，直接验证S113已审字节在连续实际对话中的效果。开工只读确认S112父账22/42、余20，原manifest为live；旧200/开发44无需使用。

复用[S113交流研究](2026-10-01-s113-dialogue-repair.md)的上下文分组、话语修复及来源区分假设；本次材料/策略没有新增心理机制，因此不扩研究或把结构合法当语言成功。现有A/B typed DTO、Python裁决、Facade/Timeline、原子Publication/恢复、seed闭集和S112一次性发送票据均可直接复用。

新增的工程缺口是“原42父账内，独立候选仅能花本轮18”，以及新资格不能借旧S112/LOCAL身份启用。采用同一SQLite文件内追加grant元数据及stage映射，让父claim与子计次在同一事务提交；分支本地阶段审计仍与真实账分离，半完成保守耗额。依据复用已核对的[SQLite事务](https://www.sqlite.org/lang_transaction.html)与[原子提交](https://www.sqlite.org/atomiccommit.html)官方机制，核对现有CharacterChatBudget源码：原配置/行/head和schema保持，新marker/元数据缺失失败关闭，不重新分配。该工程问题不需要哲学/心理学解释。

新grant固定本轮已核验22终态前缀、批准manifest摘要与18上限；未知交付计次，重启不重铸票据。新策略digest绑定S113候选、协议、方案与资料，真实sender按策略选择精确已审builder；S112旧wire/digest不变。新入口只允许新dormant分支，各模式显式装配；offline仍使用真实transport无法解析的假credential ref，seed不读key。

不采用另开42额度、重置父账、扩开发44、替换用户服务、改变旧策略或加入自动重试。没有新第三方依赖/代码引入或新数据来源；使用标准库与已有接口。验收先做18/42限额与并发/丢失元数据、资格隔离、同源连续重置/重启的离线检查和独立复核，然后仅运行批准的一次四链，保留失败、原文、用量与未解问题。
