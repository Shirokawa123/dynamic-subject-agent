# S142：持续生活、主动分享与两轮接话的准确用途审阅

2026-10-06，真实已审材料的新独立LOCAL资格已完成五支合成闭环，31个LOCAL ModelTask；0远程请求、0凭据读取。三用途的只读builder预览均逐值等于实际任务，普通回复另核完整canonical轮/head及原输出。准确对象在[review.json](review.json)冻结，当前basis为`153bc6e8bfe766a8cfc7a852b4ae295ea7acf8e2e20ea960d2ad7d7a91e08f06`；尚未批准，也没有可执行远程grant。最终独立复核和整体接纳由主窗口承接。

独立复核要求LOCAL运行在非预期失败时保留已完成证据，已增逐阶段/分支/任务的安全检查点：摘要仅status/error_type/累计计数/任务SHA及已完成安全步骤，精确Task只写自有本机partial文件；main/finally保存failed-partial，不重建canonical或回显异常正文。检查点I/O失败不会改变ModelResult/业务返回，失败或未核检查点不能冻结新审阅。仅用仓库合成fixture核过此前完成步骤、下一断言失败与I/O失败，0产品/模型调用。新basis绑定两个helper SHA；31已通过样本不重跑，全部旧字段逐项保持。原basis `c6317b6f048340e290c7942ef6e3890e9d29543dc2a6716a4049d9e5cd1bc5c3`的[完整审阅对象](review.previous-c6317b6f048340e290c7942ef6e3890e9d29543dc2a6716a4049d9e5cd1bc5c3.json)和原wire均保留。

请求在新的独立开发root使用同已审纱雾30项事实/4项作者解释的最小人物投影，沿DeepSeek及现有Windows Credential Manager `(deepseek, default)` slot，批准以下三个用途。旧root、S105/S108用途和历史200预算均不成为本项新授权；不上传原书或sealed整包，不迁移用户分支。

| 用途与触发 | 精确输入 | 输出与本地裁决 |
| --- | --- | --- |
| 应用开启时下一活动机会 | 同S141 `background`、`shared_experience:{label:"E1",quote≤400}|null`、`current_activity:{phase,allowed_actions}`、`current_plan:{subject≤160,composition≤800,focus≤400}|null` | 同S141 `action,plan,reason_code,basis_refs,decision_note≤160`；Python核阶段、实际差异和完整依赖后提交，note仅本地，不再外发 |
| 对合资格新结果单独考虑分享 | `background`、同一有效E1或null、`activity_result:{action,plan}`；仅新提交start/revise实际文字版本 | exact `share`布尔、`reply_text≤400`、`language:"zh"`；true正文非空，false正文空；真假均canonical考虑一次，true才产生助手-origin分享，不伪用户轮 |
| 主动普通聊天与分享后的接话 | 原`turn/background/exchange/evidence`，current≤1000、history开时最多2完整committed轮≤4000；原E1及`activity_result:{kind,plan}|null`，另加`latest_share:{text≤400}|null` | exact `reply_text≤1200/language:"zh"`；仅最新一条已提交分享，且仅其head后2完整成功ordinary轮可提供；history可关，第三轮连同S1派生完整旧回复及传递lineage一起过滤 |

在线累计900秒仅提供一次choice机会，默认暂停/分享关闭；15秒短租、同窗口owner、离线与重启不补算。显式模拟入口清楚标记。分享是独立stage，不在一个动作偷偷追加第二请求。每stage最多1请求、0自动重试；技术失败暂停并needs_attention，不造事件，明确检查恢复后只用新nonce执行新机会。首次成功普通交流解除未回抑制；`answered`不定义两轮窗口，失败/查询/重启不耗窗，历史关闭时已成功的普通轮仍计数。

日上限是UTC8最多2条已提交true新话题，不是模型调用预算或必发配额；false不耗新话题。暂停/关分享/无新eligible结果或无变化/已考虑/未回复/日满/needs_attention/source控制未闭合时，share在模型前0调用。停用或替换来源、history-off、cutoff及权限变化完整过滤依赖计划、结果、分享与旧回复；canonical原记录保留。source控制先隔离进行中的旧候选，coldprepared重核来源/权限/day/head，原nonce查读或恢复不重生成，未知或损坏保持FailedClosed。不开系统通知、后台系统服务、离线生活、云、effect、新Provider/credential用途、人格重写或Reflection。

完整最终样本留本机专有资源：`%LOCALAPPDATA%/DynamicSubjectAgent/living-activity-development/s142/local-review-20261006-2/`下的`exact-unsent-previews.json`、`metadata.json`、原`exact-unsent-wire-previews.json`及新basis的`exact-unsent-wire-previews-checkpoint-1.json`。LOCAL预览canonical SHA为`00b011d740761a5d089a2a8bbcb19d780156686afe91efaa3295624de8e6143f`，contract SHA为`5751e5ed7e56f3b1451c683fb96bcc762ca783219f7df72e352458b61930f4b4`。仓库仅保metadata、policy与助手原创场景；首准备资源`local-review-20261006-1`和专用TEMP均保留，旧样本不足以冻结本次S1过滤合同。

主链通过90次×10秒**注入的模拟monotonic**检验online API的900秒边界，未证明真实15分钟在线；副链使用显式simulation动作。所有模型输出是固定合成文字，前两接话刻意逐字回声分享以检查第三轮不会绕回。五支覆盖true/false、重启同nonce、未回/无变化0share调用、source停用全过滤、暂停/失败/明确恢复、UTC8两true上限。工程流转不证明人物选择、自然度或真实生活体验。

纯`living_remote_request_preview`直接序列化这31个实际LOCAL任务，不另编请求：两条messages、HTTPS `https://api.deepseek.com/chat/completions`、`deepseek-flash`、max_tokens4096、thinking enabled、reasoning_effort high、JSON object、非stream、30秒超时。不是Provider strict-schema；条件与闭集由Python裁决。choice/share/reply policy SHA依次为`7737b3fdacad632414d0f09a29ef1a49f36fa0cea0c17277e7643bb1703ebc4f`、`eaa2d6877df8edf70282e599049c4faef6b6cf50dfa823c564190e47d4823f4d`、`ded5c6dd9b06f57ada4f42461c992cea43f9ad328388c4b89e86df4880cf7f00`；各wire摘要逐项保存在review.json。

`PendingLivingActivityGrant`只允许unapproved；`UnapprovedLivingActivityAdapter`没有transport或credential入口，31项均typed拒绝`living-activity-use-unapproved`。LOCAL composition在registry前严格拒remote gateway，旧Whole sender亦不能获得新用途。批准后仍须建立绑定本basis的单独可执行资格和用途审计，Pending/LOCAL不会升级。

获批后按[固定首场景](scenarios.json)新空分支、无E1、明确开关、一次标记模拟机会→有真实新文字方案才独立share→重启0模型→若true则两次接话及第三次换题，最多5请求作为首轮场景停止条件，非长期调用预算。首技术失败全停，合理defer/无eligible计划或share=false保留并结束，不挑样本补抽。真实人物效果须由此首结果另行评估；普通“继续”不代替本项准确新增用途批准。
