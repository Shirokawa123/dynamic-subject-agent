# Dynamic Subject Agent

2026-09-20：产品目标已对齐为有来源人物、连续虚构生活和自然聊天；当前运行代码仍是下述dogfood-s51基线。新方向先按[独立五情景原型任务书](docs/slices/slice-53-character-chat-prototype.md)验证体验，生活引擎、主动联系和全文人物解析尚未实现，见[产品定义](docs/PRODUCT.md)。

一个本地优先、具有持续身份和可验证变化过程的主体型陪伴 Agent。角色的记忆、知识使用、关系状态与后续主体变化来自有来源的经历；模型只提出候选，Python 负责裁决和原子提交。

产品语义不绑定具体模型：当前 DeepSeek 是第一个生产 Adapter；`ModelGateway`、任务契约和 credential slot 可接入后续云端或本地 Provider，而不修改 Domain 与 Timeline。

快速体验见[使用指南](docs/USER_GUIDE.md)，当前候选版验收与已知限制见[Slice-51报告](docs/reports/2026-09-18-slice-51/REPORT.md)。

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
- 新建身份支持显式主体文字任务：接受、澄清、暂缓、有限拒绝、修订与取消，和用户目标/承诺分开保存。
- 已接受任务可预览完整正文和精确文件位置，逐次确认后在应用专用目录新建UTF-8文本；支持重复确认保护、完成/失败回执与中断恢复。正文保存不调用模型，不覆盖或删除现有文件。

当前范围包括 Windows 隔离身份真实长链、原创纯文本建角封存、多身份切换、主体任务与一种受控本地执行。视频/音频、私人来源、人格发展、Reflection、主动消息、任意工具与对外执行仍不在范围内。旧身份保持原格式与权限，不自动迁移；新功能以新建身份验收。

## 安装与测试

Linux/云端离线开发的安装、全量测试、打包和HTTP联调见[云端开发指南](docs/cloud/start.md)。

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

当前内部体验 build 为 `dogfood-s51`。点击“主体任务”，填写任务说明和本地正文；模型只协商是否接受，保存须再点击“预览保存”，核对完整正文与路径后确认。起草可先在聊天中完成，再把选定成品贴入任务。已批准操作中断后可在任务卡点击“核对已批准的保存”，下一次提交也会先恢复。任务完成后显示本地文件路径；完成记录说明保存当时的结果，不监控之后的外部编辑。

旧身份仍可聊天，任务/保存能力按原权限显示不可用；使用新建身份体验新功能，无需手工改数据库。详见[任务协商报告](docs/reports/2026-09-18-slice-49/REPORT.md)、[保存验收报告](docs/reports/2026-09-18-slice-50/REPORT.md)和[架构契约](docs/ARCHITECTURE.md)。有限自然语法、生成失败与旧报告中的体验限制仍有效，不承诺任意自然表达都成功。

产品定义见 `docs/PRODUCT.md`，架构见 `docs/ARCHITECTURE.md`，当前唯一工作见 `docs/slices/current.md`。
