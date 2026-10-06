# 使用本轮入口

本机入口：http://127.0.0.1:8790 。它是独立空历史人物分支，旧8788及记录保留，开发对话没有预灌进去。

打开 `app/desktop/Start-SharedActivityChat.cmd`。首版使用本轮同输入比较较好的natural-expression候选；这是有限样本取舍，不承诺通用人物忠实或稳定无空白。baseline仍可用独立root和CLI明确启动，不能对已有root就地切版本。

正常聊天后展开“共同经历与构图”：查看已提交用户原话，选定连续片段（最多400字），确认后明确推进一次活动；看到实际文字方案和当次取舍，再回聊天。可以停用经历；原记录保留，依赖它的方案和完整旧轮不再参与后续。没有选定经历也可推进本人的日常文字构图。暂缓、失败和没有新方案会直说；这里尚不产出图片或自动生活。

刷新、查询原动作、从记录重开都不触发模型。处理中可以写下一稿，结果不会发送或覆盖新稿。遇到未确认的交付先核原请求，不自动重发。

本轮本机代理127.0.0.1:7897未运行，因此正在运行的入口只对此进程直连既有DeepSeek HTTPS端点。需要同样方式手动重开时，可执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_shared_activity_chat.ps1 -TechnicalVariant natural-expression -DirectProvider
```

该选项不修改系统代理、不替换凭据、不关闭TLS校验；不指定时沿系统连接设置。启动器只选现有可用Python，不安装或迁移环境。用户当前草稿及历史从本机原分支读取，模型只收获批的有限投影，展开本轮内容范围可查看。
