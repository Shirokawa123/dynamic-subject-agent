# Slice-42：自然偏好澄清闭环

状态：完成。基线675a2ee / dogfood-s41，代码/测试0116807，实现dogfood-s42。

## 诊断与复用

原独立混合验收4/6（8为6的重复）/9轮在ApplicationFacade构造自然声明、候选问题、短答和查询。初次pytest因旧默认临时目录ACL无法创建fixture，换新隔离basetemp后 **3 failed in 2.79s**：自然场景句不被场景查询识别，未决颜色进入普通Memory Provider路径而非明确问题。测试桩故意提议保存整句，证明本地缺口；原真实Provider当时自由追问，不从本次桩反推旧模型行为。

2026-09-17按context7-mcp尝试resolve Rasa，fetch failed；回退核对 [Rasa Flow Steps官方文档](https://rasa.com/docs/reference/primitives/flow-steps/) 的collect、ask_before_filling及结束清理：等待特定字段，明确询问当前确认，完成后不复用旧选择。复用Slice-38已有canonical问题、下一消息/30分钟限制、取消和重启恢复；只将明确当前自然场景/颜色接入该流程。没有引入Rasa运行时、依赖或源码；已有单Timeline和Python裁决满足所需机制，无第二套状态权威或历史外发。

## 有限契约

- 接受完整“给〔场景〕挑颜色时，我〔通常〕〔也〕喜欢/偏爱〔颜色〕〔尾句〕”，按原文保存场景与限定句。
- 接受“〔最近〕〔场景〕用〔颜色〕也不错，我〔拿不准/不确定〕〔这算/是〕〔添一种/补充〕还是〔换掉原来的/替换〕”。颜色沿用既有以“色”结尾的有限格式，场景字面匹配，不猜别名。没有可靠旧场景时提示完整重述，不直接保存这个未决候选。
- Python生成明确补充/替换问题，下一短答才取得原限定确认权限；原声明完整内容、来源ID、确认ID分别保留。不能把“也不错”直接推断为补充，不合成新的用户原话。
- 补充与简单唯一旧记录替换均沿用原流程；原“远看也不冷”等旧尾句、多个旧目标或其他复杂内容仍禁止短答替换丢失信息，要求完整旧新原文。
- 普通更正前缀或exact更正也不能把未决候选直接变成确定偏好。自由模型追问仍不产生pending权限。

Timeline本地LivingMemoryRecord增加只读派生preference_confirmed，由既有已验证preference_confirmation生成。无持久schema、Provider字段或数据迁移；它区分已确认补充/替换与旧版本直接保存的“拿不准”文本。后者不升级为确定偏好，旧历史不删除或改写。查询与替换使用同一recorded_preference解释，防止语义漂移。库存摘要和冻结prefix仍共同绑定原有不可变记录。

## 验证与复核

首轮原对照与既有测试41 passed；复核发现旧未决文本被列成偏好、控制前缀绕过确认，两项Facade反例 **2 failed in 2.41s** 后修正。撤回用例最初错误断言NoOp，实际Domain已拒绝且无写入，改为正确断言非accepted，没有因此改产品逻辑。最终相关 **56 passed in 55.76s**，新增18项Interface用例涵盖补充、替换、取消、重启、重复回答、换题、不同场景、未知旧场景、未确认旧记录、引用/条件/过去/撤回和完整尾句。

按code-review技能本地复核675a2ee工作区含新增测试：自然解析、Domain当前原文校验/确认例外、Timeline派生、查询/替换共享解释及Provider DTO构造。小型变更未分派子代理；两项已确认问题已修复，无剩余已确认阻断。现有超时、未提交问题、库存/身份/prefix变化、未决和权限失败用例随迁；最终全量结果见下。

## 真实后台

新合成Avery根C:/Users/30252/AppData/Local/Temp/dsa-s42-isolated-20260917，production DesktopState/HTTP/ApplicationFacade；原Windows Credential Manager DeepSeek slot和既有六类最小投影，不读正式身份/旧验收根、不抢占UI，不新增Provider用途。偏好入口和短答由本地流程处理，不把历史状态证据外发。

| Head | 结果 |
| --- | --- |
| 1–2 | 原第4轮完整场景/颜色/尾句保留；另存工具标签颜色作隔离对照。 |
| 3–5 | 原第6/8轮同一原文产生明确补充/替换问题，无提前写入；“是补充”新增原文，查询砖红+米白并存且不混入海军蓝。 |
| 6 | 重复短答没有可用问题，无新增Memory；本轮短时姿态Provider网络失败，独立FailedClosed提示保留。 |
| 7–8 | 新信封场景浅灰基准与浅黄待确认问题；此时关闭服务。 |
| 9–10 | 重启后直接“替换”成功，浅灰superseded、浅黄active；查询只显示浅黄，其他场景不变。 |
| 11–13 | 淡紫候选明确问题、“算了”取消，查询仍浅黄。 |
| 14–17 | 再提淡紫后换话题，再答“是补充”不写入；最终查询仍浅黄。 |

共17条committed，最终4条active加1条superseded；70次Provider Transport调用中69次HTTP200、1次network-failure（head6 Situated所属失败），不是零故障运行。所有本地偏好入口/查询/短答均未调用LM proposal/reply；observer仅在换话题轮记录LM公共DTO，不记鉴权或raw reasoning，也不改变请求/结果。其他能力沿原当前消息用途运行。见[逐轮原文](TRANSCRIPT.md)、[状态检查](raw/checks.json)。

两次重开（第二次移除observer）均核对display_name/build_id/memories/participant_goals/conversation_history_status/conversation_history六项一致，见raw两份comparison。所有服务已CLOSED，原始首次响应及隔离运行数据保留。来源ID/确认元数据的精确绑定由Interface验证；真实HTTP可见状态验证原文、active/superseded与结果，不夸称HTTP展示内部确认字段。

## 剩余范围

仍为有限自然句式；无色后缀的名称、任意意译、模型随意追问及无完整场景的旧记录不自动补全。既有复杂旧内容替换限制保持，已确认但原文带未决尾句的记录也不会被短答替换截掉尾句。下一建议做混合场景持续体验复验，再判断具体剩余缺口；本切片不扩展Agency、通用工作流或记忆框架。

## 最终回归

代码/测试0116807：**813 passed in 612.89s**。命令 `.venv/bin/python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s42-full-final`。包括既有Provider最小投影/字节、确认故障与恢复、原子Publication和其他能力回归。其后仅文档与合成验收记录变化，`git diff --check`通过。
