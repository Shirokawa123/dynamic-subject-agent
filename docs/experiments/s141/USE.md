# 使用S141候选入口

本机入口：[http://127.0.0.1:8791](http://127.0.0.1:8791)。这是新独立的self-directed-activity人物分支，已0模型启动，空聊天、无pending、活动未开始；首次验收的方案和聊天没有预灌进去。原8790及记录继续保留，原双击CMD仍打开原入口。

展开“经历与构图”，无需先聊绘画或选定经历即可明确推进一次文字活动；查看实际方案和取舍，再推进下一步或回聊当前结果。也可正常聊天后选一条已提交用户原话作共同经历。暂缓是合法结果，结构失败不会制造新方案；本入口仍可能遇到空白，失败后不自动重试。它只形成文字方案，持续生活/主动分享尚未开启。

本轮候选的一次真实链完成了自行构想、重启后具体修改、最终方案回聊；另一候选首请求失败，当前版也能自行开始。因此这是可体验的有限候选，不承诺稳定人物生活或完整MVP。刷新、状态、预览、查原请求、重开都是0模型；用户明确发送或推进一次才按既有用途请求模型。

需要手动重开同一候选入口时，在仓库目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_shared_activity_chat.ps1 -Python 'D:\anaconda3\python.exe' -Port 8791 -TechnicalVariant self-directed-activity -DirectProvider -NoBrowser
```

命令复用当前候选root，不就地切换旧root；启动器检查准确health，未知或被其他服务占用时关闭失败。`-DirectProvider`只对此进程直连既有DeepSeek HTTPS，不改系统代理、slot或TLS；`-NoBrowser`不打开页面焦点，需要时直接访问上方链接。没有安装新环境、迁移聊天或启用自动后台。
