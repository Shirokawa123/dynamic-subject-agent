# Dynamic Subject Agent

一个本地优先、具有持续身份和可验证变化过程的主体型陪伴 Agent。角色的记忆、知识使用、关系状态与后续主体变化来自有来源的经历；模型只提出候选，Python 负责裁决和原子提交。

产品语义不绑定具体模型：当前 DeepSeek 是第一个生产 Adapter；`ModelGateway`、任务契约和 credential slot 可接入后续云端或本地 Provider，而不修改 Domain 与 Timeline。

当前产品支持：

- Windows 本地聊天入口；
- 跨进程持久身份与对话时间线；
- Living Memory 创建、修订、召回与长期/打算标签；
- 有来源的 Knowledge 检索与引用；
- Relationship Subject Stance 事件；
- Memory、Knowledge、Relationship 同轮组合。
- 参与者目标/承诺的创建、修订、终态变化与重启恢复（STABLE）。
- Situated State 的 focused/gentle/cautious、一次 carry、30 分钟绝对过期与重启恢复（STABLE）。
- Medium State 的 settled/concerned/encouraged、双独立证据、冷却、窗口与重启恢复（STABLE）。
- 六项能力可在同一原子轮次并存；任一 Provider 子能力故障只形成该项 FailedClosed，其他无依赖能力继续裁决与回复（STABLE）。
- 软件内配置 DeepSeek key，安全保存到 Windows Credential Manager，并支持验证、替换和删除。

当前下一步是 Windows 隔离身份真实长链与重启验收。Agency、effect、人格发展、Reflection 与主动消息不在当前最小范围。

## 安装与测试

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,desktop]"
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

## 启动

直接运行：

```powershell
.\.venv\Scripts\python app\desktop\shell.py
```

也可双击 `启动Avery.bat`。默认运行数据位于 `%LOCALAPPDATA%\DynamicSubjectAgent`，不写入源码仓库。旧救援仓库与既有正式身份不会被自动读取、迁移或回退。

首次启动会显示“连接 DeepSeek”：粘贴 key 后点击“保存并验证”。软件只向 DeepSeek `/models` 发送 Bearer 鉴权验证，不发送聊天内容；key 存入 Windows Credential Manager，不进入仓库、数据库或 Timeline。

产品定义见 `docs/PRODUCT.md`，架构见 `docs/ARCHITECTURE.md`，当前唯一工作见 `docs/slices/current.md`。
