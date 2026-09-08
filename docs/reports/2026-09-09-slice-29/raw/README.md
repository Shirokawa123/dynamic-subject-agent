# 原始后台证据

这些 JSON 来自指定合成林柚身份的 loopback Desktop HTTP。turn 文件包含提交消息及完整 HTTP JSON 响应；before/after 是 `/api/state` 返回。UUID 统一替换为 `<internal-id>`，其余文本、状态、时间与轮次保留；这会损失跨文件 ID 对应关系，因此不能以这些脱敏文件独立验证同一 recalled ID 的具体内容。未保存 credential 或请求鉴权头。

- `baseline-*`：基线 b41874c / dogfood-s28，head56–77。
- `fixed-*`：c63c24c / dogfood-s29，重开后 head78–79。
- `continuity-*`：同实现，head80–86，含两轮清出近期上下文、更正及再次询问。
- `restart-*`：同实现重启恢复，head87–89；comparison 检查启动前后五个用户投影字段一致。head89 是保留的真实失败。
- `forget-*`：同实现，head90–92，含显式逻辑遗忘、后续询问与独立资料夹召回。
- `final-*`：28707c9 姓名回归修复后的重开与复验，head93–94；重启比较以 forget-after 为基准。head93 找回旧偏好；head94 未泄露旧安排但误说“还没定”，不能当表达通过。

本地诊断脚本保留在忽略的 `.scratch/s29_live.py` 和 `.scratch/s29_server.py`，没有新增产品命令或自动运行任务；可重复的确定性回归入口为 `tests/test_memory_retrieval.py` 与 `tests/test_memory_control.py`，均通过 ApplicationFacade。模型真实输出可能变化，不能把再次运行视作同一结果。
