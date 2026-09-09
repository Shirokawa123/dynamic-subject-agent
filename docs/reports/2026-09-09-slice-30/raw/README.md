# Slice-30 原始验收证据

- fixed：head95–103，原遗忘查询、新计划、改述、更正与独立创作。
- restart：head104–109，同代码重启、改述、exact 遗忘及独立偏好。
- final：head110–114，3ad1468 后复验带条件记录与关系/状态组合；head110、head114 的失败保留。
- 每个 turn JSON 是当前消息和完整 Desktop HTTP JSON 响应；before/after 为 `/api/state`。UUID 统一替换成 `<internal-id>`。
- memory JSONL 是本地诊断包装从 Memory 公开 DTO 记录的实际 active/selected 内容与 reply 类型，调用原 Provider 并原样返回结果，没有改变请求或增加调用。凭据、ID、思维不在日志中。因而本轮可以核对实际被选中的内容，不仅是召回数量。

模型输出不是验收判定；HTTP ok 也不等于回答准确。具体判定与版本区别见上一层 REPORT.md。诊断脚本仅保留在本地忽略的 `.scratch/s30_server.py`、`.scratch/s30_live.py`；稳定回归入口是 `tests/test_memory_grounded_answer.py`，通过 ApplicationFacade 检查新逻辑。
