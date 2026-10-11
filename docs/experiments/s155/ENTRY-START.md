# S155 独立自然反馈入口的具体启动动作

状态：待用户明确批准；准备、初始化、临时 Fake HTTP 验证均不是常驻启动批准。

批准后只在同一本地仓库执行一次 `scripts/start_natural_feedback_chat.ps1 -Python D:/anaconda3/python.exe`，隐藏窗口启动本仓 `serve_natural_feedback_chat.py --port 8796`。启动器固定 `PYTHONPATH=src`、`TEMP/TMP=.artifacts`，与已有初始化的隔离类别一致；不从其他临时目录环境直接打开该 root。服务只绑定 `127.0.0.1:8796`，准确 health 为 `{"application":"natural-feedback-chat-s155"}`；不弹浏览器，不注册系统服务、开机任务或调度。未知端口占用拒绝，不接管其他进程。

使用已零模型初始化的独立空目录 `.artifacts/s155/experience-entry`，保留其 exact pointer、人物和单 Timeline，不重新建角、不复制开发验收内容。启动前 Authority 核 active identity/Timeline/multi-span contract；部分目录、外来 pointer 或不合资格保留原数据并拒绝。打开、刷新、查读原 nonce、查看参考内容、预览下一步和重开都不调用模型。

普通发送和明确推进活动沿 S150 已批两用途及 S154 multi-span 技术资格：同已审人物材料、DeepSeek HTTPS、既有 Windows default slot；每次明确动作最多一次请求、零自动重试。来源选择/停用和历史开关由本地 Facade 裁决。没有计时推进、自动分享、后台生活或通知；本入口只提供手动文字构图和接话。

当前自动修订覆盖明确引文旧词→新词；含糊指称可以询问/讨论，未独立确定范围不执行。原 before≤160、after≤240、总项数≤4、唯一且不重叠、完整目标覆盖与所有非目标字符逐字保护保持。通用自然指称自动定位、自由语义编辑、隔日连续生活及实用户人物体验尚未证明。

启动后只读核 health、同 pointer、空聊天、activity revision=0、audit=0，并记录回执。旧入口、旧 root、用户草稿和全部失败保持；不迁移、删除或改写数据。用户后续点击发送/推进才会沿既有用途产生请求；启动本身不执行冻结开发场景。

需要确认的准确原因来自 [AGENTS.md](../../../AGENTS.md)：“后台运行/通知按具体已批准合同执行”，以及 [S155 当前任务](../../slices/slice-155-natural-feedback-entry.md)：“新8796持续启动另做准确review，未批不运行”。已有 8793/8795 批准不覆盖这个新持续进程。可审依据与零调用回执见 [S155 报告](../../reports/2026-10-11-slice-155/REPORT.md)。
