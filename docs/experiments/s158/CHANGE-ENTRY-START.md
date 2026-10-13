# S158 统一人物入口：候选通过后的具体启动准备

本文件准备change-evidence入口的持续启动；尚未获用户批准。模型数据用途已由change-approval.json批准，不能替代本次8797常驻启动。准确初始化回执与启动basis在工程和真实候选核验后冻结。

拟一次执行：在 `E:/dynamic-subject-agent` 运行 `scripts/start_integrated_character_chat.ps1 -Python D:/anaconda3/python.exe -TechnicalVariant change-evidence`，隐藏启动 `serve_integrated_character_chat.py --port 8797 --technical-variant change-evidence`，只绑定 `127.0.0.1:8797`；health应为 `{"application":"integrated-character-changes-s158"}`。不打开浏览器、不抢占焦点；端口已有其他服务则拒绝，不接管或停止旧进程。

独立目录为 `.artifacts/s158/experience-changes/entry`，审计在同级 `audit`。零模型初始化新身份/同一Timeline，开发场景不复制到用户入口；所有旧root、失败、聊天和草稿保留。部分初始化/pointer不符拒绝，不能重建覆盖。启动环境为PYTHONPATH=src、TEMP/TMP=.artifacts及当前进程NO_PROXY含loopback/api.deepseek.com，与初始化保持一致；日志独占写入同级随机launch目录。

空入口初始生活暂停、分享关闭。启动/刷新/查询/重开不调用模型；用户发送聊天或明确开启在线生活/分享后才按已批用途工作。页面可见且持有租约时累计900秒在线机会，隐藏/关闭不补算；新文字方案才可考虑分享，每UTC8日最多两次、未回复时抑制，0自动重试。不创建系统服务、开机任务、通知、离线生活或隔日调度。

同已审人物/DeepSeek/default Windows Credential Manager slot，只作HTTPS Bearer；4096及全部原投影/修改保护不变。reply/share新增当前有效修订的有界变化证据（最多三字段/before160/after240/双来源有效），choice不新增字段。失败与未知如实显示，未提交草稿不得自动发送。

批准后仅上述一次隐藏启动，并以接口核health、同pointer/身份、空聊天/活动0/audit0及真实PID/日志，随后交付用户访问地址。默认桌面启动命令待主窗口确认候选后指向这一入口，内部候选名字不要求用户选择。

审批依据：[AGENTS.md](../../../AGENTS.md)“后台运行/通知按具体已批准合同执行”，以及[S158任务书](../../slices/slice-158-integrated-character-loop.md)“新增持续启动先完成可运行准备与具体审阅”。若候选未通过，本文件仍仅准备，不能据此启动或宣称可体验已交付。
