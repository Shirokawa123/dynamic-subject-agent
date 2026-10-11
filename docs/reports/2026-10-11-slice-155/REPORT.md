# S155：独立入口与真实长距、自然指称首验

## 真实首验终态：初稿九个目标，有界结束

工程 e747f83 已提交推送后，冻结首次新场景实际只执行2步/2请求/0retry，2 audit complete、3 canonical（初次聊天、零模型E1选定、初稿choice），仅v1。两个 final 均 finish=stop，无截断或技术失败；completion 121/1921，choice reasoning1428、feedback细分null不伪0。

首接话 intent=clarify，重复询问已经明确允许自选的构图内容/外观，未生成文字方案或冒称成图；自然性1。第二步真实 choice=start，初稿有速写少女、画具、白兔形笔袋、纸灯、灰猫、水景，前中远景及镜头/光线/具体关注均可见，内容要素2。composition实际6处“汀舍”、首末目标跨度291>160，是实际长距初稿；但subject1+composition6+focus2共9目标，超出先定≤8的独立frame门槛，requested_frame返回None。人工初稿内容分2不能覆盖资格分0；执行器零模型grade-long后终态 bounded-end-initial-content-not-met。

没有削目标、改正文、提高8目标/4项/160/240界限或重抽初稿。后8步（自然指称、明确修订、未来条件、三个新话题、重开新choice、结果接话）全部未执行。没有实际多跨度修订发表、v2/F1或保名新版本；**长距完整修订与自然指称人物效果仍未验证**，不能把首长稿或工程通过称为该目标完成。

| 层次 | 结果与限制 |
| --- | --- |
| 工程 | 独立入口/恢复/HTTP Fake/门槛检查与双复核通过，工程已push。真实2请求raw/audit/canonical一致；首门槛拒绝资格后未补发。8796仍未批/未运行。 |
| 场景 | 2/10执行，长稿首门槛未达；后8步未验，0retry/skip取好样本。九目标是冻结首稿门槛未达，不是模型JSON失败或永久产品取舍。 |
| 人物 | 初稿具体主体、镜头、光线、关注要素2；初次澄清有重复确认，自然性1。自然指称澄清、准确修订、换题后选择和最新结果忠实度全未验。 |

只读核 audit/request/raw SHA/normalized digest、同identity/Timeline资格、完整3 Publication链和record digest、唯一聊天正文等于首次原reply、v1及E1依赖一致；0模型/凭据/业务写入。两首次原文/预览/metadata/audit/canonical全保本机，见[只读核验](../../../.artifacts/s155/long-first/readonly-verification.json)、[完整metadata](../../../.artifacts/s155/long-first/metadata.json)、[首初稿](../../../.artifacts/s155/long-first/finals/initial-activity.json)。公开仅[事实摘要](live-summary.json)。旧S150/151/152/153失败仍各4/6/3/3次原终态，未重发或改判；所有工程/核验失败保留。

本轮首验按冻结条件终态收口，待[8796准确启动动作](../../experiments/s155/ENTRY-START.md)集中确认。下一必要验证仍为保持原保护下、未见且可表示的真实长距完整更正→自然指称澄清→换题后新选择；不能复跑本次初稿至过或把入口启动当人物验收。新用途仍需具体审阅，本次没有新增出站用途。

## 换窗恢复与工程准备

从本仓文件和实际状态恢复，没有读取旧聊天历史。2026-10-11 本地 main/HEAD 为 5516561，fetch 后 origin/main 同值；S155 tracked 差异和相关 untracked 仍在，全部旧临时目录、草稿及失败保留，没有 reset、清理或重建。

断线前最终日志 [test-final.log](../../../.artifacts/s155/test-final.log) 已结束：23 passed / 199.99 秒；恢复时没有可见 Python/pytest 进程，8796 没有监听。没有重复运行这批测试。首次 HTTP 异步回执误断言、Unknown 场景对 history 状态的误断言、helper fixture UTF-8 读取错误，以及初始化核验脚本首个错误表名均保存在本轮 artifacts，不能视为真实模型失败，也未删除。最终页面脚本与 PowerShell 启动器语法检查通过，未运行启动器。

