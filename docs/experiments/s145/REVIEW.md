# S145：当前构图工作理解的新增用途审阅

2026-10-09批准承接：用户对绑定下述准确basis的集中问题明确答复“同意”。新增LIVE与首验由[S146](../../slices/slice-146-working-understanding-live.md)执行，原review.json的not-granted及Pending/LOCAL保持原对象，不直接转为发送资格；批准事实见[用户决定](../../plans/character-chat-direction.md)。下文保留准备时状态。

2026-10-09。独立LOCAL实现与实包整链已完成，**未获新用途批准**；原S139/S142 E1/三用途和S144技术开发批准不被扩用。准确对象已在[review.json](review.json)冻结，basis `e87c9db1f6f52409faee497ca05f0852362add519e461d48f50bee27d760977c`。source/runner/实际metadata最终复核由主窗口接纳，本文件不自行授权发送。

## 这次要改变的行为

把两次真实提交交流和已有文字活动放在一起，形成一条可修正的当前构图理解。近期对话窗口淘汰后、重启后，后续活动仍能参考这条理解改变方案，结果再进入交流；错误或停用要让整条派生链退出使用。范围限当前工作，不形成永久用户画像、关系或人格，也没有自动逐轮归纳/Reflection。

## 准备请求的准确范围

新的独立开发身份和root，同已审纱雾30事实/4作者解释最小背景、现有DeepSeek及Windows默认 `(deepseek, default)` slot，三个新purpose：

| 显式触发 | 输入 | 输出与本地成立条件 |
| --- | --- | --- |
| 形成一次当前构图理解 | 同最小background；固定scope composition-text；2条不同committed用户轮的连续逐字原话，各≤400，标签U1/U2；至多1个已提交独立构图文字方案A1或null，subject≤160/composition≤800/focus≤400 | exact status formed/insufficient、scope、statement≤240、basis_refs。formed必须引用U1/U2，A1只在实际提供时可引用；全部实际输入保留依赖。Python核出处/范围/结构/权限后原子提交tentative理解；语义忠实还需真实内容检查。insufficient为typed NoOp，保留原有效理解 |
| 明确推进一次活动 | 原最小background、phase/allowed_actions、当前已提交plan；shared_experience固定null；新增最多1条W1，含scope/statement≤240与形成时2原话/A1支持 | 原有限action/plan/reason_code/basis_refs/decision_note≤160，新增可引用实际W1；裁决阶段、真实字段差异与所有传递依赖后提交。note仍仅本地，不能重新送模型 |
| 手动普通交流与结果接话 | 原current≤1000、最小background、可关闭2完整committed轮合计≤4000，以及当前activity_result；shared_experience固定null；新增最多1条有效W1及同一原支持 | 沿S144自然最终正文、Python原文封装reply_text/language，非空≤1200/NUL/完整性等原裁决保持；不从reasoning补答、不重试 |

W1支持中的A1是形成时真实提交的文字方案快照，不是图片、外部反馈、过去全部活动或decision_note。无内部head/profile/timeline/event ID、日期或依赖hash发送；原引用和版本关系只保本地。由旧W1派生的方案不能反向形成新W1来绕过替代或撤回，本片保守拒该来源。新资格不取得旧E1选定/停用能力，pure builder兼容字段shared_experience恒null；当前result不夹带额外历史。

## 控制、保留与停止条件

形成、停用/更正和活动都由明确操作发起，普通交流只因手动发送触发；每stage最多1请求、0自动重试。独立新资格/3purpose审计，旧身份/入口/草稿不迁移、不改默认入口；首次真实验收另用新自有开发root，原canonical原文保留。

停用/替换、history-off/cutoff和权限变化同时移除理解、派生plan/result及完整相关旧轮/传递lineage。模型引用不是权限：即使少写refs，所有实际输入依赖仍保守继承。prepared发表前重核scope/版本/来源；原nonce或冷恢复不重新请求模型，未知/损坏不能当空库存。

不开新后台生活/通知/云，不新增原书或其他私人材料，不改Provider/key用途，不自动人格重写/Reflection，不物理删除或迁移旧记录。跨天只证明真实观察到的范围；LOCAL模拟D+1标签不等于日界逻辑或离线继续生活验收。

## 冻结前所需证据

完整LOCAL实际ModelTask/精确wire保在新自有忽略目录，仓库只保存安全状态、计数、哈希、政策和助手原创场景。`run_s145_local_review.py`先验source原话及typed A1与canonical对应，再核每form/choice/reply preview==actual；首失败保任务/状态/错误类型，不补抽。`prepare_s145_review.py`从这些实际任务直接形成pure wire和Pending拒绝证据，不另造一套样例。

review.json冻结后绑定人物最小资料、LOCAL合同、scenario、helper与actual任务/policy/wire摘要；原审批状态not-granted保持，后续批准由方向/current准确承接。Pending Adapter没有transport/credential路径，LOCAL在registry前拒remote。当前无可执行LIVE grant。

## 获准后的固定首次场景（尚未执行）

协议参数来自15个实际LOCAL任务的同一pure serializer：HTTPS `https://api.deepseek.com/chat/completions`，deepseek-flash，max_tokens4096、thinking enabled/reasoning_effort high、非stream、timeout30秒；form/choice为JSON object，reply为自然text且不带response_format，最终正文无语义变化封装，保非空/1200/NUL/完整性裁决。未发送wire只保新自有root，不把背景或响应全文复制到仓库。

[首次真实场景](live-scene.json)：新独立身份，2条原话交流→独立一次choice新方案→两原话/实际方案形成理解→3轮换题→关闭重开0模型→一次choice参考理解→结果回聊→原nonce查读0模型→明确disable0模型→实际禁用接话→2条新更正交流→形成新理解→新choice→同结果接话。最多15首次请求（10普通reply/3choice/2form），每stage1请求0retry；数量是本场景结束条件，不恢复旧全局次数限制。

首技术失败/完整性未知停止全部；首choice没有eligible新方案、form insufficient或理解越出当前范围、后续choice无实际变化，都记录首次并结束。没有备用分支或补抽成功，不提前规定真实模型的statement/plan/reply。重启真实关闭打开；不靠模拟标签宣称真实跨天，实际日界/离线生活仍另验。

## 实际LOCAL与禁发证据

新自有workspace资源 `.local_indexes/s145/local-review-20261009-3` 上，原已审纱雾包经精确预览/freeze进入新身份，15个合成任务（2form/3choice/10reply）、19个完成步骤及12个完整行为check通过。原话退出最近2轮、关闭重开0任务、真实方案字段变化、同结果回聊、disable及实际旧链过滤、新2原话更正/新方案回聊均核实际输入；这是工程运行证据，不是人物因果/自然度或真实跨天通过。

15份wire的system与user逐值等于实际LOCAL policy/payload，三purpose齐备且所有E1null。Pending逐项拒15次，0transport/credential；完整exact任务和wire保同目录、public onlymetadata。实际LOCAL exact SHA `aff1286768d2ce995bf43f67982dabc1407a58142026aa8a0a6bd00e5959d214`，wire资源SHA `c78441ad8f0f1b6e2dd49c3dbd9df22f83d6b6e7639291ae1df338cfb5c1395a`。原root1沙箱0任务失败、root2同文误lineage12任务中断均完整保留；修actual selected head后才跑root3，不改场景挑成功，详见[完整报告](../../reports/2026-10-09-slice-145/REPORT.md)。
