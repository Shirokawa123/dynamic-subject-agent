# Slice-97：角色定义与连续聊天的可审准备

已交付只读定义预览及[具体用途方案](../../plans/character-continuity-consent.md)。本片远程调用0；累计30/200，剩170。未保存正式Source Draft、封存/切换身份或发送真实聊天历史，连续聊天和生活尚未完成。

## 结果与发现

Facade验证现有人物资料后生成完整内容映射、派生来源声明和自持运行资料。真实v9包含30条已纳入认识、12条排除/待核，形成10项候选（2项Genesis、8组Knowledge）、1887字符派生文档。限定和事实/信念类型保留；排除信息及原文证据只留本地追溯，不进入运行资产。角色起点为当天预告直播前，已有此前插画与直播经验，与现实用户没有既有共同经历。

核查正式封存发现旧LocalIdentityAuthority、Studio PolicyKernel和isolation proof仅支持project-original。把小说派生资料套入该路径会错误声明原创。本片不扩来源权限，而将source/save/freeze请求置空，标execution_ready=false、original-only-freezer和content_mapping_only；旧mapping basis不是可执行批准。独立definition basis绑定准确来源/用途、人物/起点和运行资产，所有确认仍为false。批准后需先实现并验证正确来源路径，实际内容必须与批准包一致。

本地结果（Git忽略，不上传人物全文）：

- `.local_indexes/eromanga-sensei/s97/identity-review.md`：可读定义。
- `.local_indexes/eromanga-sensei/s97/identity-preview-v3.json`：最终未确认包；前两份仅为迭代预览，不是批准对象。
- definition basis：`6e68a0c76f938b81d8908214604a53a2fdc0b1dcbd459cfdf39ae75a88246957`。
- runtime asset SHA：`27a04840632e75d462d8cbf4dda300ef7adf570d9a270ad91aec5143b7732f3e`。

## 验证

Sol high完成15项新行为检查，另4项兼容检查通过，共19个唯一用例。覆盖完整内容/时序/信念限定、未来与未核项排除、来源及选择变化绑定、超限拒绝而非截断、重复/重启稳定、canonical/Studio文件不变、Provider零调用、旧请求不可用及确认未伪造。兼容检查为source_character_authoring中的deterministic_exact_and_read_only、basis_changes_with_selection_revision，character_evidence_model中的retrospective_evidence_can_support_prior_self_knowledge_without_sealing、context_invalid_request_and_changed_source_are_not_empty_success。

主窗口检查最终代码、只读调用链及真实v9导出；git diff --check通过。子agent线程总额已达上限，本片没有新上下文独立reviewer，不冒称独立复核。以上是准备流程正确性的证据，不证明人物语义已经完美或MVP已验收。

## 停止点

需确认本定义的私人派生建角用途、独立身份，以及真实聊天本地保留和同一Provider最多2完整轮/4000字符的历史用途。这来自仓库新数据用途审批规则，200次调用额度不替代新用途许可；不再逐批申请同范围次数。下一片应直接推进来源正确的身份与连续聊天，不再追加单轮实验作为默认主线。
