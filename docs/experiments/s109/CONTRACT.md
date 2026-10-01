# S109：已交付离线包与待审真实对照合同

2026-10-01。**离线准备已获批准；本文件不授予任何真实调用或新用途。** 用户明确未批准行动方案中的48次。本轮实现没有远程执行入口，也未读真实凭据、小说、私聊或运行账本。

## 已经可以运行和审查

```powershell
.venv/bin/python.exe scripts/s109_route_preview.py --output .artifacts/s109-my-review
```

输出目录必须全新，拒绝覆盖既有快照。`README.md`供阅读；`requests.json`包含两类各八轮的逐字段A/B请求、关闭历史对照、显式活动限制候选、来源/请求摘要、冻结场景预期和阻断标记。输入来自本目录[scenarios.json](scenarios.json)及脚本内固定原创人物，不接收真实目录/任意人物资产/credential参数。

场景摘要为 `8ae8721bb9073f5be095c73b872521dec68d3baed75c5a87c3d6b26c9a1dbef7`。完整准备摘要在生成包的 `review_basis`；它覆盖策略、具体请求与场景，后续修改需产生新审阅依据。摘要是版本绑定，不是批准令牌。

两场景分别是花瓶/书的方案版本冲突、纸船文字构图/图片完成与用户误述。每条八轮：开放邀请→短追问→矛盾/澄清→新构想→普通目标话题→限制当前活动→无关话题→重建后接续。以完整链判定接话、纠错、取舍和不相关特点保持，不设固定正确台词。原创样本只用于机制检查，最终小说人物与自动建角仍按PRODUCT验收。

### 证据分层

1. **当前B请求复用。** 规划及表达wire直接由v4纯构造器生成；表达依据脚本给定的合法选择。没有把另写的“两阶段”冒称production B。
2. **同源请求准备。** A与B规划拿到相同人物、处境与历史，A删除规划指令后直接生成整体回复候选。共享人工回复/选择用于固定下一轮输入，属于teacher-forced准备；真实对照必须各自承接本路线实际回复，不能继续套脚本。
3. **真实本地机制。** `test_s109_continuous_baseline.py`通过现有Facade、独立identity、原子Timeline及预算代码提交合成活动/分享/聊天，并关闭再重开产品核对恢复。没有第二聊天store。当前B在“目标”控制处阻断及其后持续失败是保留的产品缺口，测试通过表示成功复现缺口。
4. **候选控制。** `candidate_common_scope`是两路线共用的本地实验参数，限制后同时移除活动三字段及所有限制前交流；新话题可以建立新窗口。第6轮不准备任何出站请求，第7轮无旧话，第8轮仅带第7轮完整交流。该候选没有production权威、自然语言识别或canonical控制记录；JSON往返只证明可重建，不能冒称真正重启持久化。

## 精确的数据及模型配置建议（未批准）

目的地建议仍为现有DeepSeek HTTPS聊天端点，凭据建议复用现有Windows Credential Manager DeepSeek slot，仅作该端点Bearer鉴权。**A是新用途，合成材料也不能凭既有聊天批准自动外发。** 当前不新建或迁移凭据、不启用其他Provider。真实执行前须重新核实官方模型/参数支持及现有账本，不以当前离线构造器证明服务端可用。

| 字段/阶段 | A一次整体回复 | B现行v4两阶段 |
| --- | --- | --- |
| 人物 | 同源`runtime_identity {subject_name,subject_identity,canon_start}`；一个核心条目、两个已审知识条目、一条作者解释 | 规划相同；表达按现行选择最多2个知识条目，核心/作者解释保持 |
| 知识限定 | 条目`{dimension,content,kind,basis,event_scope,knowledge_scope}`，知识条目另有本请求F label | 同左，Python原样复制选中条目 |
| 作者解释 | `{title,interpretation,when,choice,expression,limits,basis,support_includes_belief}`，只使用脚本内那一条 | 相同；解释不是世界事实 |
| 当前话与相识 | `conversation {self_knowledge,stage_description,encounter,disclosure,current_message}`；当前话≤1000字符 | 规划同源并含固定policy；表达为`selected_facts,action,stage_description,encounter,disclosure,current_message,policy` |
| 交流 | `dialogue_sources [{label,speaker,text,kind}]`，最多2完整轮/4000字符＋最新1条share/400字符且仅其后两轮；`history_enabled,has_prior_committed_exchange` | 规划相同；表达只复制最多2项至`selected_dialogue`，保留说话者与kind |
| 活动 | `current_activity {project_kind,phase,revision,allowed_actions}` | 规划相同；表达由`use_life`决定保留或清空 |
| 当前文字方案 | `current_plan {subject,composition,focus}`或null | 同上 |
| 最多一个事件 | `related_event {kind,revision,summary,differences,simulated,content_kind}`；diff为`{field,before,after}` | 同上；既有v4使用范围不扩大 |
| 输出 | exact `{reply_text,language}`，中文非空≤1200字符，不产生状态变化 | 规划exact `{action,fact_refs,use_life,focus,dialogue_refs}`；Python裁决后表达输出同A |
| 配置 | 沿用当前B表达：`deepseek-flash`、thinking enabled/high、max_tokens4096、JSON object、stream false | 当前规划low/4096、表达high/4096，同模型；这项差异透明保留，不宣称所有阶段同思考档 |

