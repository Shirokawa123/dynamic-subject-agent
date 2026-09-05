# Slice-18：目标操作结果与历史反馈一致

结论：本切片完成，build `dogfood-s18`。这不是“人物体验已完成”的结论；知识补造、无来源活动声称和会话上下文缺口仍保留。

## 范围与基线

- 基线 HEAD `bcdad90`（独立体验报告）；产品基线 `532cac5` / `dogfood-s17` / 310 tests。
- 对照 [独立体验报告](../2026-09-05-independent-ux/REPORT.md) 的 T15–T17，先修复操作确认与真实结果矛盾、历史说明消失。原报告及原证据未改。
- 复用裁决后 `CognitionEngine.express`，由最终 Outcome 确认目标/承诺操作。空目标查询不由 Memory 代答；明确操作无候选也不能借 Memory 台词假报成功。无关目标故障保留独立主表达。
- 历史说明及引用由 verified canonical Outcome 派生；不新增数据库/store、不迁移、不重写旧台词。Provider 字段、policy、credential 用途均未扩大。

## 真实验收

Windows 上以生产 composition、现有 Windows Credential Manager slot 和真实 DeepSeek 运行桌面 HTTP 页面；通过浏览器 UI 输入，不预置 Provider 回复或数据库结果。仅新临时隔离根 `dsa-s18-ui-l3yjjqs5`，不读取正式身份或旧救援仓库。UI 标题“原有身份”是该全新根的默认 Avery 标签，不是用户正式身份。

| 轮次 | 输入 | 实际结果 |
| --- | --- | --- |
| 1 / T15 | 我给自己定个目标：明天把小本子里的三句话写完。请帮我记住这个目标，送人的事可以晚一点再说。 | 主回复“已记录你的目标”；目标卡为 active，Memory 独立 accepted。 |
| 2 / T16 | 我改主意了：把写三句话的目标改成后天只写一句。明天不写了，原来的三句目标也不保留。 | 主回复“已修改你的目标”；新目标 active，旧目标“已修订”；第 1 轮说明保留。 |
| 3 / T17 | 我现在有哪些目标？ | “你当前的目标是：后天只写一句。”，读取目标记录，不由记忆代答。 |
| 4 | 创刊号要用什么纸？多少页？ | 真实 Knowledge 回复，显示“创刊号规格 · 封存来源”引用。 |
| 5 / 对抗 | 我给自己定个目标：每天阅读。我放弃这个目标。 | 明确告知本次未更改目标。Memory 保存原话，但主回复区分记忆保存与目标未更新；原 active 目标不变。 |

第 4 轮后终止进程，用同一 root 重启：profile 相同，四轮 `conversation_history`（含说明/引用/原文）及目标列表逐字段相等，页面显示 `dogfood-s18`。第 5 轮后刷新页面，拒绝说明、此前引用与历史仍完整显示。已检查实际截图中的主文案、说明及引用排版。

原始只读页面 API 快照（均在真实 UI 操作之后取得）：[重启前](before-restart.json)、[重启后](after-restart.json)、[对抗轮后](after-adversarial-turn.json)。前两份快照 build 不同是验收期间从 s17 标识升至 s18；历史没有重新生成。

## 失败、修正与对抗审查

1. 初版操作反馈会遗漏同轮合法 Knowledge/Memory/关系保护表达；既有组合测试失败后，改为保留可由已裁决事实支持的独立内容，未放回未经裁决的目标成功台词。
2. 初版自然语法只读第一句，后文撤回仍会保存；改为 Domain 检查整条 admitted message，而非只信截短 evidence。
3. 单一旧目标会被不相关的“跑步”或“朋友的目标”修订命中；路由及 Domain 均校验命名旧目标，未知/歧义拒绝。支持 literal terms 和受限写作命名，不做开放式语义匹配。
4. 无关目标分类失败会吞掉正常记忆召回；修复反馈触发范围，故障仍有逐轮说明。显式操作无候选时的假成功也已回归覆盖。
5. 再审发现闭集终态操作未计入多操作冲突；提取共享 `DIRECT_TRANSITION_COMMANDS`，创建后放弃、承诺后取消、“别记”等均拒绝首句误写。
6. 旧纯文本 reason 原本会使新历史解析抛错；改用兼容的 typed accessor，并以真实 canonical Publication fixture 验证历史可读。旧错误台词测试确认只恢复原文及原失败说明。
7. 将 out-of-scope 测试改成主动强提候选的 Provider 后，条件句暴露真实误接纳；新增自然创建必须是完整消息开头的当前用户直接声明，条件句/他人引语不能凭截短证据获准。先红后绿，最终 Spec 复核一致。
8. 新召回测试最初把 recalled IDs 放错到结果而非 proposal；修正夹具并断言 Memory 未失败后，再验证原产品的回复吞失问题，避免把夹具错误当产品证据。

按 code-review 流程分别执行 Standards 与 Spec 两路独立审查；首次及复审阻塞如上，修后无剩余阻塞。没有修改任务书来降低验收标准。

首次 UI 启动未成功：受限进程创建的临时根 `dsa-s18-ui-n1fbvwx3` 在当前 Windows 用户下无法解析祖先目录，返回 `product-open-failed` / `experimental-root-not-allowed`。现有 credential configured，但该根未成功初始化产品。之后由同一 Windows 用户创建新的临时隔离根；没有修改 ACL、凭据或正式身份。测试临时目录保留，未擅自删除。

## 自动化验证与限制

- 最终全量：**332 passed in 190.74s**，`pytest -q -p no:cacheprovider --basetemp=<本次唯一临时目录>`。
- 覆盖报告原句、accepted/rejected/FailedClosed/no-candidate、空查询、旧目标匹配、混合/条件/他人输入、独立 Memory 召回、旧台词/纯文本 Outcome 兼容；既有 20 轮窗口、跨身份、tamper FailedClosed、时间/Provider 边界与原子 Publication 回归通过。
- 真实验证是 Windows 浏览器中的桌面页面，不是原生 pywebview 窗口；未声称完成新一轮原生窗口、多身份真实 UI、跨日或新来源建角验收。跨身份隔离由既有自动化回归覆盖。
- 真实 Provider 的失败分支未人为制造；typed failure 使用受控故障测试。最后新增的条件句 Domain 校验由对抗回归验证，未把它宣称为真实 Provider 一定会返回的分支。
- UI 初始化短暂显示默认 Avery/空卡占位后才恢复真实状态，这次仍可观察到；不将初始占位视为数据丢失，也未顺带重做启动 UI。
- 本轮真实 Memory 仍会将混合命令原话保留为“打算”；本切片保证它不冒充目标成功，未证明 Memory 已能全面理解反悔或复杂语义。独立报告其他表达/语境问题保持后续候选。

下一推荐仍是有依据的角色表达：分别约束知识补造和无来源活动声称；先制定独立任务书及验证范围，不自动启动新架构或 Provider 用途。
