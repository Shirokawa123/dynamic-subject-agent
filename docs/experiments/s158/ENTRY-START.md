# S158 持续相处入口的具体启动动作（草案）

状态：用途已获批准；此新常驻入口仍待单独启动批准。初始化、Fake HTTP与真实开发验收均不等于持续启动批准。准确文件hash及初始化回执由主窗口完成后冻结。

批准后在 `E:/dynamic-subject-agent` 一次执行 `scripts/start_integrated_character_chat.ps1 -Python D:/anaconda3/python.exe`，隐藏启动本仓 `serve_integrated_character_chat.py --port 8797`。仅绑定 `127.0.0.1:8797`，health为 `{"application":"integrated-character-live-s158"}`。不弹浏览器、不建系统服务、开机任务、通知或离线补算；未知端口占用拒绝，不接管进程。

独立体验目录固定 `.artifacts/s158/experience-live/entry`，审计目录固定同级 `audit`。以原已审人物包零模型初始化新身份及单Timeline；开发场景另根，不复制其聊天或方案。启动时校验exact pointer、active identity、Timeline和组合LIVE资格，部分初始化或身份变更保留原数据并拒绝。启动器保持 `PYTHONPATH=src`、`TEMP/TMP=.artifacts`，与初始化隔离环境相同。日志写入同级 `launch/<随机ID>`，不覆盖旧日志。

初始生活暂停、分享关闭、空聊天与空方案。打开、刷新、查询原请求、查看参考和重开0模型请求；只有明确发送或开启在线生活/分享后，沿用户已批S158三项准确用途工作。在线机会只在当前页面可见且持有短租时累计900秒，隐藏、关闭与重开不补算。真实新文字方案才可独立考虑分享；UTC8每日最多两条新分享、未回抑制分享、每阶段最多一次请求且0自动重试。失败按依赖闭合处理，不虚构活动或自动重发。

同DeepSeek HTTPS与现有Windows default slot；正文保持最小人物投影、当前文字1000、可关闭两完整轮4000、E1/F1各400、方案160/800/400、S1分享400及两成功普通轮规则。分享只取已提交方案，不额外发F1原话。全部原4096预算、精确文字修改界限和“其他照旧”保护保持。草稿留在独立s158-live会话存储，不读取或覆盖旧入口草稿。

启动前与启动后只读核同pointer/身份、empty canonical、activity revision0、audit0及health，并记录真实PID与日志路径。保留8793/8795/8796、旧roots与所有失败，不迁移或删除。启动不执行开发场景或隔日调度。

需要单独确认的依据是[AGENTS.md](../../../AGENTS.md)“后台运行/通知按具体已批准合同执行”及[S158任务书](../../slices/slice-158-integrated-character-loop.md)“新增持续启动先完成可运行准备与具体审阅”。已批准的三项Provider用途与旧入口启动批准不等于这次8797常驻启动批准。