新 `NaturalFeedbackChatAdapter` 复用原聊天/nonce/历史/来源/手动活动 Adapter，只调用 Facade；参考内容与活动预览使用实际 natural-feedback 投影，展示有效 F1、E1 和当前 plan，页面草稿/动作缓存使用独立 S155 scope。新的 entry 由 production composition 与 Authority 校验 sealed exact active pointer；新 root 不复制旧内容，部分 root/错误 pointer 保留并拒绝，Unknown 和已核失败关闭历史仍可零请求重开/查读。共享接缝仅新增纯身份资格验证入口，旧资格与协议不升级。

断线前 [初始化回执](../../../.artifacts/s155/prepare-review-receipt.json) 与 prepare 日志一致：空聊天、activity revision=0、audit=0、0模型/0凭据读取，状态 prepared-not-started。恢复后未再次初始化。新的 8796 常驻服务尚未批准或启动；具体动作见 [ENTRY-START](../../experiments/s155/ENTRY-START.md)。

工程验证为临时自有 HTTP/Fake 和入口/执行器行为证据：消息→选 E1→活动→长距明确替换→3话题→重开→新活动、原 nonce 查读、历史关闭投影与独立草稿键。它不证明真实人物效果或实用户 UI 体验。本轮没有新依赖或外部代码；入口取舍及研究适用性见 [开工证据](../../research/2026-10-11-s155-entry-clarification.md)。

只读双复核指出并接纳两类修正：页面不再因 `basis_refs` 无 E1 而否认实际 F 反馈原话；执行器技术通过后仍核场景门槛，合法 chat/clarify 未修订、后续 keep/rework/defer 未形成新方案、后续新方案未保新名均有界结束，不补抽。含糊/条件/普通话题保护当前方案，明确更正核 exact 完整 frame；pending 原 nonce 也可通过 inspect 零请求查读。标准先定的 SCENE 未改。

恢复增量 helper 验证 8 passed / 142.81 秒；新增测试重复块已保留原文件于 artifacts 并去重，最终定义内容等价。只读入口核验首先因核验进程未固定 TEMP 而返回 reviewed-policy-binding-invalid，同脚本提升宿主读取权限仍失败，排除沙箱因素；按初始化/启动器原 `TEMP/TMP=.artifacts` 后通过：same pointer、完整 canonical 空链、audit=0、0模型/凭据/业务写入/重建。此诊断失败与脚本保留，未更改封存 policy；启动需使用准确启动器环境。回执见 [只读恢复核验](../../../.artifacts/s155/entry-recovery-readonly.json)。

## 首验安排与当前限制

[SCENE](../../experiments/s155/SCENE.md) 已先定：汀舍→栖舍，初稿同 composition 首末目标跨度必须 >160、全部目标≤8且能按原≤4/160/240/唯一不重叠界限完整表示；短稿/不采纳/不可表示有界结束，不抽长稿。自然含糊不误执行，再明确全部引文替换；3话题退出近期窗后真重开0请求，再一次实际 choice 和结果接话。每 stage 首次一次、0retry、首技术或保护失败终态，所有 first final 保本机。

最终名字检查逐字段匹配，跨字段拼出新名不能冒充保名；受影响成功十步与该新边界例 2 passed / 67.37 秒，[日志](../../../.artifacts/s155/test-final-name-boundary.log)。新增 helper 共9个唯一用例分8+2两次相关验证（成功例重验一次），不是新增人物效果。两路最终只读复核全部问题关闭；冻结 scene/grant/policy 的 check 通过0模型/凭据/product open，未改 SCENE 的字节或门槛。准确启动机器依据见 [entry-start.json](../../experiments/s155/entry-start.json)。

工程阶段收口时 `.artifacts/s155/long-first` 尚不存在，0实际新请求；工程e747f83推送后才执行首次首验，终态见报告顶部。既有真实模型请求和失败场景未重跑。当前临时覆盖是明确引文替换及含糊澄清，不称通用自然指称自动定位或永久产品限制。
