# S131：查清原请求结果并安全继续聊

连续十片4/10，2026-10-02。S128–130多次空白/不确定结果保留，S127已修已知失败清nonce留草稿；仍缺无admission的nonce结果查询，服务重启后内存handle丢失只能再走submit，unknown也不能明确放下后开始新轮。交付用户能查清原结果、保留未发送草稿、明确选择安全继续的完整体验。

开工比较与定向一手HTTP/idempotency研究见[证据](../research/2026-10-02-s131-request-recovery-evidence.md)。只有Facade新pure query可查当前identity/Timeline范围内匹配nonce＋原消息指纹的canonical Admission/失败/Publication，不admit、execute、冷恢复、重试或预算claim；not-found、pending、known-terminal、unknown/integrity失败区分。不能将lookup实现为再次submit。

薄入口刷新/重开凭自己保留的request_id/request_text查原结果，不发送草稿或清用户新改文字。unknown明确显示不确定及原尝试保留；用户主动确认放下原尝试后仅清本地旧nonce，下一次明确发送才新请求，绝不自动重发。原已知终态恢复与IME保护保留。

沿同一已批whole数据/Provider/slot和现有schema/Timeline/资格；query是本地现有数据读取，不新增外发用途、人物状态、生活/S1/人格/关系、删除或迁移。默认旧8785服务/用户草稿保持，在独立开发root/后台入口验证。唯一所有者贯通core query接缝，入口另有唯一所有者，接口先协调；必要权限/完整性/0发送/真实重取/草稿恢复验证及独立复核后提交/push。
