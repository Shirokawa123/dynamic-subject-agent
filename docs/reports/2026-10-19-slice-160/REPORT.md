# S160后台推进：建议归属与插件清理

2026-10-19用户要求继续推进；承接纯后台约定，未操作任何窗口或键鼠。本片整体仍为梅莫莉游戏内交流/学习接续，旧[首批真实结果与失败](../2026-10-18-slice-160/REPORT.md)保持。

## 工程与用途

[开工证据](../../research/2026-10-19-memorie-attribution.md)据实际“助手建议被称作测试目标”的缺口，核Clark/Brennan的交流呈现/理解证据及Johnson等的信息来源归属研究。只作设计类比，不能把理解直接等同采纳，也不据此赋予AI人的心理。复用现有exchange双方原话，不增加事实/目标/人格状态。

新增`memorie-companion-attribution-s160-2`技术候选：仅在system policy追加来源/采纳/完成的自然表达规则。定义、asset、父审阅/用途、Provider/slot、四投影字段、2完整轮/4000字、4096 tokens/thinking disabled/30秒/0retry均保持。新contract绑定policy摘要和parent版本，经Facade精确预览、Authority/QRI、Host、Bootstrap、Session、最终guard/冷恢复与只读原UUID查询贯通；未知版本拒绝，已有baseline root在变更前冲突，默认入口仍用baseline，不暗改旧QRI。

相同父用途下做独立技术适配，不发送新材料或新增凭据用途；准备和旧review不重写。当前experience、5条既有真实提交、所有首次/误发记录和游戏草稿保留；后续候选真实验证使用新独立开发Timeline。

54项合成/Interface与相关既有检查通过，首组4项已编译C#客户检查因未指定其可选runtime而跳过，不称首组全过。新检查验证actual wire与Facade preview相同、除system外逐值不变、重开/原UUID/近期原话、新旧root不升级和最终授权撤回；不以合成回复验证人物归属。双独立只读复核无剩余finding。以下分别保留两个独立真实首景的结果。

## attribution-2首次内容与intent-3针对性修正

9741475后独立开发Timeline固定5步，五个独立进程5首次/5模型/5canonical/0retry，102/49/63/74/81字符，完整正文只保canonical。第3轮能区分助手办法与用户未采纳，第4轮承接明确采纳，第5轮没有把决定说成完成；但第3轮没承接窗口内已有的“两页笔记”意向，用“没有记录”回应，冻结的保留意图条款未达。主窗口与独立只读内容复核一致判有限通过，不改旧结果或换问句补抽。

据此追加独立`memorie-companion-intent-s160-3`：保持v2 policy逐字不变并继承其technical parent，只补“未定具体做法不等于未表达意向、按原话保留打算/决定/完成语气、自然承接而非记录播报”。全部父用途、字段、材料、资格与limits不变，旧root仍不升级。新增Interface检查验证v3 wire/policy/历史重开，后续只用新的固定场景核先前意向、未采纳、明确采纳与未完成；此前5次内容不重判。

aab46d3后intent-3新固定场景，仍为五个独立进程、5首次/5真实模型/5canonical/0retry，同一Timeline `918e2a90-42df-4fd1-b9c2-f3806d0e1b59`，正文106/70/81/77/63字符。第3轮保留用户整理三条实验笔记的打算，同时说明具体办法未定且尚未开始；第4轮承接用户明确选择的做法；第5轮没有把采纳当完成，也没有把此前助手建议说成已采纳。主窗口和独立只读内容复核确认该场景四项事实要求均成立，表达可自然接续；只证明这五轮，不外推为通用、长距或隔日通过。评分复核经Facade读canonical，0新增发送；不把正文另存Git。

本日两首景共10真实请求，连同此前5次累计已知15次，均保首次结果与metadata-only审计，不以新通过覆盖attribution-2意向遗漏或旧错误。

## 独立日常入口准备

Python CLI保留baseline默认和旧marker格式；日常CMD调用的PowerShell启动器默认选择intent-3，严格映射到新的`.artifacts/s160/experience-intent`。原experience及其已披露合成记录保留，不迁移、不删除、不暗改旧QRI。新入口已零模型初始化和同身份重开：Timeline `4cb4d813-2f96-41ce-815f-83ff09ae8b5c`，canonical0/audit0。旧根只读确认没有pending，registry摘要不变。

两独立复核发现启动器只核版本可能误接同版本开发Timeline（P2）。现先由只读`--describe-entry`核原批准/review，并派生绑定限定绝对root、准确合同版本与批准摘要的entry key；正式实例的health携带此key，普通开发factory缺省为空。启动器对已有服务复用和新启动均核版本/key，不匹配则保留进程并拒绝。真实Windows PowerShell5负测证实旧脚本错误接受同版本错入口、新脚本拒绝且不执行Start-Process；两复核已关闭该项，无剩余finding。该key用于入口识别，不充当POST会话token。

游戏草稿和输入不触及；尚待本次工程提交后在空闲8798隐藏启动新正式入口，并以只读HTTP/C# probe确认，不向正式入口发送测试消息。

## 插件后台修复

只读BepInEx日志发现原生组件已销毁时`NativeInput.Dispose → Component.gameObject`空引用，属于退出清理，不据此解释尚未确认的入口/按钮状态。按[Unity6000.3对象相等文档](https://docs.unity3d.com/6000.3/Documentation/ScriptReference/Object-operator_eq.html)对原生对象存活作检查；先判断root/field/RectTransform/Button，避免访问已销毁组件。`OnDestroy`时机参照[官方生命周期](https://docs.unity3d.com/6000.3/Documentation/ScriptReference/MonoBehaviour.OnDestroy.html)。Context7无可调用接口，沿官方文档回退。

candidate10用本机生成interop编译0警告0错误。在确认游戏已关闭、GameAssembly匹配原批准摘要、当前DLL精确等于candidate9且父路径无reparse后，仅原子替换自己新增的插件DLL；candidate9和原错误日志保留，回执存本机。未停止/启动游戏、读写存档或操作草稿。实际退出行为和最终UI仍未验，不用编译/存活判断冒充运行通过；没有为这个原生生命周期错误写失真的模拟测试。

## 当前边界

旧root未升级；intent-3的单个五轮真实场景已有限成立，游戏最终入口/按钮/发送/焦点、原生退出修复的实际运行、实际隔日和日常人物效果继续分别验证。用户后台限制仍有效，日期变化不自动算隔日验收。S160不整片收口，不安排通知、自动回访或后台生活。
