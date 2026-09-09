# Slice-30：记忆回答与可用记录一致

状态：completed。基线 fb28c36 / dogfood-s29；主要实现 a984437，最终代码 3ad1468，build dogfood-s30。**555 passed in 673.62s**。以下分别报告结构化回答通过与仍存在的自由表达/错误选择问题，不将所有 HTTP 成功计为体验成功。

## 根因与契约

先通过 ApplicationFacade 对照验证 reply 的实际输入：完整周日记录或空 tuple 均与预期一致，但两条不可靠自由回复原样显示，2 failed in 3.41s。按新 memory 类型重放仍先红（2 failed in 2.31s），再实现 Python 渲染路径。原始对照证明自由回复可与输入矛盾，不证明历史 head89 的具体选中对象；该旧记录只保留脱敏 ID。

具体方案先写入 [DESIGN.md](DESIGN.md)。仅在既有 LM reply 三字段返回中增加 memory 类型；有选中内容时保留完整原文，无选中内容时只说暂时无法确定，无法披露时说无法核实。普通 conversation/creative/activity 保持原路由；没有新增模型调用、输入数据、历史用途、统一表达层或 canonical 状态。其他能力组合用临时本地标记保留完整记忆依据和独立来源/目标结果。

## 阶段验证

- 首轮新失败与既有范围/来源回归：49 passed in 27.51s。
- 扩展组合、披露和边界对照：44 passed；唯一失败为预期 LM reply 提示哈希变化。输出明确显示其他 11 项相同；只更新 LM reply 对应哈希，保留其他基线。
- 提示哈希更新后新场景与字节基线 12 passed in 11.42s。Spec 审查追加三个组合回归先 3 failed in 4.15s，补齐后新场景及既有 composite 回归 31 passed in 41.80s。第一次全量因审查修复变更代码而停止，不记为通过；最终全量 **555 passed in 673.62s**，命令 `.venv/bin/python.exe -m pytest -q --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s30-final-full`。

## 真实后台验收与实际选择

仅使用已授权合成林柚根 `C:\Users\30252\AppData\Local\Temp\dsa-ux-retest-20260908`，验证 active identity 与所属路径后通过 production Desktop HTTP 提交。沿用原 Windows Credential Manager 的 DeepSeek 用途，没有保存或打印凭据，没有访问正式身份/旧救援仓库。

本地忽略的诊断启动器仅包装 DeepSeekLivingMemoryProvider 的公开 propose/reply 方法并原样调用 super：在本地记录 active/selected 内容、action、返回类型与文本，其他能力/Transport/请求完全不变。`*-memory.jsonl` 不记录 credential、内部 ID 或思维内容；包含已有授权 DTO 的合成原文，能直接核验本次选择对象。HTTP 原始响应中的 UUID 仍脱敏，不能依其数量推断对象。诊断包装没有进入生产源码。

| head | 场景 | 实际观察与判定 |
|---|---|---|
| 95 | 原星砂遗忘后询问 | selected 为空，类型 memory，输出暂时无法确定；没有再说尚未安排。通过。 |
| 96–99 | 新月港计划，插入两轮无关创作，再问当时哪天 | proposal 与 reply 均选中完整周六记录，类型 memory，输出完整引用；近期两轮只有创作。通过。 |
| 100–103 | 更正周日，再隔两轮创作询问 | canonical 新记录为「月港手册改为周日整理，不是周六。」，原计划 superseded；reply 只收到新记录，类型 memory，完整保留否定限定。通过。 |
| 104–106 | 重启后清出近期内容，用未参与设计的改述提问 | 启动前后五个投影字段相等；proposal/reply 都选中新月港记录，直接完整引用。通过。 |
| 107–109 | 显式遗忘 exact 新记录，再问安排与独立纸张偏好 | 月港标为 forgotten；问月港 selected 为空，答无法确定；独立浅绿色偏好正常完整引用并保留 Knowledge 来源。通过。 |
| 110 | 提供带条件的新雾桥计划 | 保存的 canonical 原文完整，但 conversation 自由确认说「周日先不安排，等校样到了再顺延整理」，把条件说得过于确定。**保留为失败，不算完整表达通过**。 |
| 111–113 | 同一雾桥计划分别与关系、短时及中期状态询问合并 | 新 memory 类型均完整引用「我周日整理雾桥手册，但目前没有校样，没收到就顺延。」并保留独立回执；修复后限定句未被删。通过。 |
| 114 | 加入相似题材后再次询问已遗忘的月港 | proposal 错选 active 雾桥记录，reply 实际收到雾桥并以 memory 类型完整引用。**这是候选错选导致的答非所问，不能计为正确回答或诚实未知**；没有复活月港旧记录。 |

共 20 次后台追加（head95–114）。fixed/restart 为 a984437 的阶段，final 为 3ad1468；不合并成一个版本成功率。所有验收服务已正常关闭并输出 CLOSED，运行数据保留。重启比较见 raw/restart-comparison.json。

## Standards

独立规范轴初审与 3ad1468 增量复核均无新增可行动问题；确认新增标记仅用于表达，关系/状态候选裁决和重叠 Memory 候选过滤仍保留。规范轴初审没有发现下面的组合问题，因此不以其通过替代测试。

## Spec

独立需求轴发现 1 项 P1：后续关系/Situated/Medium 合并会把包含「目前没有」的完整记忆当自由未知台词删除。三种 ApplicationFacade 场景均复现；第一次修正后两个状态场景通过，关系场景仍失败，进一步定位到更早的关系声称分支直接替换 Memory 表达及标记。3ad1468 同时修复早期替换和后续三处合并，需求轴增量复核确认 P1 关闭、无新增问题；最终真实混合场景也保留完整条件句。

## 局限

memory 类型不能证明模型选中了正确对象，head114 已证实无关记录仍可能被引用。模型误将记忆问题标为 conversation、当前新陈述/更正确认的自由表达（head110）、或生成失败走旧 fallback 时，不自动获得此结构化路径的保证。本切片不通过两句台词的过滤特例掩盖这些限制。不宣称通用语义检索、任意复合意图或完整连续对话已经完成。
