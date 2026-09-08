# 交流与接口记录

本记录按发生顺序保留本次体验的用户文本、后台结果说明和引用。`[代理体验者]` 是模型代理，不是人类用户。未产生的角色回复不会补写。

## 建角（对话前）

1. `[代理体验者]` 明确确认：这是一份原创合成文本；同意它仅用于未发布角色候选提取。

   来源标题：`秋日便笺（原创合成）`

   来源正文：`林柚是一名在社区图书室轮值的整理员。她喜欢把散乱的纸张按颜色夹好，也会在傍晚记下窗边的光。她说话简洁，遇到不知道的事会直接承认，并愿意一起把小事写成短句。`

   结果：`available`；10 个候选被接受，0 个被拒。完整脱敏响应：`raw/01-source-preview.json`。

2. `[代理体验者]` 选择全部候选并明确确认本地保存。

   结果：草稿 revision 1，`available`。完整脱敏响应：`raw/02-source-save-first-map.json`。

3. `[代理体验者]` 请求以“林柚（复验隔离身份）”显示 mapping。

   结果说明：`rejected`，`source-freeze-display-name-not-in-identity-evidence`；没有 freeze。

4. `[代理体验者]` 一次澄清后以来源身份名“林柚”请求 mapping，明确确认 exact freeze basis。

   结果：mapping `available`；freeze `created`，5 条 sealed Knowledge 成员，初始为 inactive。完整脱敏响应：`raw/03-source-map-freeze.json`。

5. 关闭该后台产品进程并重新打开相同临时运行根；`[代理体验者]` 明确选择“林柚”。

   结果：`selected`、`active: true`。这是建角数据的重启后证据，不是聊天历史恢复。完整脱敏响应：`raw/05-restart-evidence.json`。

## 第一段对话（阻断于第 1 轮）

6. `[代理体验者]`：今天整理桌面时找到一张空白明信片。我想把它写成送给朋友的小句子，你愿意陪我想想吗？

   首次可提交后台结果：`status: unavailable`，`problem.code: intent-unavailable`，`operation_ref: null`。

   角色主回复：无。

   当轮说明：无（没有 committed outcome）。

   引用：无。

   完整脱敏响应：`raw/04-chat-submission.json`。

### 命令构造前置记录（非用户对话）

为调用公开的后台命令对象，体验者先遇到三次 Admission 前规范错误：不支持的 contract version、命令 kind、以及语言 canonical normalization。这些调用均在 `SubjectCommand` 构造时抛出，未交给 `ApplicationFacade`，未写入 Timeline，也没有角色输出；它们不替代上面的首次自然用户输入或成功/失败结论。修正到产品接受的封装格式后，第 6 项返回 `intent-unavailable`。

没有继续改写第 6 项的自然语言或猜测不同 intent；因此没有第二段聊天，也没有聊天后重启。
