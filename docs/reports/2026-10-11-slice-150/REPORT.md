# S150：自然反馈修订有限成立，真实首景因截断终止

## 真实首景终态：一句反馈修订成立，完整接续未通过

工程6ef4be9已commit/push后按冻结首景实际执行4首次/0retry：3audit complete、1failed-closed；4 canonical为普通来源聊天、零模型E1选定、冷主光v1活动、自然反馈v2。第4步“再收一点”HTTP200但final为空，completion_tokens=4096，严格完整响应解析返回original-whole-response-truncated（该码对应finish_reason=length）；未发表、当前版本仍v2。人物是否理解这句含糊反馈无法判断，模型内部耗尽输出预算的原因未确认，未读取/保存raw reasoning。首技术失败已终止，没有补发或另开模型场景。

后续6步全部未执行：条件反馈、3个换题、过近期窗后的真重开/新活动choice、当前结果接话。本次不证明真实换题接续、完整闭环或长期稳定；新实际隔日不在本次范围，旧S149隔日事实保持。无新服务/通知/调度，旧8793/8795及草稿未触及。

实际自然反馈只有原句“主光改暖，冷色只留一点边缘反光，其他照旧”，没有抄旧plan、补主体/视点或手选新来源。模型提出4个实际光照片段替换，Python发表v2并将本条已提交用户原话自动绑定F，保原E1依赖。暖主光、暖白远景灯、暖高光及少量轻微冷色边反光进入方案；站台少女/兔形布偶主体、右侧位置/左轨道留白、视点、轮廓/抱持关注及全部非光照文字保持。自然正文与canonical expression逐字一致，没有成图/离线活动声称。这是一个真实明确反馈的有限效果，不能把局部编辑结构通过当作泛化语义能力。

**标准变化及影响已在第三步请求前说明。** 初稿focus本身写了偏冷主光/冷光，原SCENE要求focus逐字不变会使正确改暖后仍留下旧冷光。原冻结标准未改：实际focus变动，原focus逐字项记0/未达，不能声称原标准全部通过。[ASSESSMENT-NOTE](../../experiments/s150/ASSESSMENT-NOTE.md)在反馈输出前另定只允许光照文字同步修正、其他内容逐字保留的语义标准，结果在该项记2。没有把补充送给模型、改题/策略/协议/投影/上限或重试；两套分数并列于[live-summary](live-summary.json)。原首回复偏长且像构图说明（自然性1），自身选择确有站台/布偶与可爱轮廓的具体关注，但不足以证明长期自有生活。

只读核验：4audit逐请求digest/首次final一致，3完整输出的output digest一致；active authority/同profile与Timeline、4Publication全链/record digest/原文来源、E1＋F依赖及v2当前结果一致，第4失败无Publication。最初blocked transport factory inspect的自动审批超时，未执行；改用SQLite URI mode=ro，不打开应用/transport/credential，完成全链核验，新增模型/凭据均0。不是绕过风险拒绝，也未修改失败。完整证据均本机：

- [真实metadata](../../../.artifacts/s150/real-first/metadata.json)、[只读核验](../../../.artifacts/s150/real-first/readonly-verification.json)。
- [初始来源首次全文](../../../.artifacts/s150/real-first/finals/initial-source.json)、[初稿全文](../../../.artifacts/s150/real-first/finals/initial-activity.json)、[唯一自然反馈全文](../../../.artifacts/s150/real-first/finals/natural-correction.json)、[第4步原空final](../../../.artifacts/s150/real-first/finals/ambiguous-feedback.json)。每步previews目录保全部准确body，audit保metadata；canonical-history保已提交双方正文，未将空白写成台词。

目前可查看真实一次反馈的修订正文、逐字差异和v2方案；现有聊天页尚未接入S150，完整“自然反馈→换题→继续活动”只在LOCAL/Fake完成，真实链未完成。本轮诊断到此结束。下一必要工作是处理联合结构化任务的响应截断，先作有界输出预算/协议诊断，再用未见过的场景补验真实换题后选择；现有原首失败保留，不复跑至通过。W1继续来源优先/可选，无新增永久限制或记忆扩建前置。

## 2026-10-11准确批准后的LIVE工程阶段

