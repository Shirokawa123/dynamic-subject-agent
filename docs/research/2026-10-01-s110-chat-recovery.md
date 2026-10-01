# S110开工证据：普通话题与明确的上下文恢复

2026-10-01。用户结果、已见失败和可观察验收见[S110](../slices/slice-110-continuous-chat-recovery.md)。复用S109真实八/九轮失败链和来源投影调查，本轮重点是如何恢复可用交流而不改写历史。真实Provider调用0，无新依赖。

## 来源与取舍

| 一手依据 | 本次适用的机制 | 如何进入项目与验证 |
| --- | --- | --- |
| [Rasa 3.6.x官方Tracker源码](https://github.com/RasaHQ/rasa/blob/3.6.x/rasa/shared/core/trackers.py)，经Context7解析官方仓库并查询，随后直接核对源码 | `events_after_latest_restart`按最近Restarted分界；源码分别暴露ALL、AFTER_RESTART和APPLIED视图。事件记录与当前可用上下文可区分 | 在本项目既有canonical Timeline追加本地边界事件；只从该边界后选对话/share，不引入Rasa、第二store或其完整会话重置语义。核对重开、幂等及旧原话保留 |
| [Stanford Encyclopedia：Speech Acts](https://plato.stanford.edu/entries/speech-acts/) | 命题内容、句式与言语行为的作用并不等同；出现“目标/承诺”名词不能单独证明要求变更状态 | first-life不承接旧v1参与者目标管理的裸词触发；仍保留明确状态操作和隐私/撤回识别。用普通讨论与真实控制对照，而非特定问句白名单 |
| [S109来源监控/多轮研究](2026-10-01-s109-offline-route-evidence.md)及[实际Facade结果](../reports/2026-10-01-slice-109/baseline.json) | 人物说过的话不自动成为事实；失败可能在后续轮延续 | 保留use_life丢依据反例，不把上下文恢复冒充事实忠实修复；真实模型质量另验 |

Rasa文档摘录对restart使用“无历史”的简化描述，与其源码ALL视图容易混淆，故以源码区分事件记录和应用视图；不引用它证明本项目的持久化/权限保证。哲学资料只是解释“普通词不等于控制动作”的设计类比，不是通用意图识别算法，也不证明AI有心理或意识。

## 仓库证据与实现决定

- `first_life_dialogue`委托旧`is_dialogue_control`，其中目标/承诺裸词属于旧参与者状态语义。按路径区分这些名词与明确修改/记录指令，其他旧调用默认合同保持，不改模型wire或提示词。
- `Timeline._verified_dialogue_prefix`检查所有未出版Subject，终态控制同pending一样永久返回None。新增独立`chat-context-reset`的FirstLifeInput/LifeRecord kind，复用所有现有字段、prepared/Publication/恢复与expected-head fence；旧字段集和指纹不变，不做SQL schema迁移。旧二进制不认识新kind时拒读，部署前需明确升级所有读取进程，本轮不动运行服务。
- 新Facade DTO需`confirmed is True`，拒绝未确认或无效请求。确定性本地回复零模型/零额度，也不恢复生活故障或修改生活暂停/分享状态。边界仅来自已验证已提交事件，不能通过写registry或模型返回来建立。
- 只越过边界前已确认终态FAILED_CLOSED且有frozen basis的失败；pending、无basis、损坏或之后的新控制继续保护。对话选择、最后轮控制判断和S1分享选择都使用同一cutoff。
- 明确恢复操作重新确认既有范围：旧聊天/share不再进后续上下文，原记录保留；人物资料、已保存活动/方案继续可用于生成，新输入仍按已批准当前消息用途处理并与回复本地保存。它不是任意话题禁用、删除或人格遗忘；原型中“新话重述受限内容”不能据此宣称自动识别已解决。
- 当前真实控制在历史开/关均先本地阻断，不把关闭历史当消解控制意图。旧失败保护和正常普通消息的无历史交流分别验证。明确的本地恢复操作是新的安全边界，而不是清掉失败行。

不采用：registry单独计数（无法代表canonical边界）、清除旧失败/历史（未经批准且丢失证据）、增加每条问法例外（未解决职责混用）、先做通用语义话题禁用（新用途与更广依赖未定）、静默改v4事实投影（需版本/用途合同）。本次自建仅是既有Timeline的一种本地系统事件和只读筛选；标准库与仓库模块复用，不引入外部代码，故没有新增第三方许可/维护/凭据成本。

验收结束条件：真实Facade连续链的普通话题可通过；撤回0调用，明确确认后新首轮无旧对话/share、第二轮只有新首轮，正常重开一致；旧失败/记录保持，重复确认不重复出版，未确认/跨身份/未知完整性无恢复，旧prepared被head fence阻止。根据新增恢复路径补必要崩溃点检查，不用模拟回复证明自然度。
