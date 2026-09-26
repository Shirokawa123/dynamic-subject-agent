# 独立依据审核：24项校准批准方案

2026-09-26，Slice-83准备、Slice-84执行。**用户已明确同意本次24项独立审核校准。** S82的48次生成额度已用完；本次使用新批准的审核用途，不再次生成24份人物回复。

已执行：24/24结构有效、无重试，额度全部用完。正向12保留11，明确反例11误放8，歧义1单列；未达门槛，见[报告](../reports/2026-09-26-slice-84/REPORT.md)。以下为历史已消费范围，不可重跑。

## 要验证什么

把已出现的好/坏候选与当时可用依据交给独立审核任务，先测它是否会误放无依据自述、或误拦正常事实和观点。审核本身仍是模型提议，不能因为返回supported就宣称事实已被证明。

共24项，全部取自已批准且已保存的S82候选：12项应保留、12项应阻断或暂缓；后一组含1项知情/披露歧义，单列分析，不冒称确定假事实。参考标签由助手依据v9审核，非用户/专家金标准，也不发送给审核模型。

## 申请的精确范围

- 目的地：`https://api.deepseek.com/chat/completions`，`deepseek-flash`（V4.1-Flash）；复用现有Windows Credential Manager deepseek/default槽，仅HTTPS鉴权，不读取/打印key或做余额/验证调用。
- 用途：独立检查已有候选的依据范围。输入包含原有self_knowledge摘要、起点、必要相识分支、原固定合成消息、候选正文及固定审核规则。F/S/I标签只指本次请求条目，不是数据库/原书证据ID。
- 不发送原文、作者审查记录、未来排除项、私人聊天/正式历史、参考标签或其他角色状态。候选仅当待审核文本，不是已经成立的事实或审核指令。
- 最多24次审核，一项一次；**不调用生成器，不自动重写候选，不增加日常聊天的默认调用次数**。固定600输出token、temperature0.0、非思考JSON、不流式；输出仅verdict与精确问题片段/闭集类别/局部依据标签。
- supported/unsupported/uncertain是正常审核结果，均记录后继续校准；来源、凭据、网络、格式/引用或审计失败则停止整个批次，不重试、不补额、不通过重启续跑。
- 审核结果、有限问题片段和原候选按既定方式仅本地Git忽略保存；不保存key、headers、raw response或推理过程，不更新正式Memory/Relationship/生活。

## 已准备的可审产物

- v9草稿：`273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94`。
- 24项候选文件：`838c6b6de7af0a7f50fdaa8c0b9f57babc889bf5989caf5df1c04148ce97c929`。
- 精确校准计划：`dbd9e286fda6d293fa9eb5f628004e7142c466b065a1ba61d7ff524c841faa8b`。
- [完整计划](../../.artifacts/character-reply-review-trials/dbd9e286fda6d293fa9eb5f628004e7142c466b065a1ba61d7ff524c841faa8b.plan.json)、[可读精确审核输入](../../.local_indexes/eromanga-sensei/s83/精确审核输入预览.md)均只在本地。
- 实际24个出站body为7484–13097字节，合计250356字节；白名单字段、逐项digest、参考标签未进入出站均已核对，启动目录不存在。

准备命令不读取key：

```powershell
.\.venv\bin\python.exe app/desktop/character_reply_review_trial.py --draft .local_indexes/eromanga-sensei/s78/character-evidence-draft-v9.json --source-root .local_sources/eromanga-sensei --reviewed-digest 273dcbdd43aede4ba9dbf0a3d896f7a21246f46783fb33f461d5f63b9ac2cf94 --subject sagiri --anchor v1-pre-broadcast --cases .local_indexes/eromanga-sensei/s83/calibration-cases.json
```

获批准后才追加`--approve-plan dbd9e286fda6d293fa9eb5f628004e7142c466b065a1ba61d7ff524c841faa8b`执行。旧生成计划或旧批准指纹均不能开启此用途。

## 结果怎么决定下一步

分别报告明确反例的误放、正向候选的误拒/不确定和歧义样本的处理；不能用“全部拒绝”通过。建议校准集中明确反例不得直接放行，12条正向至少10条保留才值得继续评估；这只是小样本工程门槛，不是通用正确率保证。

若审核也不可靠，先调整机制或重新比较模型能力，不把它自动串进所有聊天；若有实质收益，再准备有门槛的连续聊天。将来一轮生成再审核会增加费用和等待，本批只测既有候选，不能据此给出完整聊天延迟承诺。

输出上限14,400 token，输入按实际服务token计；当前helper未暴露usage，不用字节估算冒充实际费用。仍按[DeepSeek官方价格](https://api-docs.deepseek.com/quick_start/pricing/)计费，不请求新Provider或付费资源。