用户已明确“批准这两项，继续真实验收”，绑定原basis f09dd24a…518f6；原review.json/SCENE保持冻结unapproved历史对象，批准事实由direction/current与ApprovedNaturalFeedbackGrant承接。新增feedback-live authority/Manifest/精确publication key，保持独立schema8/新root，不转换旧LOCAL或8795。两用途保持原策略/协议/数据上限、最小资料/DeepSeek/default Windows slot；每次claim和同线程一次consume都由sealed/canonical/权限重建，严格最终JSON校验及原Publication裁决，audit与正文/密钥分开保存。

12项新LIVE Fake检查通过；首次UNKNOWN用例原断言错误地要求活动投影可用，按旧UNKNOWN未知前缀拒读合同纠正，状态/不重发未放宽。执行器及6项必要旧兼容选集首1序列化失败/8通过，修正history DTO转plain后，执行器4项全部通过（全10步、reserved仅inspect、首技术失败不重试、关闭失败禁止下一步）。独立发送边界与规格复核接纳；发现finally关闭错误会留下ready的P2，已改为保存first-stage-failed并返回非0、回归通过。冻结review/scene、runner、辅助与执行源pins，在开始首景前核验；此阶段0实际remote/0credential，真实场景尚未执行，不能以Fake通过证明人物效果。

工程阶段按用户要求commit/push后才执行[原SCENE](../../experiments/s150/SCENE.md)。执行器每次只执行下一个固定stage，先持久nonce再arm一次；已有reserved/failed/终态不可补发，只inspect原nonce。初始冷主光按原标准人工读取final后记本地分数，不把评语输入模型；随后自然反馈、歧义/条件、三话题、真重开、一次新choice和当前结果接话。首技术失败终止；所有可提取首次最终正文/预览/wire/canonical保本机。无服务/通知/调度、8793/8795/草稿或源材料变更。

## LOCAL准备阶段历史（以下为批准前事实）

已交付可运行的独立LOCAL闭环：同一已审人物包/同一Timeline，普通消息一句“主光改暖，冷色只留一点边缘反光，其他照旧”原子修订当前方案；三轮换题退出近期窗、真关闭重开零调用后，再实际产生新活动版本并接话当前结果。这里的意图、编辑和正文由明确标记的合成Adapter给出；当时真实自然理解及人物效果尚未验证、新用途待[准确审阅](../../experiments/s150/REVIEW.md)，不能把LOCAL成功当作LIVE交付。最新批准与真实结果见顶部。

## 实现及权威

基线62cb694，开工fetch后与origin/main一致、tracked干净；全部旧untracked成果保留。最新用户明确继续及自主权已同步[方向](../../plans/character-chat-direction.md)，唯一[S150](../../slices/slice-150-natural-feedback-continuity.md)承接；S149隔日已收口/调度PAUSED，不由它扩权。原8793/8795/root/草稿与冻结S149执行器不操作。

新增natural-feedback-local authority/Manifest/schema8/精确contract/publication key及正常Facade发送路径；复用SharedActivityRecord、ModelGateway、来源过滤和原子Publication，没有第二store或整仓重构。模型仅提议chat/clarify/revise、正文和最多4个field/逐字before/after；Python核当前有效方案、活动版本、冻结basis/权限、原文唯一匹配、不重叠和实际差异，在副本应用后提交，未修改文字保持原样。chat/clarify是活动typed NoOp，技术拒绝是FailedClosed，不把两者混同。

修订保留全部本次实际来源依赖及完整当前用户原话F；不把旧无效plan解封为参考。后续choice/接话读取同一有效plan及最新有效反馈，只最近F1出站；来源停用/更换/history-off/cutoff过滤依赖和派生旧轮。独立新方案不再投影不支持它的旧反馈。最多8条来源/4编辑/before160/after240属于本轮准备合同，不是永久产品限制。没有永久偏好、人格/关系写入或Reflection。

## 工程验证

- 首轮17项有16失败/1旧接口通过，缺新runtime合同闭集接线；诊断并修复，原目录保留。随后17项新接口全部通过。合成fixture字段错误（current_message位于turn内、LifeEvent字段kind）也按实际合同纠正。
- 新行为及必要原话/W1/S149动作合同兼容选集：59通过/1断言失败。该断言错误地要求history-off隐藏完全不依赖聊天的独立方案；正确要求是不发表本次反馈候选、原独立方案和版本不变，单项纠正后通过。不是缩小隐私标准或放宽派生方案规则。
- 最终自然反馈21项通过；独立复核发现一个P2：“独立方案→后选E1→自然修订”漏记实际提供的E1依赖。改为本次reply_dependencies加新F，新增此顺序Facade回归；修复后该项、完整闭环及停用过滤3项通过。最终62个不同选集案例的全部最终相关检查通过（新22、旧40），未在最后重跑整仓或重复已无变化的40旧兼容。
- 范围/规格与核心/状态两个独立复核完成；P2关闭，无未解决actionable问题。reviewers没有写入、产品请求、factory或读取凭据/私人包。工程保证的是片段、版本、依赖、状态与恢复，不能判断模型是否正确理解反馈。