字段原值、完整policy和每轮JSON均在可运行预览中；不发送来源路径、小说原文、证据/数据库/事件ID、publication timestamp、真实用户画像、其他身份、未提交草稿、原始推理或密钥。未来实际历史只来自各隔离身份的canonical Timeline，审阅输出只限合成试验内容，不自动复制用户原私聊进报告/Git。

现行B的`use_life=False`会保留旧话而丢活动事实；A保留的是获准可用的事实，不是“已知就可外发”。一旦候选scope限制活动，**A与B共同**清除activity/plan/event和限制前对话。关闭历史则仅移除交流/分享，不能当作活动限制。一般人物核心可能含受限事项时必须先确定依赖，不能照搬本合成样本“核心总可保留”。

独立复核实际复现的限制：**限制后新用户消息或新历史若重新描述受限方案，该文本仍会进入候选请求。** 当前原型没有判定这是重新授权、继续限制还是待澄清，也没有处理模型自己在新回复中重述的情况。因此第7–8轮的通过仅覆盖冻结的无关安全话题，不是通用话题禁用；不能接入真实外发。真实接入前须明确新输入/派生内容的使用语义及依赖裁决，该缺口保留为验收反例。

## 预算、停止规则与尚未接入的工程

建议先把共同前置控制接入同一原子Timeline及授权revision，再启动真实比较。当前范围内离线实现/验证无需新增调用批准；production控制类型、权限撤回/恢复、A的独立Gateway任务/版本绑定和共享预算接线仍须实施，不能用本JSON当运行授权。此工程缺口不会通过批准额度自动消失。

原建议48次仍未批准。按现在每条链第6轮明确本地控制、其余7轮模型交流计算，**建议真实上限改为42次：两类×7轮×（A最多1＋B最多2）**；48不作为备用额度。自动重试0、模型评分0；实际少用不补齐，不启动后台life/share调用，初始活动/分享使用合成已提交种子。没有新种子生成费用。

若批准，建议在既有总200授权内另追加独立S109阶段上限42，而不是把旧开发44直接改常量或重建账本。执行前核验真实剩余额度≥所需上限、所有读取器兼容、场景/用途/版本绑定一致；未知交付计尝试，不退款。S108报告的129/200只是历史事实，本轮没有把余71当作已分配给S109。前置不成立就0调用停止。

技术失败、权限/预算不明、身份不符、静默丢写停止受影响链并保留全部记录；普通语义错误保留并继续后续冻结问题，不改提示重抽。重新试验需另列变更、预算和依据。真实结果另记每阶段延迟、调用/用量、原始回复、来源及提交结果，用户评判完整交流；人工脚本成功不评为模型成功。

## 集中待确认项与推荐

- **新模型数据用途：** 是否批准以上原创合成场景的A整体回复用途及A/B在明确限制前后按表外发；若只批准用途、不批准调用，继续保持0真实调用。
- **真实额度及鉴权用途：** 共同前置控制/恢复离线接通后，是否批准总200内独立S109最多42次、0自动重试，并复用现有DeepSeek slot做该精确实验鉴权。建议到该工程门槛达成再启用，不现在消耗预算。
- **云端：** 本轮建议暂不纳入，不申请区域/费用/secret或部署授权；手机入口可在交流路线有结果后并行推进。已有云端评估保持候选性质。

没有需要批准的删除或迁移；旧数据、身份、预算、服务与窗口没有被改动。待审项属于用户本轮明确要求单独确认的新用途/调用/凭据边界，不是技术方案被升级为永久限制。
