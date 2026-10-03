# S139：有据共同经历与构图活动的新增用途审阅

2026-10-03，当前未获新增出站批准。LOCAL完整链、来源控制/恢复边界、必要兼容检查及最终独立只读复核均已完成；本文件不是发送许可，也不把合成结果当作人物效果。

## 请求批准的具体范围

在新的独立开发分支，使用原来已审的纱雾30项事实/4项作者解释所形成的最小人物投影，沿现有DeepSeek及Windows安全凭据slot，新增下列两个用途。无需新凭据，不上传原书全文或旧用户分支，不迁移正式8788。

| 用途与触发 | 准确输入 | 模型输出与本地裁决 |
| --- | --- | --- |
| 明确推进一次构图文字活动 | `background`（原人物最小投影）；`shared_experience:{label:"E1",quote≤400}|null`；`current_activity:{phase,allowed_actions}`；`current_plan:{subject≤160,composition≤800,focus≤400}|null`。不发送近期聊天或事件 | `action,plan,reason_code,basis_refs,decision_note≤160`。Python核阶段、真实内容差异和仅本次E1引用后原子提交；说明仅供用户本地查看，不再送模型 |
| 主动发送普通聊天及活动后的接话 | 原`turn/background/exchange`：当前文字≤1000、历史开启时最多2完整轮≤4000。`evidence`精确为同一条E1或null，以及`activity_result:{kind,plan}|null` | 单个`reply_text/language`，只依据已提交文字方案接话，不把方案说成完成图片或外部事件 |

E1只来自本身份已经提交的用户原话，须本地明确选定一段连续逐字片段；不从助手话语抽事实，不生成永久人格或摘要。来源、判断、活动版本及相关完整聊天轮保留本地依赖；停用/换源、历史关闭和交流cutoff须同时移除依赖产物，不能只拿掉E1而让方案或旧回复绕回。过去记录保留，不物理删除。

每次发送/推进最多一个请求，0自动重试；在上述准确用途内沿既有无次数上限的开发批准记每次用途与结果。失败不写成虚构活动。不开启后台生活、主动分享/通知、人格重写、Reflection、任意工具、云端或其他Provider/credential用途。

## 实际本地预览

精确字段来自`build_choice_preview`/`build_reply_preview`，同一返回值已作为LOCAL `ModelTask.payload`执行并逐项相等，不是另写的一份示意请求。选择policy SHA为`38e151620ff9e59eaa948fd378d0a70d917b47d73c585aca59490cca76018a21`，接话policy SHA为`03f1e741159fc5a18e8fedc49aa56b17ed1ad48ec457baf64d2d3c5cf1fd800a`。

完整未发送样本保存在本机`%LOCALAPPDATA%/DynamicSubjectAgent/shared-activity-development/s139/local-review-20261003-1/exact-unsent-previews.json`，整份canonical摘要`2c86a706ed2b3b438228a8d3c902c435807c67eb18a5bbb5a63ab3e323607c69`。其中回复与方案明确是固定合成输出，只验证字段/流程；实际人物效果未验收。最终冻结若更改policy或payload，必须重新生成相应预览及摘要，不沿用旧值。

## 已实现但不可执行的远程请求

[准确审阅合同](review.json)的review basis为`8bb95a501eb44827e939ea41376cbda0eea6463a266b2983581d36f65494301a`，绑定原人物材料、两个purpose/policy、字段上限和六份样本wire摘要。`shared_remote_request_preview`直接序列化同一LOCAL builder的结果为两条messages；实测六份内容逐值相等，不重新调用任何模型。

固定HTTPS端点为`https://api.deepseek.com/chat/completions`，`deepseek-flash`、`max_tokens=4096`、thinking enabled、`reasoning_effort=high`、JSON object、非stream，timeout30秒，每次手动动作最多1请求/0自动重试。完整未发送wire保留在同目录`exact-unsent-wire-previews.json`，不把已审人物全文复制进本报告。

`PendingSharedActivityGrant`只允许unapproved，`UnapprovedSharedActivityAdapter`所有invoke都返回typed `shared-activity-use-unapproved`，没有transport或credential读取路径；LOCAL composition在读取registry前拒绝remote Adapter。六份实际样本均经此入口拒绝，0凭据读取/0远程请求。本合同还不能激活任何旧whole/LIFE Sender；获批后须以此准确basis建立独立可执行资格与用途审计，不能把preview对象当发送票。

## 获批后的首轮实际场景

[固定三支场景](scenarios.json)分别为相关配色/留白原话、无关便签习惯原话、同一相关原话在推进前停用。实际选定片段分别33/25/0字符，不是用户真实个人偏好。每支由真实已提交交流开始，至少3轮无关话题后重启，使来源离开两轮窗口，再明确推进一次并接话；活动前其他输入已在LOCAL逐项核对相同。

保留每支第一次结果，观察实际方案取舍和来源引用、重启一致性及接话对应。E1引用或自述“受影响”本身不能证明因果，单次样本不证明稳定效应；没有明显选择差异或遇到空白，就记录未达/技术中断，不挑好样本补抽。批准前这些新用途远程请求为0；普通“继续推进”不代替本项具体用途批准。
