# S151：输出预算诊断与未见自然反馈接续

## 新首景终态：截断未再出现，但准确修订与完整闭环未通过

固定新首景实际6首次/0retry，5audit complete/1failed-closed、6canonical为来源chat/零模型select/自选v1/自动F修订v2/含糊chat/条件chat。六响应均finish stop，completion依次128、1838（choice其中1533reasoning）、185、122、121、220；feedback reasoning细分未提供，不能伪0。没有截断或空final；第6首话题虽有388字完整JSON正文，但缺language，Python严格拒绝并未发表。当前v2保留；按首技术失败结束，不补字段、不重试、不另抽同题。

后4步全部未执行：topic-gap-2、topic-gap-3、过两轮窗/真重开后的新choice、当前结果接话。第一次换题仅有未发表候选，不把它算成已成功换题；真实过窗/重开/继续活动仍未验证。四格诊断＋首景合计10新真实请求，0retry；旧S1504首/首失败保持。预算干预在这些新样本未触发旧length路径，不能据单场景宣称永不截断或完整功能修好。

人物效果按原冻结语义标准：初始选择右侧原创抱膝少女、中景/稍低四分之三视点，以小可爱体块与空间重量为关注，明确左侧大片干净留白（2）；一句新反馈自动把左侧换浅灰细纹理（目标2），无复制plan或手选F。但是第二项edit将“只用一条极淡的地平线和一点渐变光暗示空间…”换成仅留地平线/纹理暗示空间，删了用户明确要求照旧的渐变光（保留约束0）。回复先说“光线都不动”又说“渐变光去掉”，存在可核矛盾（准确表达0）；自己的审美理由不能代替该修改的授权。没有改标准以接受它，也没有补发纠正直到通过。不能把这个语义越界归因于关闭thinking：本新场景没有相同完整链的原模式对照，原模式诊断也有字段遗漏。

含糊“那个再调一下”虽intent=chat，正文具体询问纹理/地平线/主体等对象，没有猜改版本（澄清作用2）；但其复述仍沿此前“光线照旧/渐变去掉”的矛盾，不能当内容全准。未来拥挤书店条件没有修改v2，明确仅是假设（条件2）。普通表达较长、像构图咨询，初回复仍让用户先列主体而后续活动才自行选择（自然性1）；材料不支持的习惯/成图/离线新活动未补造，但不能证明长期自身生活。

只读核验6audit的请求/全部首次final hash、5完整DTO output digest、active独立资格/同identity Timeline、6Publication全链和record digest、E1＋F源闭包、失败零发表一致；确认渐变光删除确实已进canonical。核验0模型/0credential，仅SQLite URI mode=ro，不对失败重新调用/改变状态。证据：[新首景metadata](../../../.artifacts/s151/new-scene-first/metadata.json)、[只读核验](../../../.artifacts/s151/new-scene-first/readonly-verification.json)、[初稿](../../../.artifacts/s151/new-scene-first/finals/initial-activity.json)、[唯一反馈及实际edits](../../../.artifacts/s151/new-scene-first/finals/natural-correction.json)、[含糊接话](../../../.artifacts/s151/new-scene-first/finals/ambiguous-feedback.json)、[条件接话](../../../.artifacts/s151/new-scene-first/finals/conditional-feedback.json)、[第6缺字段首final](../../../.artifacts/s151/new-scene-first/finals/topic-gap-1.json)。previews/audit/canonical-history同目录保全，公开仅[live-summary](live-summary.json)。

本轮有界诊断结束。保留direct-final作为独立开发选项，限制结论为本次反馈输出预算路径改善，不推广为已完整通过的人物能力/默认入口。真实“准确修订→换题→继续”目标未达，工程字段/序列化通过不补人物效果。剩余两具体缺口：固定language常量仍要求模型重复生成而会漏；局部before/after验证只能保证跨度外文字不变，不能证明跨度内没有删掉用户要求保留的概念。下一必要交付应减少无必要的协议生成字段、明确修订保护范围并拒绝未请求变化，再用另一个未见场景补验后续选择；不把它扩成W1/记忆重构或放宽结构接纳。无新服务、调度、旧入口/草稿/数据迁移或新用途。

## 四格真实诊断收口

工程5a5b1b2/1b30d3a已push后固定4格全执行，4真实首次/0retry/0人物Publication，旧source权限/canonical/WAL字节不变，S1504首/失败保持。结果：A-baseline stop/1246completion（1062reasoning）/302final字符，但缺language，结构拒绝；A-direct stop/126completion/231final，完整chat不改；B-direct stop/99completion/240final，完整revise，唯一将远景列车灯暖白→中性白；B-baseline stop/380completion（258reasoning）/267final，完整。3complete/1schema失败，全部首次正文/audit保本机。

