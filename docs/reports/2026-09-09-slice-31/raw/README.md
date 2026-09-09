# Slice-31 后台证据

使用新建的独立合成Avery根 dsa-s31-live-20260909；旧林柚登记缺失的预检没有启动产品或发出Provider请求。本目录不声称恢复旧链。

- fixed：e9f5aa9，head1–8。
- restart：同代码重开，head9–15。
- final：438d003重开，head16–21，head21为保留的重叠名称失败。
- boundary：b8ddb2d重开，head22–25，直接复验head21并有完整名正对照。
- turn JSON为提交消息及完整HTTP响应；before/after来自/api/state，UUID已脱敏。
- memory JSONL从公开Memory DTO记录实际active/selected内容、action、reply种类/文本及已授权recent_dialogue，不记录key、内部ID或思维，不改变请求或调用。HTTP ok不等于回答准确。
- 三个comparison文件检查同一新根重启前后五个用户投影字段一致。

诊断脚本在本地忽略的.scratch/s31_server.py与.scratch/s31_live.py，服务已关闭。稳定回归为tests/test_memory_subject_selection.py，经过ApplicationFacade。
