# Slice-40：混合自然目标

状态：完成。基线6f9ea62 / dogfood-s39。

## 诊断与复用

独立混合验收13/14/21/22轮为原始样本。原文创建与带“诊断对照”前缀均路由None、Memory证据全句eligible；去除前缀补回“我”即命中确定性create、Memory participant-only。两组ApplicationFacade原始对照先 **2 failed in 1.58s**（故意模拟分类失败），证明本地识别缺口与Memory范围未排除并存，不证明能力在争夺同一写锁，也不能从黑盒反推原Provider具体错误。

按context7-mcp技能尝试resolve Rasa时fetch failed，回退2026-09-13核实的 [Rasa Command Generator官方文档](https://rasa.com/docs/pro/customize/command-generator/)。复用动作与参数绑定、区分无法生成命令与执行结果的思路；仓库已有typed candidate和Domain，无需引入其流程栈、额外上下文或依赖。新解析保留当前原文跨度，一份结果供目标路由、最终裁决和Memory分工使用，不复制Rasa实现。

## 有限实现

当前明确“换个话题：”“说正事：”“（诊断对照）”前缀保留原文；逗号连接的自述安排后“也给自己定个/一个目标”仅从当前第一人称安排继承主语，条件或不明结构不执行。支持完整“把目标〔引号旧条款〕改成/改为/换成〔引号新条款〕”；省略目标二字时仅在旧条款逐字命中当前active目标才进入该能力。新旧引号必须配对，旧条款完整库存唯一，不以引号内容生成指令；尾部只允许裸安排/计划不变、椅子/工具/材料/点心照带，其他尾句拒绝。

目标创建/修订继续原append-only裁决，Memory扣除已识别目标操作，保留独立连续原文；拒绝的明确目标修改不能覆盖安排。原主体、引用、条件、撤回、同轮多命令、完整库存及Provider原投影/提示/调用边界保持。没有历史新授权、pending状态或新store。

## 验证进度

初始原样及Slice39相关19 passed in 16.68s；扩大Interface/旧分工/最终回执 **73 passed in 60.35s**，目标Domain/Provider/时间 **31 passed in 7.82s**。包含恶意Provider截取条件/转述/引号修改的反例，不以Provider失败代替裁决验证。最终全量、复核和真实后台结果见下。

code-review两轴复核6f9ea62..e8275c7：规格轴发现新增引号修改的Memory证据缺少完整消息核对，可能被模型从转述或条件中截取后覆盖独立安排。两项Facade反例先 **2 failed in 1.98s**；9ef2f8d修复为同时核对逐字命令和绝对起始位置，相关 **53 passed in 38.58s**。复核确认P1关闭，规则轴无其他确定问题；初次全量因该修复中止，不记为通过。

## 真实后台

全新隔离根 `C:/Users/30252/AppData/Local/Temp/dsa-s40-isolated-20260913`，经production composition创建默认合成Avery，不复制或改写此前唐微/许澄验收根，不操作正式身份。代码9ef2f8d / dogfood-s40，沿用原DeepSeek slot和数据用途，后台HTTP；未修改Provider配置、凭据或抢占页面焦点。

| Head | 结果 |
| --- | --- |
| 1–2 | 原独立第13/14轮原样：椅子安排与底稿目标分别形成；引号指定旧目标改为两句正文，Memory NoOp且安排清单完全不变。 |
| 3–4 | 原独立第21/22轮原样：带诊断前缀建立工具箱目标，再以完整旧新条款修订；Memory均NoOp。 |
| 5–6 | 确定性目标查询返回两项最终条款；自然安排查询完整引用周日带三把椅子的原文。 |
| 7–9 | 未加入自动测试的新题材“下周二带材料去陶艺课＋做杯子目标”分别保存；改为练杯把，材料照带且Memory不变；混有“如果晴天”明确拒绝目标，Goal与Memory清单均不变。 |
| 10–13 | 重启后目标查询恢复三项；杯把目标继续修订为做好再晾干，Memory不变；椅子仍可召回；不存在的采购清单目标拒绝且两种清单均不变。 |

共13轮，最终3项active目标、2条独立安排Memory。第一次重启及最终再次关闭重开均对照display_name/build_id/memories/participant_goals/conversation_history_status/conversation_history六项，完全一致。所有服务已CLOSED，隔离运行数据保留。trace记录live 55与restart 25次HTTP200，无transport failure，逐轮没有能力failed-closed。

见 [逐轮对话](TRANSCRIPT.md)、[状态检查](raw/checks.json)、[第一次重启](raw/restart-comparison.json)、[最终重开](raw/final-reopen-comparison.json)。raw保留各轮首次响应和逐轮状态，仅内部UUID脱敏；观察器不改变请求，只记录已有公共Memory DTO与HTTP状态。

## 最终结果与限制

全量 **778 passed in 620.95s**，代码/测试提交9ef2f8d；命令 `.venv/bin/python.exe -m pytest -q --tb=short --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s40-full-final`。其后仅文档及合成验收记录变化。`git diff --check`无错误；19项新增Interface用例与既有Provider最小投影/字节、原子提交、恢复及其他能力回归通过。文档复核与raw核对无重大事实矛盾。

当前修复的是可核实的当前自述和逐字操作，不是任意自然目标理解。未支持前缀、复杂条件安排、意译旧条款或未知尾句仍可能需要完整重述；省略“目标”的修改只有现有目标逐字匹配时才按Goal处理。原失败生成的旧Memory没有清洗。独立报告共同写作19/20轮连续失败与自由偏好澄清仍待新切片；现有证据仍不支持更换整个记忆框架。
