# S160后台推进：建议归属与插件清理

2026-10-19用户要求继续推进；承接纯后台约定，未操作任何窗口或键鼠。本片整体仍为梅莫莉游戏内交流/学习接续，旧[首批真实结果与失败](../2026-10-18-slice-160/REPORT.md)保持。

## 工程与用途

[开工证据](../../research/2026-10-19-memorie-attribution.md)据实际“助手建议被称作测试目标”的缺口，核Clark/Brennan的交流呈现/理解证据及Johnson等的信息来源归属研究。只作设计类比，不能把理解直接等同采纳，也不据此赋予AI人的心理。复用现有exchange双方原话，不增加事实/目标/人格状态。

新增`memorie-companion-attribution-s160-2`技术候选：仅在system policy追加来源/采纳/完成的自然表达规则。定义、asset、父审阅/用途、Provider/slot、四投影字段、2完整轮/4000字、4096 tokens/thinking disabled/30秒/0retry均保持。新contract绑定policy摘要和parent版本，经Facade精确预览、Authority/QRI、Host、Bootstrap、Session、最终guard/冷恢复与只读原UUID查询贯通；未知版本拒绝，已有baseline root在变更前冲突，默认入口仍用baseline，不暗改旧QRI。

相同父用途下做独立技术适配，不发送新材料或新增凭据用途；准备和旧review不重写。当前experience、5条既有真实提交、所有首次/误发记录和游戏草稿保留；后续候选真实验证使用新独立开发Timeline。

54项合成/Interface与相关既有检查通过，4项已编译C#客户检查因本次未指定其可选runtime而跳过，不称本轮全过。新检查验证actual wire与Facade preview相同、除system外逐值不变、重开/原UUID/近期原话、新旧root不升级和最终授权撤回；不以合成回复验证人物归属。双独立只读复核无剩余finding。真实新场景尚待工程提交后执行。

## attribution-2首次内容与intent-3针对性修正

9741475后独立开发Timeline固定5步，五个独立进程5首次/5模型/5canonical/0retry，102/49/63/74/81字符，完整正文只保canonical。第3轮能区分助手办法与用户未采纳，第4轮承接明确采纳，第5轮没有把决定说成完成；但第3轮没承接窗口内已有的“两页笔记”意向，用“没有记录”回应，冻结的保留意图条款未达。主窗口与独立只读内容复核一致判有限通过，不改旧结果或换问句补抽。

据此追加独立`memorie-companion-intent-s160-3`：保持v2 policy逐字不变并继承其technical parent，只补“未定具体做法不等于未表达意向、按原话保留打算/决定/完成语气、自然承接而非记录播报”。全部父用途、字段、材料、资格与limits不变，旧root仍不升级。新增Interface检查验证v3 wire/policy/历史重开，后续只用新的固定场景核先前意向、未采纳、明确采纳与未完成；此前5次内容不重判。

## 插件后台修复

只读BepInEx日志发现原生组件已销毁时`NativeInput.Dispose → Component.gameObject`空引用，属于退出清理，不据此解释尚未确认的入口/按钮状态。按[Unity6000.3对象相等文档](https://docs.unity3d.com/6000.3/Documentation/ScriptReference/Object-operator_eq.html)对原生对象存活作检查；先判断root/field/RectTransform/Button，避免访问已销毁组件。`OnDestroy`时机参照[官方生命周期](https://docs.unity3d.com/6000.3/Documentation/ScriptReference/MonoBehaviour.OnDestroy.html)。Context7无可调用接口，沿官方文档回退。

candidate10用本机生成interop编译0警告0错误。在确认游戏已关闭、GameAssembly匹配原批准摘要、当前DLL精确等于candidate9且父路径无reparse后，仅原子替换自己新增的插件DLL；candidate9和原错误日志保留，回执存本机。未停止/启动游戏、读写存档或操作草稿。实际退出行为和最终UI仍未验，不用编译/存活判断冒充运行通过；没有为这个原生生命周期错误写失真的模拟测试。

## 当前边界

尚未启用attribution到用户旧root；候选实际归属、游戏最终入口/按钮/发送/焦点、实际隔日和日常人物效果继续分别验证。用户后台限制仍有效，日期变化不自动算隔日验收。S160不整片收口，不安排通知、自动回访或后台生活。
