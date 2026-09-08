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
- 新 plan/目标/承诺中的闭集相对日表达绑定 canonical Admission；原文不改写，Memory/目标卡和既有 Provider 投影可跨日显示明天、今天或昨天。
- 当前 sealed identity 的姓名、subject identity 与 canon start 只进入既有能力的 reply 阶段；有封存 voice 的身份可持续体现表达方式，无 voice 的 Avery 不伪装为已有性格。
- 四条明确“上次什么时候聊/多久没聊”查询由本地 Python 按当前身份 canonical Timeline 回答；不调用 Provider，不把间隔解释成离线经历。
- Situated State 的 focused/gentle/cautious、一次 carry、30 分钟绝对过期与重启恢复（STABLE）。
- Medium State 的 settled/concerned/encouraged、双独立证据、冷却、窗口与重启恢复（STABLE）。
- 六项能力可在同一原子轮次并存；任一 Provider 子能力故障只形成该项 FailedClosed，其他无依赖能力继续裁决与回复（STABLE）。
- Windows 页面以用户语言说明本轮形成、召回、保持或失败的既有能力结果；Python 发言预算避免目标样板和多状态重复，解释仍来自裁决后的 Outcome。
- 页面显示当前 dogfood build，并从当前隔离身份的 canonical Timeline 恢复最近 20 个已提交对话轮次；身份切换与重启不会混入其他身份历史，未完成操作不伪装成已完成对话。
- 直接状态命令和关系声称仍由 Python 规则保护，但主对话使用自然回应；内部裁决原因只显示在逐轮 explanation，不作为角色台词朗读。
- Windows 页面可将逐次确认授权的一份原创纯文本提取为带逐字证据的 Genesis/Knowledge 候选预览；提取预览本身不保存、不封存、不修改既有身份。
- 用户可选择候选并显式保存为 SubjectStudio 内未封存草稿；支持重启恢复、选择 revision 和显式删除。保存与删除均需单独确认。
- 未封存草稿可生成 exact Profile/Genesis/Knowledge 映射和稳定 Freeze Basis；用户再次确认 exact basis 后可幂等创建新的来源封存身份。原有身份不被替换，两个身份使用独立 QRI、Knowledge snapshot、Host 与 Timeline，并可显式切换和跨重启恢复。
- 软件内配置 DeepSeek key，安全保存到 Windows Credential Manager，并支持验证、替换和删除。

当前最小产品范围已完成 Windows 隔离身份真实长链、project-original 纯文本建角封存、多身份切换与重启验收。下一项能力需重新定义切片；视频/音频、私人来源、Agency、effect、人格发展、Reflection 与主动消息不在当前范围。

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

当前内部体验 build 为 `dogfood-s28`。逻辑遗忘停用活跃使用，原历史保留；当前不提供定时或下次自动提醒。记忆回答区分本轮选中范围与全库存，可用精确原文只查状态，但不保证模糊题材检索命中。事实遵守封存来源边界，共同创作/限字/编号修改仍为有限契约。详见 [Slice-28 报告](docs/reports/2026-09-08-slice-28/REPORT.md) 与 [架构契约](docs/ARCHITECTURE.md)。

产品定义见 `docs/PRODUCT.md`，架构见 `docs/ARCHITECTURE.md`，当前唯一工作见 `docs/slices/current.md`。
