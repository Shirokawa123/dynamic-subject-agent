# Slice-20：关系失败的有界维护结论

结论：**有界排查完成，原故障未复现，精确原因未定；没有实施行为修复。** 产品仍为 `f5ea73b` / `dogfood-s19`。不以四次成功改写 Slice-19 第 8 轮失败事实。

## 原始证据

Slice-19 [最终状态](../2026-09-05-slice-19/final-state.json) 第 8 轮“我喜欢什么样的地方？”完成了 Memory 召回，但 Relationship FailedClosed。

只读检查该报告指明的专用根 `C:\Users\30252\AppData\Local\Temp\dsa-s19-ui-9u290eew`，第 8 个 publication 的关系裁决保留：

```json
{"code":"relationship-provider-failed","status":"failed-closed","reason_code":"relationship-provider-failed","event":""}
```

读取通过 SQLite `mode=ro` / `query_only=ON` 完成，没有启动旧 Runtime、恢复 pending、发送旧聊天或改写记录；仅查指定合成测试库的该轮原因。原始根的普通受限读取遇到权限拒绝，随后以获准的当前 Windows 用户只读访问同一路径，没有修改 ACL。该只读步骤未访问正式身份、旧救援仓库或凭据；后续采样仅通过既有安全路径使用 credential 作 HTTPS 鉴权。

该代码对应 `ControlledRelationshipCognition.propose` 的 `ModelGateway.execute(RELATIONSHIP_ANALYSIS)` 调用链抛异常，不是 Domain 的普通规则拒绝，也不是可选 identity reply 的回退结果。这里会汇总 Provider/Gateway 异常；未保存该次 HTTP 状态、原始响应或细分错误，因此**不能追溯证明当时是网络、返回格式还是调用链内的本地异常**。本次定向只读提取不替代完整 Timeline 链重新验签。

## 四次真实采样

严格按任务书只采样四次，均使用既有生产 `DeepSeekRelationshipProvider.analyze` 和 `DeepSeekUrlLibTransport`，输入固定为报告中的原创虚构文本：

- current_user_message：`我喜欢什么样的地方？`
- stance_summary：`尚无立场互动记录。`
- 其余 fixed policy、模型和请求字节生成逻辑保持原样；沿用既有 credential，仅作 HTTPS Bearer 鉴权。

四次均 HTTP 200、预期模型、合法 `no_persistent_evidence`；evidence_quote 和 experience_summary 均为空字符串，reply_text 为非空字符串，没有额外字段。[脱敏采样记录](samples.json) 来自当次实际输出，不是手工构造的 Provider 回答。没有采样到可用于修改 Adapter 的异常格式。

命令 `.\.venv\bin\python.exe .scratch\s20_relationship_probe.py`，6.05 秒，退出码 0。helper 只观察 HTTP 状态、字段类型/长度、闭集 event 和受控错误类别，不保存原始响应、请求认证头或 key；不改变响应、不重试、不写 Runtime。四次之后停止，没有继续请求直到挑到期望结果。

这不是原故障的成功重放，也不是新的 UI/全能力长链验收。诊断按 `diagnosing-bugs` 的证据门槛停在未能建立原故障可重复信号的阶段，没有据此猜测和实施修复。

## 既有行为复核

`pytest -q -p no:cacheprovider --basetemp=<本次唯一临时目录> tests/test_relationship.py tests/test_composite.py`

结果 **28 passed in 20.33s**。覆盖关系成功、无更新、非逐字证据和闭集事件拒绝、重启恢复、关系失败不掩盖或取消其他能力等既有行为。本轮没有产品代码变化，因此未重跑全量；364 passed 是 Slice-19 的既有全量基线，不冒充本轮新全量。

没有把失败改成 NoOp、没有放松字段或事件验证、没有增加重试/日志体系/Provider 请求，也没有增加历史外发。原故障仍列为待跟踪事实，后续若再出现，应在相同最小投影下先收集受控错误类别，而非预设某种根因。

## 下一项主要工作：待授权的近期对话范围

以下是供用户确认的最小数据用途提议，**尚未实施、尚未获得此项外发授权，不是当前执行任务**：

- 仅在 Living Memory 的现有 reply 请求中新增 `recent_dialogue`，来自当前 identity canonical Timeline 最近最多 2 个完整已提交对话轮次；每项只含 `{user_text, assistant_text}`。
- 合计最多 4,000 字符，超额按完整轮次减少，不拆句截断；不发送内部 ID、时间戳、状态说明、数据库行、未提交操作或其他身份内容。
- 仅用于理解指代和当前续写。历史 assistant 文本不作为事实权威、状态证据或新的持久 Memory；六类 proposal/classification 和其他 reply 不获得历史。
- 更正/遗忘不能因上下文重新外发而失效；无法安全确定内容可再次使用、身份不明或历史完整性不成立时，不发送历史，允许澄清/无历史回退。具体筛选与验收须在下一张任务书中落实。
- 不增加 Provider 调用，不触及正式身份做开发验收，不引入 Lifeworld/Agency/主动消息。

这项授权需要用户明确确认；“同意产品方向”不能替代历史文本的新数据用途授权。