## 场景执行与原始证据

已审真实人物包经Facade核审basis后，建立新的独立LOCAL资源。首`local-loop-first`到初始活动→准确局部反馈→澄清→条件话题，共4合成请求/4提交；gap1幂等键过短在模型和发表前被拒绝，后三换题/重开/新活动/结果接话未执行。目录与4个完整synthetic final、purewire保留，没有补发原Timeline。

只读原nonce lookup返回malformed-idempotency-key；诊断脚本起初的submit被自动审批拒绝，原因是可能写实验Timeline且应直接读既有证据。移除submit，改只读lookup/预览，完成诊断。后续修复LOCAL执行器键长度并在独立工程资源`local-loop-validated`完整验证，保持同一句反馈/同一合成标准，没有调真实模型题目或覆盖首失败。

`local-loop-validated`完成9个LOCAL合成请求/9 canonical发表、真重开0请求、9个Pending Adapter逐个拒绝、6项检查全部true：preview等于执行输入、精确局部修改、反馈退出两轮窗、同身份/历史重开零模型、真正后续活动版本变化、结果接话拿到当前plan。活动版本1→2→3，新活动修改focus并保持纠正后的composition。澄清/条件/无关消息未改活动版本；普通chat仍有真实聊天Publication，与活动NoOp分开。

全部正文、逐请求LOCAL preview/unsent body、状态、canonical历史、metadata和日志在本机：

- [首失败metadata](../../../.artifacts/s150/local-loop-first/metadata.json)、[首失败所有任务入口](../../../.artifacts/s150/local-loop-first/tasks/01.json)。
- [完成metadata](../../../.artifacts/s150/local-loop-validated/metadata.json)、[完整canonical聊天](../../../.artifacts/s150/local-loop-validated/canonical-history.json)、[逐请求任务入口](../../../.artifacts/s150/local-loop-validated/tasks/01.json)。tasks/01–09逐个保全文及wire，LOCAL字样保持。
- [旧兼容/首断言日志](../../../.artifacts/s150/pytest-final.log)、[最终21新行为](../../../.artifacts/s150/pytest-feedback-final.log)、[复核修复3项](../../../.artifacts/s150/pytest-review-fix.log)。最早控制台失败与对应pytest-first/diagnose目录均保留。
- 公开仅[summary](summary.json)和审阅合同/哈希，不提交私人角色全文或实际background/wire；`.artifacts`保持ignored。

## 人物效果、未执行和下一步

新真实Provider请求0、credential读取0；没有执行新的真实人物场景、真实自然反馈语义评分、真实新活动内容或新的隔日。合成Adapter按字符串预设intent/编辑，不能证明含糊指称识别、条件相关性、自由反馈准确、语气自然、人物自有关注或长期稳定。S149真实明确来源/隔日的有限通过保留，不用它替代本次验证。

用户现在可以查看或运行LOCAL接口演示/证据，看到局部变化和活动版本；8795实际聊天仍是原获批S149能力，没有接入此新用途。下一步值得做的是按已先定[真实首次场景](../../experiments/s150/SCENE.md)，让DeepSeek首次判断自然反馈并核实际部分修订与过窗后的新选择；这是区分工程闭环与人物效果所缺的证据。

集中待批仅两项准确新用途：自然反馈/普通接话一次联合提议，以及活动choice增加有效F1。basis `f09dd24a840082d19dea10c0e0f8cce3bf8b31764d3f151be20f0c86d3e518f6`。方案、代码、协议、字段、上限、源pins、首次≤10/0retry/首技术失败结束和纯wire均已可审；Pending无transport/resolver，LOCAL factory在registry前拒remote。批准后还要精确LIVE资格、claim/consume/audit与最终Publication核验接线，不把目前准备夸成已有sender。无新长期服务、通知、调度、迁移、人格重写或Reflection。