没有格发生length，不能说重现了旧截断或证明全部内部根因；旧记录已定位响应阶段预算耗满，新mode去掉该feedback思考开销路径是技术干预，不放宽失败接受。Direct两格reasoning_tokens未提供，记录None而非0。B真实patch只变目标片段、主体/视点/其他光路不变；A只是当前条件意见，没有已印刷/成图声称，语义均2/完整。两格技术/语义门槛满足，第一次不可覆盖eligibility绑定manifest/metadata/final SHA，允许冻结的未见空间纹理场景；不因少样本宣称稳定性。

证据：[四格metadata](../../../.artifacts/s151/four-cell-first-live/metadata.json)、[已核冻结来源](../../../.artifacts/s151/four-cell-first-live/manifest.json)、[首次eligibility](../../../.artifacts/s151/four-cell-first-live/eligibility.json)、[A新模式正文](../../../.artifacts/s151/four-cell-first-live/finals/A-direct-final.json)、[B新模式正文](../../../.artifacts/s151/four-cell-first-live/finals/B-direct-final.json)。固定诊断到此结束，不为强复现增加题目；新场景尚未请求。

第一次0请求预览冻结后，复核要求添加readiness/evaluate门槛，执行器hash因此变化。旧four-cell-first准备目录保留且0attempt/0call；在新four-cell-first-live仅重新作0请求准备，消息/场景/协议不改。不是补发或抽样重试，最终执行器commit/push后才产生首次4格请求。

## 工程阶段

基线5522160与fetch后main一致，tracked干净、全部旧成果保留。用户已要求同用途截断诊断/修复与新场景，自主提交推送；准确数据用途仍为S150 f09dd24a…518f6两项，同Sagiri30/4/DeepSeek/default Windows slot。唯一[S151](../../slices/slice-151-output-budget-new-continuity.md)，旧S1504首次/首失败/nonce/正文/审阅/SCENE/runner保持，不重发原问题。

已证层：S150捕获字段本来是空final、4096completion、生产parser在finish length分支拒绝，未发表；不是Publication丢失有效正文。保存字段的安全envelope重建仍得到response-truncated，不是原HTTP包重放；不能从旧未记录的reasoning细分推断模型内部情况。官方Context7及原文说明预算/模式/JSON与metadata见[调研](../../research/2026-10-11-s151-output-budget.md)。思考耗满是主要待验假设，真实因果靠新固定对照补证。

独立direct-final候选只改变feedback的thinking enabled/high→disabled/无effort，policy/JSON/4K/投影/来源/单请求/0retry/裁决不变；choice仍原high。新version/开发Grant/literal protocol pin/audit/publication key/root隔离，复用feedback-live family/schema8，不升级旧S150资格。capture新增finish/final_chars/可选reasoning_tokens标量，不读存CoT或凭据；missing用量为None，不伪0。原length继续FailedClosed，未引入补答、截断接受或重试。

9预算/metadata行为＋12 S150LIVE必要兼容共21通过；新场景3（完整10步/失败停/缺diagnostic门槛0opening0请求）及旧执行器4必要兼容最终相关检查通过。首测试因缺basetemp父目录在fixture前报错（1通过/1setup error）保留；下一轮13通过/1失败暴露metadata默认字段缺失掩盖凭据unavailable，修复后21通过。原问题重建仅本地，不违反用户禁止原题重抽的要求；技能通用原题重跑/环境变量凭据建议未采用。

两独立复核接纳；规格复核指出候选→新场景缺readiness门槛，已绑定不可覆盖的eligible/A、B语义2分、四格manifest/metadata/首次final SHA、两direct完整stop和0Publication，发送前以及每stage核验；源/诊断变动拒绝。基线已有的reviewed_character_chat_status遗漏feedback audit分派记收尾，非本轮新增、当前脚本不依赖，不扩权修整仓/旧UI。

新固定[4格诊断](../../experiments/s151/DIAGNOSTIC.md)只读旧有效v2的两条从未发送消息preview，关闭owner后冻结权限/canonical/WAL，0原分支调用/业务发表。原角色source3成功与失败保持。[新空间纹理场景](../../experiments/s151/SCENE.md)先冻结，10首次/0retry/首技术失败停，实际纹理修订→条件/指称→3话题→过窗/真重开→新choice→结果；按语义修改目标允许相关focus表述同步修正，非目标细节逐字保留，不沿用错误的全focus不变标准。

此工程阶段未证明真实预算干预或人物效果；先commit/push，随后执行固定4格并写真实结果；只有候选技术和语义接纳才推进新首景。完整初次结果/失败只本机，公开摘要，不提交人物资料全文、raw wire或CoT。无新服务、通知、调度、旧8793/8795/草稿操作或迁移。
