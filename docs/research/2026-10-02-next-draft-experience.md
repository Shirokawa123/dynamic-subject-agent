# S137准备：等待回复时继续写下一条

2026-10-02，当前仍是S136。下一完整用户结果：当前一轮在处理时，用户能继续编辑下一条草稿；本轮成功、空白或结果未明都不覆盖后来文字，仍须明确发送才开始下一轮。

已证实缺口在HTML `lock`：`busy`与`presentation_pending`同时禁用textarea，网络等待期间不能继续写。S131的`request_text`与可变`text`已分开保存，`receive`只有二者与当前输入仍一致时才清空；可复用此保护，不新建队列、自动连发、第三方草稿存储或模型调用。不能只是把所有disabled删掉：发送、边界/身份操作和IME仍需独立处理。

经context7 `/mdn/content`定向核对[textarea](https://github.com/mdn/content/blob/main/files/en-us/web/html/reference/elements/textarea/index.md)与[readOnly](https://github.com/mdn/content/blob/main/files/en-us/web/api/htmltextareaelement/readonly/index.md)：disabled与readonly都会阻止编辑，后者仍可聚焦/选择，因此换成readonly也不满足继续写。采用将编辑能力与提交能力分别控制，保留同scope/页面可核状态约束。[KeyboardEvent.isComposing](https://github.com/mdn/content/blob/main/files/en-us/web/api/keyboardevent/iscomposing/index.md)表示compositionstart至compositionend期间的键盘事件；沿现有isComposing/composing/keyCode229护栏，不能因textarea可编辑就让输入法确认被当作发送。

按[HAX G16](https://www.microsoft.com/en-us/haxtoolkit/guideline/convey-the-consequences-of-user-actions/)的后果说明，将“当前快照/不是发送许可”改成可直接理解的“查看本轮参考内容；发送时会按最新文字和设置重新核对”。这是本片完整输入体验的文案收口，不另拆片。纯异步输入状态与人机交互足以解释，不引入人物心理机制或宣称意识。

验收以一个未完成请求及后来不同草稿为核心：处理中可编辑但不可重复发；成功不清后来草稿，明确失败/unknown不丢原nonce或冒称发送了新稿；刷新/重开和IME保持既有保护。必要Interface/Node覆盖成功、失败、unknown与scope变化，真实自有开发入口一轮观察“等待期间新草稿→结果之后仍在”，不向新正式空入口预灌台词。模型空白照记，不能为了通过UI验收自动重发。原用途/两轮窗口/credential/Publisher保持，不新库、不新生命周期/后台生成，不主动发送下一条。
