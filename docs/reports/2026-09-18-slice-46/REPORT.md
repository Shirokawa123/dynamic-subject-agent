# Slice-46：目标修改与不变安排（连续三切片2/3）

状态：完成。基线dbcc5a6 / dogfood-s45，代码0a6abda / dogfood-s46。

## 诊断与复用

原Slice-43桌布尾句及命名目标入口在Facade **2 failed in 1.79s**：物件词表/两入口不一致导致明确目标修改被拒绝。目标模型桩故意不可用，验证原有Python路径本身的缺口。

本轮Context7 resolve Rasa仍fetch failed，回退2026-09-18核对[Rasa Command Generator](https://rasa.com/docs/pro/customize/command-generator/)。借鉴将操作和参数分开表达的机制；继续复用原CurrentGoalCommand/NamedGoalChange和Domain，不引入Rasa的历史上下文、流程运行时、依赖或源码。

新增共用is_unchanged_arrangement：保留既有有限“不变”结构，新增1–24字中英文/数字主体加“照带”。不再列物件名，但明确条件、否定、操作词、多尾句、引号等仍拒绝。主体只是不变声明的一段原文，不查询物件、不证明安排存在、不产生新Memory或执行许可；目标仍按原完整库存唯一定位和原文证据裁决。两个入口共享判定，Provider12类字段/模板/调用与历史用途全部不变。

## 复核与测试

首次相关55 passed；扩大后97 passed / 1 failed：命名目标带引号尾句时，原direct_statement_spans丢掉整条候选，Memory可保存操作原文。修为仅当前完整命名操作前半句已满足直接陈述时，将其保留在unsupported拒绝路径；引号尾句不取得新权限。最终相关 **74 passed in 53.38s**。

新增21项Facade测试，覆盖原两入口、新物件/数量/英文数字、条件/否定/新操作/多尾句、非法引用及重启。单独的另一条合法目标按既有独立操作契约处理，不把它混称为尾句。code-review小型变更本地复核共享解析、完整消息范围、Memory分工与最终回执；已知失败关闭，无剩余已确认阻断。最终全量见下。

## 真实后台

新隔离合成Avery根C:/Users/30252/AppData/Local/Temp/dsa-s46-isolated-20260918，production Desktop HTTP/ApplicationFacade，原DeepSeek slot/用途；不读正式身份、旧数据，不操作焦点。原桌布和新雨伞两场景均目标创建/修改成立，Memory保持原安排；重启后画板尾句仍只改目标，不新增画板安排；明确条件和引号尾句均拒绝且两种库存不变。最终2个目标、2条原安排。

## 限制

有限尾句不是通用条件/名词语义解析；含否定/动作字样的物件名可能保守拒绝。“画板照带”即使尚无画板记录也不会新增它，只修改明确目标。未知或复合变化仍需分开说明；不将自然表达覆盖扩大为隐式状态权限。

真实共11轮；64次Transport调用、64次HTTP200，异常记录见raw/checks.json。两次重开六项投影一致；所有服务CLOSED，原始数据保留。见[逐轮记录](TRANSCRIPT.md)。

最终0a6abda：**873 passed in 651.72s**；命令`.venv/bin/python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s46-full-final`。其后仅文档与合成证据变化，diff检查通过。
