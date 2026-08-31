# 仓库协作规则

默认使用中文与用户沟通。

## 权威顺序

1. `docs/PRODUCT.md`：产品目标、v1 和非目标。
2. `docs/ARCHITECTURE.md`：Module、Interface、持久化与失败语义。
3. `docs/DECISIONS.md`：少量当前决定。
4. `docs/STATUS.md`：已实现能力与当前缺口。
5. `docs/slices/current.md`：唯一可执行工作。

发现冲突时停止实现并向用户报告。旧救援仓库仅在当前切片明确要求迁移既有行为时按具体文件查阅，不是运行依赖或默认上下文。

## 会话协议

- 开工前必须存在 `docs/slices/current.md` 任务书；任务书外发现记入收尾，不扩权处理。
- 同一时刻只有一个执行切片；每张切片以用户可体验结果收口。
- 每个工作会话以 git commit 结束；每个切片收口后必须 push 已配置远端。无 remote 时保留完成提交并请求用户提供地址，不擅自创建远端。
- `docs/STATUS.md` 只追加或更新不超过 5 行的当前事实。
- 删除、不可逆数据迁移、新 credential 用途、新 provider 数据用途必须先获用户批准。

## 产品顺序

当前最小产品范围已完成：Memory、Knowledge、Relationship、参与者目标与承诺、Situated State、Medium State、六项同轮原子整合、Windows UI、持久身份及隔离身份真实长链/重启验收。下一项工作必须先有新的用户目标与切片任务书；Agency、effect、人格发展、Reflection 与主动消息不在已授权范围。

文本来源建角预览已完成：只生成未发布、未持久化的 Genesis/Knowledge 候选；封存、身份创建、视频/音频和私人来源仍需新切片与授权。

## 永久不变量

1. 一条 RuntimeTimeline 只有一个写入者与一个 canonical store。
2. Publication 原子且具有崩溃恢复语义。
3. `unavailable`、typed `NoOp`、`FailedClosed` 严格区分。
4. 模型只提议，Python 裁决；模型输出不能直接成为持久状态。
5. Provider 只接收当前能力获授权的最小投影，并由行为测试守护。

## Module 与测试

- 只有 `ApplicationFacade` 是产品业务 Interface；`open_local_product` 是 production composition root。
- 所有含糊模型任务只通过 provider-neutral `ModelGateway.execute(ModelTask)`；Domain 和 composite 不 import 具体 Provider。
- 明确查询与产品闭集语法优先由 Python 处理；Adapter 只规范化无语义差异的格式变体，状态变化仍由 Domain 裁决。
- 六项 Provider 子任务分别经 ModelGateway；单项故障作为所属 Domain 的 FailedClosed 片段提交，不终止其他无依赖能力。
- 桌面 Adapter 不直接装配 Studio、QRI、RuntimeHost、provider 或 canonical store。
- Interface 是测试表面；保留新逻辑行为测试、既有能力随迁测试和五条不变量测试。
- 不建立 guard/mutation/证据生成/多环境矩阵等新测试类别。

## Provider 数据边界

- Living Memory：当前消息 1 条 + 最多 20 条 active `{memory_id, content, source_user_message_id}`。
- Knowledge：当前消息 1 条 + 最多 6 条 sealed `{entry_id, title, content}`。
- Relationship：当前消息 1 条 + 当前立场摘要 + 固定策略版本。
- 参与者目标/承诺：分类发送当前消息 + 最多 20 条 active `{turn_ref, kind, terms, status}` + 固定策略；回复使用当前消息且只附加本轮选中的最多 5 条 `{kind, terms, status}`。
- Situated State：分类发送当前消息 + 最多一个未到期 `{posture, remaining_turns, expires_in_seconds}` + 固定策略；回复使用当前消息且只附加本轮选中的 `{posture}`。
- Medium State：分类只发送当前消息 + 固定版本策略；回复使用当前消息且只附加本轮选中的 `{baseline}`。
- 文本来源建角：只在用户逐次确认权利与用途后发送单份 `{source_title, source_text, policy}`；source_text 最多 16,000 字符，仅用于未发布 Genesis/Knowledge 候选提取，不发送任何 runtime 状态或聊天历史。
- 六类投影分别发送，不合并；不得发送历史消息、数据库行、内部 ID、其他 Domain 状态、raw chain-of-thought 或 API key。
- `default` 使用 DeepSeek；其他 profile/provider 在单独任务与授权前保持 unavailable。

## Credential

- 远程 Provider key 按 `{provider_id, account_id}` slot 存入 Windows Credential Manager；固定命名由 credential Module 拥有。
- UI 只显示 configured/verified 状态，不回显 key；保存、验证、替换和删除必须由用户明确操作触发。
- key 只用于 HTTPS Bearer 鉴权，不进入源码、配置、SQLite、Timeline、日志、错误、模型消息或测试 fixture。
- secure backend 不可用时返回 typed unavailable；不使用仓库文件、环境变量持久化或明文 fallback。
