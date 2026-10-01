# S113本地等待诊断与开工依据

用户结果：减少消息提交的本地等待，保留完整原子写入、恢复和发送/提交授权检查。S112真实纸船A各轮扣除Provider观测后仍有6.64–10.16秒本地耗时；该数字含本机磁盘/调度等因素，不能凭它断言SQLite或权限校验是全部原因。

假设排序（实施前已向用户说明）：1. 同一权限操作中重复完整资格校验；2. Timeline反复重建完整历史；3. SQLite持久提交/文件系统开销。用明确本地transport、同一Facade/原种子/三条冻结输入复现，不读取用户身份或真实账本，不降低synchronous或伪造状态。

已运行的反馈环：`PYTHONPATH=src;scripts;tests python .artifacts/s113-profile/profile_turn.py .artifacts/s113-profile/before-measured`。三轮均terminal并冷重开核对历史；单轮2.452/2.605/2.599秒（含profiler开销）。只在单一runtime worker串行任务启用cProfile，避免本Python并发profile冲突。早期工具包装冲突和短idempotency key是诊断脚本错误，已纠正，不记为产品故障。

累计worker时间约6.82秒，`_active_chat_record`/完整身份校验45次约3.04秒；同一次`chat_guard→share_guard→runtime_policy/share_authorization`层叠读取。Timeline验证也明显耗时（query_outcome约3.12秒，包含重叠），因此权限优化不能宣称消除全部本地等待。修复预测：同一权限快照只完整读取一次可减少重复调用与耗时，而每次新发送/提交边界仍必须重新读取，外部变化、撤回和损坏仍失败关闭。

来源核对：本仓`local_identity_authority`的registry_lock和prepared ChatAuthorization合同；[SQLite事务官方文档](https://www.sqlite.org/lang_transaction.html)说明读事务提供持续到事务结束的快照、IMMEDIATE主动取得写事务；[SQLite原子提交](https://www.sqlite.org/atomiccommit.html)解释日志及落盘维持崩溃语义。Context7已定位SQLite官方资料但查询无命中，按skill回退上述官方原页。这里只借鉴一次操作使用一致已验证输入；不把Python registry锁冒称跨数据库事务。

采用：把既有策略校验提取为消费本次已验证(state,record,identity)的内部函数，share/chat快照与guard复用一次读取；下一次guard仍全量读，不设跨轮缓存、不按mtime跳过完整性、不改磁盘格式。未采用：关闭同步、把canonical state常驻缓存、重写Timeline历史读取或改WAL；这些超出当前已证实的最小缺口，且可能损害失败语义。不开新依赖/不复制外部源码，无额外许可集成成本。

此为纯工程一致性/性能工作，哲学心理学不解释其因果，故不硬套。验证使用同输入前后耗时、完整提交/重开，以及旧资格/历史撤回/切换与prepared恢复用例；实际用户端和真实Provider延迟仍需后续体验，离线提升不冒充线上数值。

结果：同三轮全量身份读取45→12，保持每次发送/返回/提交的新校验。无profiler的单轮耗时由1.814/1.888/1.962秒变为1.029/0.972/1.013秒，中位数降低约46%；均terminal、冷重开历史相同。旧权限/恢复相关41项通过。以上为本机E盘、纯本地transport的小样本，不能与S112真API/C盘的9–12.9秒直接比较，也不能推算用户端同幅提升。完整数据与可运行诊断脚本见[S113报告](../reports/2026-10-01-slice-113/REPORT.md)；Timeline反复校验的剩余成本保留，不在本片扩改。
