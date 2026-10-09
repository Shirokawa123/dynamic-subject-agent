# S147独立工作理解入口的启动动作

实现已提交`e63b8fb`，用户用途沿S146准确批准，本启动动作不新增模型数据用途。验收完成并交付后若用户批准，则由主窗口启动一次本仓启动器：

```powershell
powershell.exe -NoProfile -File scripts/start_working_understanding_chat.ps1 -Python D:/anaconda3/python.exe -Port 8794 -NoBrowser -DirectProvider
```

用隐藏窗口持续运行该本地应用进程，页面地址`http://127.0.0.1:8794`，health必须为`working-understanding-chat-s147`；只监听loopback。新空数据目录`%LOCALAPPDATA%/DynamicSubjectAgent/working-understanding-chat/entry`，明确variant/binding/profile/timeline指针与Authority核验，未知占用或部分初始化不覆盖修复。已运行旧8793和全部既有记录/草稿保持，不迁移或预灌验收正文。

首次启动、页面打开、刷新、查读与重开为0模型请求。后续只在用户明确发送、形成理解或推进活动时，按原准确三用途向现有DeepSeek发送最小投影，现有Windows默认凭据仅用于原HTTPS鉴权；停用为0模型。无生活计时器、系统服务、开机任务、通知、LAN或云发布，不保存或显示key。

本轮开发首景只用自有临时随机端口并在结束关闭，未因此启动8794。2026-10-08单独启动批准仅覆盖8793；按仓库AGENTS“后台运行/通知按具体已批准合同执行”，8794持续应用进程需本动作的明确同意。用户直接点击启动器也是该具体动作的明确操作，不要求额外模型用途审批。
