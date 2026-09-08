# 调用方式、版本及重启证据

## 版本和隔离

开始时 `git status --short` 无输出。HEAD 为 `37258f31d30a6a96174f9d67e89cdb305de8a33d`，与用户预期一致。本地实际导入 `E:\dynamic-subject-agent\src\dynamic_subject_agent\local_product.py`；build 常量、初始状态和重启后状态均为 `dogfood-s22`。

全新临时目录 `C:\Users\30252\AppData\Local\Temp\dsa-ux-20260908-0912` 在启动前检查不存在。仅给本次服务子进程设置 `LOCALAPPDATA` 指向它。生产组合在其中创建默认 Avery 身份，初始 `/api/state` 的历史和记忆均为空，identity 为 `8da2560e-0ffa-4648-a890-234e070dfe46`。

没有读取 `%LOCALAPPDATA%\DynamicSubjectAgent` 的正式数据，没有从旧测试或救援仓库复制身份。运行数据库位于临时目录，不在 Git 提交中。

## 后台调用

使用现有解释器及入口：

```text
E:\dynamic-subject-agent\.venv\bin\python.exe -u app\desktop\server.py
```

工作目录为本仓库；PowerShell `Start-Process -WindowStyle Hidden` 启动，stdout/stderr 重定向到上述临时目录。没有运行 `shell.py`、没有打开页面。服务使用现有 `DesktopState`、`WindowsCredentialStore`、`DEEPSEEK_CREDENTIAL_SLOT` 和默认 production product factory。

初始 `/api/setup` 返回 `configured=true`、`product_ready=true`、`provider_id=deepseek`、`problem=null`、`verification=not-run`。没有主动调用保存/验证/删除凭据接口；鉴权由原生产路径内部完成。代码配置的模型为 `deepseek-v4-flash`，没有覆盖默认模型、cognition、gateway、transport 或输出。

一次性客户端在临时目录内，仅用标准库向本次 loopback 端口请求：

- `GET /api/setup`：只读状态。
- `GET /api/state`：本次隔离身份的状态投影，初始、重启前、重启后、最终各一次。
- `POST /api/turn`：一次一个 `{"text": "当前用户原话"}`，共 18 次。上一轮返回并阅读后才构思下一句。

客户端不接触 Provider endpoint/key，也不构造 recent_dialogue 或跨能力投影。它保存原始 JSON 响应和 `perf_counter()` 计时，不加工应用表达。输出到工具时省略增长中的历史数组以便阅读；[raw](raw) 内仍保存完整数组、说明和引用。请求名存在时在发送前拒绝重复调用，未对失败轮次重发。

没有在 Gateway 上安装观察钩子，故无逐 Provider 请求字段/次数审计；本次严格使用未修改的现有生产实现。停止服务之后，仅对四条真实输入运行现有本地纯谓词，记录在 [cause-checks.json](cause-checks.json)，没有再次调用应用或 Provider。

## 顺序与真实重启

| 时间（上海） | 事件 |
| --- | --- |
| 09:10 左右 | 开始核对文档与版本 |
| 09:11:42 | 进程 14588 启动，端口 62267 |
| 09:12:56 | 初始状态证明新身份、空历史、空记忆 |
| 09:13:09–09:16:03 | 完成 T01–T06，自然分享、讨论、一次配文失败、换题 |
| 09:16 左右 | 首段原文写入 FIRST-SEGMENT.md 后才打开旧报告 |
| 09:16:50–09:18:43 | T07–T09：事实疑问、材质未知、选择不做试验和短暂停下 |
| 09:19:16 | GET 重启前状态；在全部九轮提交后结束进程 14588，WaitForExit 确认退出 |
| 09:19:16 | 用同一数据目录启动进程 35280，端口变为 61565 |
| 09:19:36 | GET 重启后状态并逐项比较 |
| 09:19:52–09:24:34 | T10–T18：继续、省略式总结、新虚构场景、创作/改写、更正、遗忘与矛盾追问 |
| 09:25:19 | 保存最终状态，结束进程 35280并确认退出；保留测试数据 |

重启使用 `Process.Kill`，不是优雅关闭；操作前没有未完成的 HTTP 请求。新进程不是旧进程中的 reopen。`restart-process.json` 保存两次 PID、真实时间和同一根目录；`restart-comparison.json` 显示：

- build、profile、identity selector、九轮完整 history、Memory、目标列表、中期状态均相等；
- history 包含 T04 的首次失败原话，说明和引用字段也参与逐项比较；
- history 序列化 SHA-256：`c7a98051e1ce01da2603935e2541c7c271ec6007d1ddec173c7e785cd18e0586`。

T10 在新进程中完成，并准确归纳 T09 的保存步骤。没有改系统时钟、注入假时间或等待跨日；服务停止到重新启动很短，不能用这次结果声称验证了长时间离线活动。

最终 [cleanup.json](cleanup.json) 记录进程退出和数据保留。附带 TCP 连接检查未连接成功，仅作补充；停止的主证据是所启动进程的退出确认，不把连接超时本身当作关闭证明。

## 计时口径

每轮从本地 HTTP 请求开始至完整响应体读完计时，含生产模型调用、本地裁决及提交；不含写下一句、模型体验者思考和工具返回等待，不是单次 DeepSeek 请求延迟。

18 轮总请求等待 155.19 秒，中位 8.18 秒，最短 T16 为 6.14 秒，最长 T08 为 13.96 秒。每轮完整精度见 raw 中的 `elapsed_seconds`；失败的 T04/T13 同样计入，无挑选样本。

| 轮次 | 秒 | 简述 |
| --- | ---: | --- |
| T01 | 11.1142 | 旧票分享 |
| T02 | 10.1791 | 澄清舍不得的意义 |
| T03 | 8.8988 | 讨论保存与叙事 |
| T04 | 7.5196 | 配文未完成 |
| T05 | 7.9986 | 分析体验者自拟文案 |
| T06 | 7.6073 | 换题雨天城市 |
| T07 | 10.4965 | 偏色与物理解释 |
| T08 | 13.9616 | 材质未知与保存建议 |
| T09 | 8.5285 | 选择保存步骤与明日打算 |
| T10 | 7.5791 | 真实重启后总结前文 |
| T11 | 9.0821 | 新面馆场景讨论 |
| T12 | 7.1145 | 创作招呼语 |
| T13 | 6.6562 | 缩短台词未完成 |
| T14 | 7.9406 | 更正颜色 |
| T15 | 8.4852 | 按新颜色建议书签底色 |
| T16 | 6.1404 | 请求忘掉名字，未改变 Memory |
| T17 | 7.5232 | 再次使用名字 |
| T18 | 8.3669 | 指出矛盾后的回应 |

这是一段约 11 分 25 秒的真实连续会话，中间含重启和体验者阅读/组织下一句。整个任务另含文档核对、报告与 Git 交付，不能把请求耗时总和当作任务总耗时。
