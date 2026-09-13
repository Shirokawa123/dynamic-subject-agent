# Slice-39：自然目标操作

状态：完成。基线b981478 / dogfood-s38，来源为独立验收第6/7轮。

## 调研与复用

2026-09-13查阅 [Rasa Command Generator](https://rasa.com/docs/pro/customize/command-generator/) 与 [LLM Command Generators](https://rasa.com/docs/reference/config/components/llm-command-generators/)，借鉴把自然表达绑定为明确动作和参数、纠正时定位字段的机制；对照 [LangChain结构化输出类型](https://reference.langchain.com/python/langchain/agents/structured_output)，本仓库已有ModelGateway、typed candidate和输出验证，故直接复用，不引入第二套Agent/依赖或复制源码。偏好澄清的跨轮权限不泛化给目标，本轮仍仅使用当前完整消息与已有目标状态。

## 诊断和实现

原样“周六我准备请两个朋友来吃早餐；我也给自己定个目标：在周五前把菜单想清楚。”在Interface得到Goal rejected，1 failed in 0.97s。原创建前缀在路由、冲突检查与Domain各有表达差异；命名修改没有结构化对象；整句被Memory接收会覆盖安排。

统一自述目标前缀，支持“我也给自己定个/一个目标”；named_goal_changes解析“〔名称〕这个/这项目标我想/希望改成/改为/换成〔内容〕”，输出名称、内容、逐字证据及原消息跨度。名称在当前活跃目标条款或该目标当前修改证据中显式名称里匹配，必须全库存唯一；不是任意语义别名或永久名字库。模型挑选的引用子串不能冒充当前修改指令。

允许逗号后仅附闭集“不变”说明，新目标只取修改内容，Memory将整个操作及不变说明视为无新记忆依据。支持裸安排/计划，原有/原来/其他/其它/别的限定，或我/我们/朋友/同事/家人来或一起吃早午晚餐、聚餐、见面、出游的安排/计划。其他尾句、混合变化或条件明确拒绝后要求分开说明，不能截掉。引用/假设/他人目标/多操作/撤回仍受完整消息检查。

本地目标库存读最多100条active，达到上限不能证明完整，拒绝状态变化；Provider继续只接收原20条窗口，字段/提示/调用预算不变。完整库存同供路由、预检查与最终Domain，目标引用索引在同一有序库存中对应；不额外外发证据或历史，不清洗旧记录。

## 验证进度

原两轮修复后1 passed in 1.27s。初期相关26 passed in 29.32s，扩大相关53 passed in 46.45s，含目标/记忆分工、旧目标语法与时间/Provider基线63 passed in 51.22s。覆盖其他题材与动作、同名/未知/引用/条件/撤回，以及模型窗口遗漏但完整本地库存存在的对照。

两轴code-review复核发现“不变”尾句允许任意前缀，可能吞掉条件或额外变化。新增Interface反例先2 failed in 1.99s，初次修复后相关54 passed in 46.00s；第二次复核指出仅排除关键词仍漏“假设”，最终改成闭集名词结构，并加“假设”“只有晴天”反例。最终专项 **17 passed in 15.72s**；规格轴确认P1关闭，标准轴未发现其他可执行问题。两次中途全量为修复停止，不计入成功结果。

## 真实后台与恢复

复用既有合成许澄根 `dsa-independent-natural-ux-20260913`，schema2 identity和原DeepSeek slot，后台HTTP经production composition调用。正式身份、Provider配置/凭据及页面焦点未修改；原验收的错误Memory与旧历史仍保留。live阶段代码6b198b7，重启与最终重开代码2c9d8fa；二者仅最后不变尾句闭集和新增反例不同。

| Head | 实际结果 |
| --- | --- |
| 47–48 | 原独立验收6/7轮原样输入：首轮Memory保存早餐安排原文、Goal创建菜单目标；第二轮Goal修订为“三道菜”，Memory NoOp。 |
| 49–51 | 查询确认“三道菜”；同名继续改为“列好采购清单”；早餐查询仍引用“周六我准备请两个朋友来吃早餐；”。 |
| 52–54 | 新题材旅行照片目标建立并改成“先整理十张照片”；混有“如果下雨”的目标修改和Memory写入均rejected。 |
| 55–58 | 重启后两项目标恢复；“菜单”继续改成“准备好食材”，Memory清单前后相同；早餐可查询；“假设下雨”目标与Memory均rejected且清单完全不变。 |
| 59–60 | 最终代码上新建“同事出游安排＋出游清单目标”，分别保存；随后只改目标为“先列好必需品”，安排清单保持完全一致。 |

共14轮追加（47–60）。重启和最终再次关闭重开均比较display_name/build_id/memories/participant_goals/conversation_history_status/conversation_history六项，完全一致。最终active目标为准备好食材、先整理十张照片、先列好必需品；原有Memory全部保留，新增早餐和出游安排独立存在。所有后台服务已CLOSED，运行数据保留。

非本切片失败保留：Head51早餐查询的Situated State处理出现一次network-failure，响应明确failed-closed且没有写入新姿态；Memory仍正确引用早餐安排。live trace为48次HTTP200与1次网络失败，restart为37次HTTP200。未重试覆盖原轮，也不宣称六能力每轮全部成功；该无依赖能力失败不影响本轮Goal/Memory验收结论。

见 [完整对话](TRANSCRIPT.md)、[结构化验收检查](raw/checks.json)、[重启对照](raw/restart-comparison.json)、[最终再次重开](raw/final-reopen-comparison.json)。raw响应只去除内部UUID，保留首次结果和各能力实际状态；Memory观察记录仅包含原公共DTO与HTTP状态，不记录key或改变请求。

## 最终结果与限制

最终全量 **759 passed in 601.01s**，代码/测试提交2c9d8fa，命令 `.venv/bin/python.exe -m pytest -q --tb=short --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s39-full-closed-tail`；其后仅文档与合成验收记录变化。原Provider字节/最小投影、历史控制、原子提交/恢复及其他能力回归通过；`git diff --check`无错误。

这是有限自然目标语法和安全对象绑定，不是任意自然语言理解。名称改写、裸“改成这样”、通用条件计划或复杂尾句不推断；同名须明确旧对象，不支持完整清单未知时写入。原失败产生的错误记忆不会自动清洗。下一步宜先做独立的跨场景混合回归，再依据实际选错/冲突证据决定是否需要更通用记忆组织；本切片不启动新框架或数据迁移。
