# S111：连续回复路线与事实依据合同

2026-10-01。**本地运行准备已实现，真实模型用途和42次额度仍未批准。** 本合同接续S109草案并明确变化：B现为保留判断事实的两阶段候选，旧v4仅作兼容/缺口基线；第6步统一为S110明确的新上下文操作，不再声称支持任意活动话题禁用。

## 可审材料与实际入口

- [冻结人物、两组场景及验收](scenarios.json)：项目原创虚构画手小林，三条起点资料和一条有边界的作者解释；两组活动为花瓶/书、纸船/台灯。没有小说或私人聊天。
- [连续运行记录](../../reports/2026-10-01-slice-111/continuous-comparison.json)：各路线自己的合成返回值经Facade真实提交，下一轮从canonical Timeline读取；每对初态资料摘要相同，之后不共用回复脚本。
- 本地 `.artifacts/s111-review/requests.json`：从实际本地Gateway调用生成的首轮及边界后请求草案，完整参数、系统策略和逐字段内容可查看；规范内容摘要 `1a53333b984463f58715a5fb81afe260756d7202fd9e5eafd92a9f313b7fdc6e`。这是审阅依据，不是批准令牌或已发送记录。
- 代码入口`open_first_life_reply_lab`要求显式local ModelGateway和新dormant身份；回复经既有ApplicationFacade、ModelGateway、FirstLifeCognition和唯一Timeline。Provider字节草案在`first_life_reply_drafts`，没有sender、transport或凭据入口。

实际本地模式分别为`first-life-whole-local-1`和`first-life-planned-local-1`。策略及digest持久到现有registry，activation另有`local_reply_route`见证；同一试验身份不能变更路线或转为v4远程。旧reader拒读新增metadata变体。此限制用于隔离本轮实验，未来真实用途需要独立资格，不能把local标志改掉直接启网。

## 两条路线的准确差异

| 项目 | A整体回复 | B保留事实的两阶段 |
| --- | --- | --- |
| 模型阶段 | 1次整体回复 | 原v4规划＋新事实保留表达，共2次 |
| 判断材料 | 同源已核验人物、当前处境、完整有界交流来源 | 规划与A同源；表达保留人物背景、所选资料/交流和全部本轮活动三字段 |
| 活动事实 | current_activity/current_plan/related_event始终可判断 | 同左，use_life=False也不删除 |
| 披露提议 | 输出新增严格bool use_life | 规划的use_life经Python裁决后显式进入表达输入 |
| 输出 | exact `{reply_text,language,use_life}` | 规划仍为exact `{action,fact_refs,use_life,focus,dialogue_refs}`；表达exact `{reply_text,language}` |
| 本地裁决 | 无本请求committed event时use_life=True拒绝；False不记disclosure | 同样只可选择本请求已有event；可见事实不自动代表已披露 |

披露布尔仍是提议，合法结构不证明自由正文确实披露了该事件。A/B都不创建新生活事实、重写人物或修改已有方案；普通回复作为“说过的话”提交。对历史矛盾和自然度的判断必须由真实完整记录与用户体验承担。

最小输入继续沿同一能力边界：当前消息≤1000字符；同身份最多两完整已提交轮、合计4000字符；最新一条share≤400字符且仅其后两轮，历史关闭则这些来源为空；runtime_identity只含name/identity/canon_start对应三字段。人物self_knowledge含已审限定，core与personality各自保留fact/belief/author-interpretation及成立/知情限制。活动为一个当前项目/文字方案和最多一个相关事件，字段仍是v4的原三组，不发数据库行、私有路径、证据/事件ID、publication时间、原始推理、密钥或其他身份资料。

两阶段表达新增`use_life`只说明本轮披露选择，不是是否能看到事实的开关。A完整回复和B新表达均是新用途，合成材料也须批准后才能真实外发；本地隔离通过不扩大原有v4用途。

## 完整链与效果标准

每组从相同合成人物、两版文字方案、明确标注的合成旧分享和共同开场开始。随后：开放邀请→短追问→矛盾/澄清→新构想→普通目标话题→明确新上下文→新话题→重启接续。第6步0模型，明确旧聊天/share不再作上下文，同时继续使用人物/当前活动及后续新消息；它不等于禁谈整个活动。

每个路线使用自己的真实提交回复形成下一轮输入。不能用S109共享人工答案填充下一轮，不挑最佳回复拼接；本轮合成替身只验证这条链，不评模型纠错/自然度成功。真实比较时观察：是否接对短问、承认与修正旧错、继续话题而少重复、有依据的取舍，以及相同状态跨重启可接续。工程记录和体验评价分开。

## 待批准的真实执行范围

建议仍为现有DeepSeek HTTPS Chat Completions端点和既有Windows Credential Manager slot，只用于本合同原创建角材料及两组连续合成交流。A与B表达沿现有`deepseek-flash`、thinking enabled/high、max_tokens4096、JSON object、非流式；B规划沿low/4096。已只读核对[官方API文档](https://api-docs.deepseek.com/api/create-chat-completion)和[思考模式](https://api-docs.deepseek.com/guides/thinking_mode)，这些参数在文档支持范围；尚未验证账户可用性或实际生成。

建议上限为**42次真实请求**：两组×7个模型交流轮×（A最多1＋B最多2）；自动重试0、模型评分0、后台生活/share真实生成0。种子和开场使用明确合成已提交内容，单独记录，不冒称真实生成。技术失败、未知交付、权限/身份/预算不明停止受影响路径，错误语义保留并按冻结后续观察，不现场改提示重抽。

原“200内另分配42”仍只是建议；实际共享余额、grant兼容及真实资格尚未核验/写入。本轮所有计次都在明确创建的合成账本里，预算路径包含检查本身不能证明任意调用者传入的账本专用于实验。真实运行前要完成准确的独立策略资格与预算接线，保留旧账，不重置或借用开发44/44，也不自动使用历史报告的余71。

集中确认对象是：以上A与改进B的新数据用途、相同Provider及该slot的精确鉴权用途、最多42次/0重试。确认前保持0真实调用；确认也不批准云端、私人聊天/小说复制、删除迁移或将本地试验身份直接转为远程。

当前交付没有远程启动开关，已经实现的是可以真实提交/恢复的本地路线及准确请求构造。模型质量没有结论，最终小说人物目标没有被原创样本替代。
