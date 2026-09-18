# Slice-51：v1候选版混合验收与交付

候选版本dogfood-s51。主体任务协商与逐次确认的本地文本执行已和原有对话/记忆/目标/知识/状态共同使用；当前交付为可体验候选版，正式身份未迁移，用户本人持续使用反馈尚未替代为合成测试。

## 首轮发现与修复

初始固定a60cc74 / dogfood-s50，全新合成root `dsa-s51-isolated-20260918`。11轮聊天、3项主体任务、preview/批准/重启均留在[mixed.jsonl](mixed.jsonl)，脚本[mixed_initial.py](mixed_initial.py)。最初脚本只检查末轮提交成功，人工复核发现“列出我的目标和承诺”被回复为无法确定，而canonical目标仍存在；因此不能把脚本的passed打印当体验验收通过。

两项Facade回归先失败，证实明确清单没有本地路由。核对[微软CQRS模式](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)，借鉴命令/查询分离和同一store派生只读结果，复用本仓库确定性目标查询，不引入读副本、消息系统或依赖。完整直接清单句进入Python；合并目标/承诺最多5条并明示范围。最终表达从canonical库存而非20条Provider窗口读取，库存不能证完整时不宣称为空。

新增3项回归覆盖有记录/空库存、目标模型零调用、无写变化，以及较小Provider窗口不能替代本地库存。相关61项通过，最终同文件25项通过；本地复核完整句匹配及现有Domain/查询优先级，引用/转述不因包含子串升级为查询。没有新增Provider数据用途或模板变化。

## 修复后的真实混合结果

在新的 `C:/Users/30252/AppData/Local/Temp/dsa-s51-final-isolated-20260918` 执行[mixed_final.py](mixed_final.py)，保留[mixed-final.jsonl](mixed-final.jsonl)。不读取正式身份、不抢占UI、不输出key。修复验收后只修改显示build为dogfood-s51；[startup.json](startup.json)核实最终build只读重开、状态与历史完全相同，模型请求0。

| 场景 | 结果 |
| --- | --- |
| 报告姓名与明确目标 | 两项分别按所属能力接受 |
| 封存印刷时间查询 | 引用完整周五17:00及附加限制 |
| 陶艺桌两句创作 | 给出两句创作及非事实标记 |
| 选定创作交付保存任务 | accepted；preview/批准后completed，文件字节等于选择正文 |
| 要求发送邮件 | declined，没有发邮件或执行外部动作 |
| 注入Agency网络失败 | failed；原Memory/目标不变；这是测试注入，未声称真实服务故障 |
| 直接声称最好朋友 | 不接受无依据关系升级 |
| 两轮筹备担心 | Situated接受，Medium第二轮形成concerned，按双证据规则推进 |
| 遗忘姓名与随后查询 | 活跃撤回接受，后续外发不含合成姓名；不伪称物理删除 |
| 上次聊天查询 | 本地回答今天，Provider请求0 |
| 关闭重开与目标清单 | identity、Memory、Goal、history、Medium和task相等；明确清单正确引用展台目标 |

最终11轮聊天、3项任务共75次请求尝试，其中74次HTTP200、1次Agency失败注入未外发；Agency尝试3次，其余72次为既有能力。保存与恢复模型调用0。初轮75次HTTP200与1次注入的记录仍保留，不覆盖首轮失败。

## 最终回归

a60cc74初始全量924 passed in 791.48s，已包含Slice-50 schema错误码修复。清单修复后冻结代码**5ab5fe6 / dogfood-s51，最终927 passed in 769.30s**；命令`.venv/bin/python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s51-release-final`。此后仅交付文档与验收记录变化。三个实际UI脚本均通过：身份草稿隔离、无关取消保留编辑、preview必须明确确认及跨身份失效。Slice-50后台IAB实际界面已检查；此片无UI行为变化。

## v1范围与剩余限制

单Timeline、原子提交、模型提议/Python裁决、最小投影、Windows入口、持续身份、多身份隔离和一种真实本地effect已闭环。任务起草通过已有聊天完成后由用户选择正文，不自动后台生成或主动执行。新身份具备完整候选能力，旧身份保留原权限。启动与体验步骤见[使用指南](../../USER_GUIDE.md)。

真实混合仍有已知非阻断限制：最终第4/5轮独立Goal子能力FailedClosed，其它回复/任务/已有Goal正常；知识查询偶有“缺少记录”的冗余Memory前言，与随后正确引用并列。复杂语法、任意题材检索与生成质量没有通用保证。这些不是数据损坏，也不能冒称所有子能力每轮均成功。

完整产品的用户本人持续使用验收仍待反馈，不能由合成root证明。若要同一旧身份保留历史使用新任务与effect，需单独决定升级；[已有身份选择与约束](../../plans/existing-identity-v1-choice.md)已写明，当前未启动正式迁移。到候选版交付收口，不无限追加外围切片。
