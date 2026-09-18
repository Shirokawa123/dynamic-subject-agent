# Slice-49：受控主体任务生命周期

状态：已完成，见[报告](../reports/2026-09-18-slice-49/REPORT.md)。基线fe017f3 / dogfood-s47。用户已明确批准A方案精确Agency用途和本地保存范围，见D-026；自主推进至重大决策或完整v1的授权继续有效。

本切片结果：通过唯一ApplicationFacade和桌面显式任务入口创建、查询、澄清/重新提交、暂缓、取消主体任务，状态由Agency Domain裁决并与同一Timeline原子提交；跨重启与身份隔离成立。Agency模型每次显式请求最多1次，只使用已批准投影。普通聊天和原12类Provider用途不变，任务原始结构不进入聊天历史外发。

复用现有AgencyDomain、ModelGateway、Timeline decision reason、原子提交和恢复，以及上轮核对的暂停/恢复机制，不新建任务store。当前数据库effect硬约束不绕过；本切片不发文件，接受不谎称执行完成。后续独立切片实现生成/审批/真实执行及版本兼容。

Facade正反行为、投影上限/错误输出、重复/取消、发布中断与恢复、两身份隔离；实际后台和全量回归后报告/commit/push。开始前保留此唯一执行书，完成后自主建立下一项。
