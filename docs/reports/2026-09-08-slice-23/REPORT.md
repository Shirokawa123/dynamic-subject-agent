# Slice-23 诊断 checkpoint：遗忘缺少独立状态操作

2026-09-08。状态：**等待数据保留语义确认，未实现、未验收**。产品基线 `0dba933` / dogfood-s22，原已验收回归 404 passed；本次没有运行或宣称新的全量通过。用户授权的后两项“事实建议边界”“自然创作/改写”继续排队，未越序实施。

## 已确认

- 通过现有 ApplicationFacade submit/wait/query，固定外部 Provider 的 CREATE→NONE 返回，复现“我叫陆禾。”→自然遗忘请求之后姓名仍 active。首次结果 **1 failed in 0.97s**，断言直接检查活跃记录，不靠成功台词。这是报告结果模式的受控复现，不是声称获得了独立体验的 Provider 原始候选。
- `LivingMemoryAction` 仅有 none/create/revise；ExperienceDomain 只接受 create/revise 状态候选，其他动作 action-invalid；Timeline 的当前实现从 accepted Memory 派生 active，并经 supersedes 将旧记录标记 superseded，没有独立遗忘记录。
- 因此，未发现已实现的遗忘结果被投影丢掉的证据；仅修改成功台词或 recent_dialogue 截断，不能使原记录退出活跃使用。
- 架构规定普通遗忘只向前追加，物理删除 Host 是独立治理。实现需要明确区分逻辑停止使用与物理抹除，不能将“这里叫我访客”保存为假替代事实来伪装忘掉姓名。

## 推荐待确认语义（不是已实现契约）

本切片采用逻辑遗忘：由当前明确命令选定本身份记忆，Python 裁决并经单次原子 Publication 向前追加撤回结果，使其退出活跃召回和后续 Provider 投影；不更改旧 Timeline、不抹除运行数据库。确认表达读取最终 Outcome；对象含糊或失败时不确认成功。其他记忆保留，重启与幂等结果一致，不经旧修订链或近期文本复活。

还需要在任务书中定清：可撤回的对象范围、含糊/失败控制的后续投影策略、历史查询如何避免撤回内容回流，以及用户重新提供信息时如何区分新授权。不能将任意自然语言目标选择当作已经解决。

Provider 目标仍为零新增数据用途；优先本地闭集命令，不增加模型调用，不扩展其他能力输入。若后续方案确实需要新 Provider 用途，再单独请求授权。

等待用户确认“逻辑遗忘保留不可变历史”这一数据保留边界后再实现。如果用户实际要求历史原文也物理抹除，必须另行评估删除、完整性和恢复方案，不能默默用逻辑遗忘替代。

## 可重复失败

[复现代码](reproduce_memory_control.py) 暂放报告目录，因为它规定的是尚未获精确语义确认、尚未实现的预期，不加入默认通过基线，也没有 skip/xfail 将失败说成成功。确认后应转为正式 Interface 行为回归并先红后绿。

在仓库根设置 `PYTHONPATH=src;tests`，运行：

```powershell
$s23temp = Join-Path $env:TEMP ('dsa-s23-repro-' + [guid]::NewGuid().ToString('N'))
& .venv\bin\python.exe -m pytest -q docs/reports/2026-09-08-slice-23/reproduce_memory_control.py -p no:cacheprovider --basetemp=$s23temp
```

预期当前版本仍为 1 failed，姓名 active 断言失败。每次使用全新临时目录，不重用 basetemp 删除旧数据。没有真实 Provider 调用、凭据读取、正式身份读取、界面操作或测试根删除。产品源码保持不变。
