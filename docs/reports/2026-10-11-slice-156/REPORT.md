# S156：未见钟表店长距、多跨度与自然指称

## 真实首验终态：初稿choice截断，后八步未验

准备工程b4bde47已提交推送后，唯一冻结新场景实际2首次/0retry：首聊天完成并零模型选E1；第2初稿choice HTTP200但finish=length、final空、completion4096/reasoning计数4096，返回 original-whole-response-truncated/FailedClosed。审计1complete+1failed-closed、完整canonical仅2 Publication（chat、select），活动版本0/无plan，初稿资格未评分。没有长稿或多跨度修订发表；后8自然指称、明确修订、条件、三话题、重开新choice、末答全未执行。

首聊天仍关联文字构图，但请求已明确“你自己选”及三个位置，回复重复让用户决定两点，并把“三段”误称“三步”；自然/推进仅1。具体主体/镜头/光线、自然指称的适当澄清、exact其他照旧、出窗后实际选择及末答忠实度均未验，不能用Fake或首聊天替代。此样本确认choice响应截断及空final，尚未证明布局要求或服务内部行为是根因；不读取/保存reasoning正文，也不改预算/policy或首题补发。

| 层次 | 结论与限制 |
| --- | --- |
| 工程 | 6 Fake/冻结check/双复核通过，原界限不变；实际首失败拒绝发表，无部分plan或虚假修订；raw/request/audit/canonical核验一致。 |
| 场景 | 2/10已执行，首技术失败有界结束；初稿资格及后8未验，0retry/0抽下一稿/0取最佳样本。 |
| 人物 | 首接话可读相关但重复确认，评分1；初稿/长距修改/指称/后续取舍/最新回复全未验。 |

只读核两条audit状态/request digest、首次final SHA、首聊天normalized digest/原文等于canonical、精确active同identity/Timeline、完整2 Publication/record digest、唯一E1及无plan；核验0模型/凭据/业务写入。[完整证据](../../../.artifacts/s156/clock-first/metadata.json)、[空初稿final](../../../.artifacts/s156/clock-first/finals/initial-activity.json)、[只读核验](../../../.artifacts/s156/clock-first/readonly-verification.json)、[人物评阅](../../../.artifacts/s156/clock-first/content-review.json)均本机保存，公开仅[事实摘要](live-summary.json)。没有改首SCENE、初稿格式、标准、源码/Provider或资格。

S155全部28文件与10保留源码hash与开工基线完全相同，九目标首稿仍2次原有界终态。8796只读复核同scope/health正确/空聊天/活动0，未向其POST或重开，不接/发/覆盖草稿。本轮有界收口，提交推送新失败与未验事实；下一必要为在同用途独立定位choice最终正文预算/协议，再冻结另一个未见场景补真实长距与指称，不能重发或改判本题，不能通过扩大旧界限制造通过。

## 准备：保九目标终态，冻结独立新场景

2026-10-11用户明确新场景补验/保首稿终态/不重跑不放宽/授权内自主提交推送。开工 main/HEAD=a12aeeb，fetch后 origin/main同值，tracked干净；只读8796 health正确/空聊天/活动0。九目标S155保持2请求、bounded-end-initial-content-not-met、后8未执行，未重发或改判。

新[SCENE](../../experiments/s156/SCENE.md)为原创钟表维修店“刻廊→时隅”，十条首次消息与root/nonce/scene SHA独立冻结。138字首消息要求三个具体构图段落、每段约90–110字、各段开头用店名一次，主题/关注点用简称；角色仍自行决定主体、物件、镜头、光线和关注。这是首次结果前明确的格式输入，不是事后削目标、程序固定plan或把旧九目标稿改到可表示；实际全部目标继续计数与验证，≤8/≤4/160/240/唯一不重叠/完整expectedplan门槛不变。

新 `run_s156_long_reference.py` 复用S155完整门槛/首失败/原nonce/reopen逻辑，只替换场景变量；生产src、Provider policy/protocol/资格/Grant/slot、旧runner与8796均不改。Fake只检查新helper实际Facade链和边界终止，不能替代人物效果。开工定向核一手研究及未采用方案见[证据](../../research/2026-10-11-s156-new-long-reference.md)；无新依赖/代码许可或外发用途。

记录[S155保留基线](../../../.artifacts/s156/baseline-preservation.json)：旧首景28个文件与10个保留源码hash，包含全部初稿、final/preview/audit/canonical/metadata，后续只读核完全相同。新root `.artifacts/s156/clock-first` 此时不存在，0真实新请求。首验须必要Fake/只读复核及工程提交推送完成后执行，每step首次一次/≤10/0retry/首技术或保护失败终态，首门槛未达或合法无目标效果有界结束。

自然指称范围是未给新名时适当询问/建议待确认并保现稿，然后用户明确所有旧词→新词后自动准确修订；不称通用指称自动解析。真实同字段多段effect、具体澄清、出窗后实际新选择及末答忠实度仍待本轮首次；长期/隔日/分享/实用户人物评价不属于这一个场景证明。

工程准备收口：[helper日志](../../../.artifacts/s156/test-helper-first.log) 6 passed / 80.76秒，覆盖新Facade十步及真实同字段分段模拟、首技术失败、短稿资格不足、合法chat/clarify未effect终止、九目标首稿不可修剪或继续；[纯check](../../../.artifacts/s156/runner-check-first.log)核scene/grant0模型/凭据/product open。两路只读复核无问题，独立核旧28文件/10源码hash全一致；未改生产src/旧runner/原scene/policy/协议或原保护。此刻clock-first仍不存在/0实际新请求，工程commit/push后才执行首次链；模拟正文不能证明人物澄清或真实长距效果。
