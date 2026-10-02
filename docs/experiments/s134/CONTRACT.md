# S134本轮范围预览实际验收

2026-10-02。同已批准whole用途、Sagiri30/4、当前文字≤1000、最多2完整轮≤4000、现有DeepSeek/Windows slot，每轮1调用0自动重试；不新增数据用途。沿S132自有新context分支，目前边界revision2、cutoff6，4条已提交聊天保持。S133查看只读，不改变此基线。

只读阶段：当前草稿的范围预览、取消/编辑失效、history-off/on、重复读取与重开均0模型、0Admission/Timeline写入，保草稿与原nonce。UI不显示内部digest或完整system prompt。未决/控制/完整性故障由现有Interface替身验证，不制造真实网络异常。

真实阶段拟两次明确新输入，先预览，再按既有发送路径独立发送；将预览projection_digest与Provider metadata observer中的实际request_digest比对。第一条预期边界后exchange0，第二条只含本段首轮exchange1，旧四轮不外发。预览不能成为发送许可或忽略发送时变化。

开发者输入：

1. 如果只画一张人物头像，你会先确定表情还是光线？我想听听你的选择。
2. 那按你刚选的顺序，如果想让人物显得安静一点，你会先处理哪里？

正文只留canonical，observer只采用既有OriginalWholeObservations白名单，报告只记录摘要/数量/失败和实测结论。空白/失败保留，不自动补发原消息；新输入须明确记录用途和结果，不能删掉失败追成功。旧用户入口/草稿、Provider与credential用途、生活/S1、云、删除迁移与人格关系边界保持。
