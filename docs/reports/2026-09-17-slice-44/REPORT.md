# Slice-44：转述与引用的Memory归属裁决

状态：完成。基线a915eeb / dogfood-s42；代码/测试22a0901，build dogfood-s44。

## 诊断与复用

Slice-43 head22完整消息“小夏说：……”与实际保存的引号内第一人称为原样来源。在ApplicationFacade用外部Provider桩分别强行提出create/revise，再加嵌套引用、条件句和无引号转述，共 **5 failed in 3.15s**：无归属摘录可新增或替换已有安排。根因是Domain当前逐字检查通过后，memory_evidence_scope仅检查部分目标动作，未普遍校验摘录的引用/转述/条件范围；模型输出是当前子串不等于可以丢失说话者。

2026-09-17按context7-mcp尝试CoreNLP resolve失败，回退核对[CoreNLP官方Quote Extraction And Attribution](https://stanfordnlp.github.io/CoreNLP/quote.html)。其确定性引用提取保留字符起止位置及嵌套结构，说话者归属另行处理。本轮借鉴“范围与归属不可混为裸文本”的机制，复用现有mask_quoted_text和Domain证据接缝；不复制代码、安装Java/NLP依赖或引入说话者模型。当前目标只是拒绝失去上下文的截取，不需要实体识别、共指模型或新store；无依赖引入，因此无新增许可证/运行时维护负担。

## 有限实现

- 每个候选出现位置与完整消息的引用遮蔽对照；触及引用时，候选须保留所在完整原文单元。保留引用后的“小夏说”等归属，不把引号内部标点作为来源边界。嵌套/未闭合引用沿已有保守遮蔽；相同摘录多次出现且其中一处不可确认时拒绝，不猜出现位置。
- 无引号的有限“说/表示/提到/告诉我”报告前缀和“如果/假如/假设/要是/除非/只有/只要”条件前缀须保留所在原文单元；已知“请记住：”包装不遮蔽条件。硬句界以外不做通用共指或条件推理。
- 完整消息、保留归属的完整片段、带引号名称的独立当前自述保持原样可用；不补写说话者、不合成用户没说过的文本。完整报告保存的仍是带来源的原文，不授权执行引用中的Goal。
- 既有exact偏好旧新原文更正的引号参数仍可用：提炼共享的explicit_preference_replacement判定，只有可解析的新偏好参数使用此接缝，具体目标/库存/变化仍经原Domain校验。前后空白变体不失效，其他quoted command不因此获得新权限。
- 普通evidence的存在性由Domain先校验；Slice-38已确认偏好的旧原文继续依赖原canonical两轮例外，不把当前短答伪造成来源。原Provider12类模板/字段/预算/用途、Timeline schema与旧数据不变。拒绝复用原AMBIGUOUS与最终Memory回执。

## 验证与复核

首轮相关118 passed；边界扩大后“请记住：如果……”有 **1 failed / 19 passed**，修复包装识别。初版要求含引用候选保留整条消息过于保守，三项合法独立自述/完整转述先 **3 failed / 7 passed**，改为保留所在完整原文单元后通过。没有删掉这些正例来迁就实现。

阶段相关139 passed in 119.02s；最终24项归属Interface用例 **24 passed in 18.78s**，覆盖原create/revise、不同引号、嵌套/未闭合、重复摘录、前后置归属、条件、混合自述、完整报告、重启及exact更正空白。既有偏好确认、逻辑遗忘、目标/Memory分工与写入回执随迁。最终全量结果见下。

按code-review技能本地复核a915eeb至22a0901：检查Domain调用位置、确认例外、已知更正接缝、引用遮蔽的长度/边界以及最终回执。小型变更本地审查，未分派子代理；上述发现均有先失败后通过的Interface对照，无已确认剩余阻断。不声称通用自然语言归属完备。

## 真实后台

新隔离合成Avery：C:/Users/30252/AppData/Local/Temp/dsa-s44-isolated-20260917。production DesktopState/HTTP/ApplicationFacade，既有Windows Credential Manager DeepSeek slot和原最小投影；不读正式身份或旧验收根，不抢焦点，不迁移/清洗head22旧错误数据。

原head22本次模型选择none而非提议摘录，Memory NoOp且既有安排不变；不能把这轮说成Python拦截了同一个真实候选。另一新题材“小周说：我周日要带饼干”模型提出create、最终Memory rejected。原始输入强制create/revise均被拒绝由Interface证明。前半段只读observer仅记录action/公共DTO/回复和transport状态，不记录evidence；重启段补充合成evidence_quote和memory_kind，未改变请求/结果，不记录鉴权或raw reasoning。后续结果如下。

## 限制与后续

这是有限标点与前缀范围检查，不是通用中文语义解析。无引号的复杂转述、跨句条件与不受支持的引号格式仍可能超出范围；含义不明确的片段会保守拒绝。完整转述可沿既有原文契约保存，但后续自由表达是否总能正确理解归属不由本切片证明。旧无归属Memory没有清洗。

Slice-43自然软化修改、目标“桌布照带”尾句、跨话题稿件恢复成本保持后续范围。本轮不增加历史外发、实体归属模型、Agency或记忆框架。

## 真实结果与恢复

| Head | 结果 |
| --- | --- |
| 1–3 | 用户桌布安排保存；原head22转述这次模型none，Memory NoOp，Goal FailedClosed；清单仍只有自己的安排。 |
| 4–5 | 新“小周说”模型create最终rejected，库存不变；混合“小夏说…；我周日带三盒彩笔”保存自己的独立句。 |
| 6–7 | 条件句模型none，未写入；当前自述去河边画画正常保存。条件摘录拒绝与完整条件保留由Interface证明，不夸称真实模型提出了条件摘录。 |
| 8–11 | 重启后无引号转述及嵌套引用均模型none；带引号名称“松风”的自述accepted；最终清单只有四条完整用户自述，无他人第一人称摘录或新增Goal。 |

共11轮，63次Transport HTTP200，无网络失败；head2独立Goal FailedClosed仍保留，不把HTTP成功等同所有能力成功。见[逐轮原文](TRANSCRIPT.md)、[结果检查](raw/checks.json)。两次重开（末次移除observer）均核对display_name/build_id/memories/participant_goals/conversation_history_status/conversation_history六项一致。所有服务已CLOSED，隔离运行数据和首次响应保留。

## 最终回归

代码/测试22a0901：**837 passed in 659.64s**。命令 `.venv/bin/python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s44-full-final`。包含既有Provider最小投影/字节、原子Publication、故障/重启和其他能力回归。其后仅文档与合成验收记录变化，`git diff --check`通过。
