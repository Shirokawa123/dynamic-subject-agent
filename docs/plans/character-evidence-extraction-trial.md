# 资料语义提取试点方案（待批准）

这是首次向模型发送指定小说原文作结构化候选提取，不是新的角色聊天验收。当前真实调用0；之前聊天用途的批准不覆盖本用途。

## 本次目的

验证模型能否在小份可核对材料中区分经历主体、叙述者、认识持有者、事件成立与获知时间，并引用真实片段。输出只作为未审候选，人工核对后才可能纳入新草稿；不能自动进入起点认识、封存人物或改变运行状态。

## 具体数据与范围

- 目标角色：和泉纱雾；分析工作锚点：第一卷当天直播即将开始之前，尚未封存为运行起点。
- 仅用户已提供的第1、2、3卷中的50个已本地阅读的非露骨片段，原文合计1606字符（各1005/347/254）。不发送整本小说或其他11份文件。
- 出站字段只有target_name、anchor、source_title、fragments[{label,text}]及固定策略。label是样本片段标签，不是运行内部ID；本地路径、文件hash、人工审核答案、人物草稿、正式身份、历史对话均不外发。
- 完整原文、标签和固定策略在本地[待确认样本](../../.local_indexes/eromanga-sensei/s67/待确认的三卷节选.md)。该文件不进Git，远端没有原文。
- 新用途character-evidence-extraction；目的地https://api.deepseek.com/chat/completions；既有deepseek-v4-flash，沿用Windows Credential Manager的deepseek/default slot，仅用于HTTPS Bearer鉴权；不显示/另存key，不调用/models验证接口。
- 三个包各最多一次，合计最多3次，失败即停，无自动重试/重启补额。输入硬上限每包6000字符/总18000，实际固定样本只有上述1606字符，不能自行追加。
- 每次输出≤2048 token、最多8条候选，字段限statement、dimension、kind、about、knower、event_time、knowledge_time、evidence[{label,quote}]；quote须逐字出自对应片段。根字段另有language=zh。temperature0、thinking disabled、stream false、无工具。
- Python固定将返回项标为candidate；格式/引文合法不证明语义正确。空候选为no-op，非法候选整包失败，不部分伪成功。
- 原始候选和检查结果仅保存为本地Git忽略文件，不公开发布。没有自由聊天、生活生成、长期记忆或正式身份迁移。

## 批准内容

需要用户确认有权将上述三份来源中的指定节选用于本次外部分析，并批准上述目的地、凭据新用途、数据字段与3次预算。只授权这些固定样本，不等于整套小说外发或无限提取。

## 执行

默认离线（不读取key）：

```powershell
.venv/bin/python.exe app/desktop/evidence_extraction_lab.py
```

仅批准后可执行：

```powershell
.venv/bin/python.exe app/desktop/evidence_extraction_lab.py --confirm-source-rights-and-use --approve-plan dddccee51104208c954aaa22e64db592edfba8aa290ad562f425094a6adc20c8
```

计划SHA-256：`dddccee51104208c954aaa22e64db592edfba8aa290ad562f425094a6adc20c8`。样本SHA-256：`c109aa2b160ce833527780d9de4ae0bd158e0a4d650c0b6f7a817df57a6c1724`。

## 判断与下一步

先与本地已核对材料比较归属、时序、知情和引文，保留错误，不为凑通过重复调用。样本很小且已有人工参考，只能判断入口及候选质量，不证明全书提取能力。通过后再确定扩大语义覆盖的方案；仍不邀请用户开始人物试聊。
