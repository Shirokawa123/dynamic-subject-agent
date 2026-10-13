# S158：统一体验的三项准确出站用途（待批准）

本轮已完成独立LOCAL组合实现和原审核人物包的合成完整链。以下请求只审数据用途，不将本地合成结果称为人物通过。原S142/S150授权、S149/S154/S157技术成果继续有效；不为旧同用途或技术版本hash重复申请。

## 请求批准的最小差异

| 用途 | 本次具体变化 | 保持的范围 |
| --- | --- | --- |
| 自然反馈和普通接话 | 原S150反馈请求增加最多一条有效的本人分享原话 `evidence.latest_share:{text}|null`，允许其合法派生近期对话进入原两轮窗 | S1≤400字符，仅分享后两次成功普通轮；第三轮连同派生历史过滤。原当前消息≤1000、两完整轮合计≤4000、当前有效plan及F1≤400/E1≤400；不加重复activity_result |
| 在线后续活动选择 | 原S142在线选择增加原S150已具备的最近有效反馈 `current_feedback:{label:F1,quote}|null`，并允许使用反馈派生的当前plan | 原页面在场累计900秒/暂停/需关注控制不变；共享来源最多E1≤400，phase/allowed_actions，plan各160/800/400。无整段近期聊天、S1或来源内部ID |
| 分享反馈后的方案 | 原share的 `{action,plan}`允许是已接纳反馈派生的方案，保留本地来源失效依赖 | 字段不增加，不发F1原话、S1或近期聊天；只已提交start/revise方案，原E1/最小人物资料，share可false；true正文≤400，原每日最多2新话题/未回复抑制/分享开关保持 |

目的：同一个人物分享后能接住反馈，并在后续活动与再次分享中使用实际新方案。将几个旧字段并到一份请求不自动取得批准，因此这三个跨用途差异明确列出。

## 目的地、材料、协议与留存

- 只发已有DeepSeek HTTPS endpoint `https://api.deepseek.com/chat/completions`，模型 `deepseek-flash`；只用现有default Windows Credential Manager slot做Bearer鉴权。无新Provider、key、来源材料或外部评判器。
- 人物材料仍是已审和泉纱雾起点资料，沿现有最小selector取材；不是每次发送整包30条事实，不发EPUB、完整Timeline或其他身份。准确已审binding见[review.json](review.json)。LOCAL每轮实际输入完整样例保在本机，不复制人物长文到Git。
- 三用途单动作最多1请求、0自动重试、4096输出预算、JSON对象、direct final，所有原文字界限/唯一性/不重叠/完整“其他照旧”保护保持。choice-final已有S157诊断证据；组合feedback与share的真实输出质量仍未验，不能由参数沿用推断可靠性。
- 用户消息只在明确发送后提交；预览和查读零调用。后续开发总次数沿用户已取消上限的决定，每项验证预先写范围/结束条件，保全部首次结果；旧失败不重发，不按次重新申请本用途。
- 模型只提议。回复可依赖S1；修订目标及全部结果由本轮明确引文与当前plan独立计算，不能从S1/代词猜编辑。F与原来源撤回时，派生plan/share/回复都退出后续投影；原canonical与失败保留。
- 新增用途批准后才接准确LIVE资格、审计与一次送达。当前composition在访问身份前拒绝任何remote gateway，预览模块无sender/凭据能力，不会借旧grant发送新投影。

## 可复核的实际准备

- [LOCAL合成完整链](../../../.artifacts/s158/reviewed-local-complete/metadata.json)：11合成提议、13canonical；澄清/长距精确修订/过窗/同人重开/实际新选择/再次分享/撤回过滤均通过，0remote、0credential。
- [分享后的首次反馈输入](../../../.artifacts/s158/reviewed-local-complete/tasks/05.json)、[带F1的后续选择](../../../.artifacts/s158/reviewed-local-complete/tasks/09.json)、[反馈派生方案的分享](../../../.artifacts/s158/reviewed-local-complete/tasks/10.json)、[同时含有效F1与新S1的接话](../../../.artifacts/s158/reviewed-local-complete/tasks/11.json)：每份包含实际Facade投影、未发送wire、明确标注的合成返回及摘要。
- [组合实现](../../../src/dynamic_subject_agent/integrated_character.py)、[统一页面Adapter](../../../app/desktop/integrated_character_chat.py)、[本轮工程报告](../../reports/2026-10-13-slice-158/REPORT.md)。文件与wire摘要绑定在review.json，不把合成回复当真实新场景输出。

## 不在本次批准对象内

新常驻入口启动、离线补算、系统通知、云/手机部署、更多材料、旧身份迁移/删除、人格重写和Reflection。本轮未请求启动动作：当前入口是LOCAL准备，准确LIVE接线完成后才有可审的持续启动对象。旧8793/8795/8796、用户草稿和已终态真实场景不操作。

待用户确认：批准以上三项准确用途，随后在同一S158内继续LIVE接线与新场景完整验收。review.json的review_basis为此次审阅对象标识；没有答复时不发这三项新用途。
