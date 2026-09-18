# Slice-50：逐次确认的本地文本成品

状态：已完成，见[报告](../reports/2026-09-18-slice-50/REPORT.md)；基线bc4f18d / dogfood-s49。沿用D-026与自主连续推进授权。

用户结果：新建身份中，accepted文字任务拥有本地正文后可查看精确目标文件与完整正文，逐次确认保存；只在应用目录新建UTF-8文本，不覆盖、不删除、不联网执行。最终完成/失败可查询，重复批准和进程中断不重复创建。正文保存不调用Provider；文字起草仍使用已有聊天创作，由用户明确选择/粘贴成品后保存，本切片不新增生成用途。

先完成新Timeline schema v2及独立effect runtime contract，只作用新binding，不迁移旧身份。v1读取/聊天/任务保留；旧身份effect明确unavailable。同一canonical SQLite中的Publication提交真实eligible/ref/ready，追加receipt及独立count/head摘要验证删除/错序；不得继续伪报false/empty/unavailable。receipt在其intent序列之后生效，pending intent后不得出现新Publication；admit和resume/freeze前均先经授权worker恢复。读接口、导出、治理冷启动不执行文件。

复用既有Admission、Timeline/Host单writer、Facade、任务面板；借鉴AWS transactional outbox的先提交后执行，LangGraph的恢复重验。Context7查询失败，已查Python os.link/fsync与微软CreateHardLink官方文档；暂存exclusive+flush/fsync后hardlink新建，同名仅samefile且exact bytes才可恢复成功，否则保留冲突文件并失败。部分暂存不清理、不重写。不引入依赖/第二store。

验收经Facade覆盖preview无写、stale/跨身份/取消拒绝、零模型批准、重复确认、Publication前中断无文件、文件后receipt前恢复、同名不同所有权/部分写失败、receipt篡改/缺失失败关闭、v1兼容和导出含receipt。桌面实际脚本验证确认与身份/草稿隔离，隔离生产后台及全量回归；报告commit/push后自主进入最终v1混合验收。任务书外问题记报告，不扩权。
