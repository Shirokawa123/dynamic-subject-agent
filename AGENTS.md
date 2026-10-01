# 仓库协作规则

默认使用中文与用户沟通。

## 开工、权威与阶段

- 开工先读 `docs/slices/current.md`，同一时刻只有一个执行切片。按完整用户结果收口；任务书外发现记入收尾，不扩权处理。
- 权威顺序：`docs/PRODUCT.md`（目标与非目标）→ `docs/ARCHITECTURE.md`（实际合同）→ `docs/DECISIONS.md`（决定）→ `docs/STATUS.md`（当前事实）→ `docs/slices/current.md`（唯一执行工作）。明确后续决定只替代其对象和阶段；无法据此消解的冲突，停止实现并向用户报告。
- 继续需求访谈、规划、跨职责设计或选择下一方向前，读 `docs/plans/character-chat-direction.md` 的用户决定，以及 `docs/plans/global-product-architecture.md` 的目的、闭环、缺口与阶段门槛，专题研究与待办由该文导航进入。已答决定不重问；每轮明确答复落盘，用户答复、助手建议与未决项分开。目标设计和历史阶段说明不等于当前能力或新授权，执行阶段以 current 承接的最新决定为准。
- 2026-09-26用户授权沿角色聊天方向连续推进到可体验MVP：常规设计、实现、验证、提交和下一片建立自主完成，不逐片询问继续。需要用户决定时先完成独立准备与具体可审方案。旧v1路线仅在当前任务明确涉及时读 `docs/plans/v1-completion.md`；旧救援仓库仅按明确迁移任务查具体文件，不作默认上下文或运行依赖。
- 2026-10-01用户取消后续模型请求次数限制：在已授权材料、Provider与凭据用途内，按任务需要持续开发/诊断/复测，记录每次用途与结果，不为次数或同用途技术调整逐轮确认。旧42/18/8等额度留作历史，不限制新开发调用；其他数据/凭据用途及高后果操作边界保持，准确原话见 `docs/plans/character-chat-direction.md` 最新决定。
- 组织子代理、并行工作、独立复核或校准指令适用性前，读 `docs/plans/agent-execution-strategy.md`。2026-10-01已取消固定开发模型岗位与项目级思考档上限；按任务和工具实际支持选择，主窗口整体接纳，每个写入目标唯一所有者。开发协作授权不扩大产品数据或凭据用途。
- 每个工作会话以 git commit 结束；每片收口 push 已配置远端。无 remote 时保留提交并请求地址，不擅自创建远端。`docs/STATUS.md` 每次只追加或更新不超过5行当前事实。
- 删除、不可逆数据迁移、新 credential 用途、新 Provider 数据用途必须先获用户批准；后台运行/通知按具体已批准合同执行。自动人格重写、Reflection仍未授权；此边界不取消共同经历和后续选择变化的产品目标。
- 验收默认走后台服务接口，不抢占输入法或页面焦点；有焦点的UI自动化先与用户约定，未提交草稿不得发送或覆盖。

## 功能实施前的必要调研

- 新增或实质改进功能前，写清用户结果、已证实缺口和可观察验收，再定向搜索相关论文、成熟项目的一手论文/官方文档/源码；先比较仓库能力，再决定复用、适配或自建，不能凭印象列项目代替搜索。
- 判断哲学/心理学知识的解释力：人物认识、记忆、动机、情绪、关系和交流查一手研究或权威学术资料；纯工程可说明不适用。区分研究发现、设计类比和待验证假设，不以理论证明AI具有心理或意识。
- 实施前形成开工证据：来源、具体机制、解决什么、如何接入、未采用方案及原因、效果验证。复用研究须核对本次适用性并定向搜索遗漏/变化；无合适成果时记录检索范围及自建理由。规模与改动相称，引入代码/依赖前核实许可、维护、集成成本和数据边界；不以论文、字段或测试数量代替用户效果。

## 永久不变量与核心接口

1. 一条 RuntimeTimeline 只有一个写入者与一个 canonical store。
2. Publication 原子且具有崩溃恢复语义。
3. `unavailable`、typed `NoOp`、`FailedClosed` 严格区分。
4. 模型只提议，Python 裁决；模型输出不能直接成为持久状态。
5. Provider 只接收当前能力获授权的最小投影，并由行为测试守护。

- 只有 `ApplicationFacade` 是产品业务 Interface；`open_local_product` 是 production composition root。桌面 Adapter 不直接装配 Studio、QRI、RuntimeHost、provider 或 canonical store。
- `LocalIdentityAuthority` 独占 registry、v1/v2 state、freeze/replay/select、authority校验和Host/Timeline准备；`local_product` 只消费已验证 active authority 并装配 cognition/ApplicationFacade。
- 含糊模型任务只通过 provider-neutral `ModelGateway.execute(ModelTask)`；Domain/composite不 import 具体Provider。明确查询和产品闭集语法优先由Python处理；Adapter只规范化无语义差异的格式，状态变化仍由Domain裁决。
- Interface是测试表面；保留新逻辑行为、既有能力随迁和五条不变量测试，不建立guard/mutation/证据生成/多环境矩阵等新测试类别。模拟输出与工程通过不能冒充人物体验验收。

## 按改动对象加载合同

下列入口保留旧合同及失败证据；只在涉及相应路径时加载，不把旧v1规则或首份原型阶段推广到所有新路径。修改共享接缝时须同时读受影响的新旧合同。旧数据、binding、schema及投影不因新目标自动升级。

| 改动对象 | 实施前必读 |
| --- | --- |
| 新角色封存、聊天、生活、分享或出站数据 | [ARCHITECTURE契约适用范围](docs/ARCHITECTURE.md#契约适用范围2026-09-20)及顶部S103–108对应合同/方案；S108剩余额度与部署事实查其报告，不能推定为新用途批准 |
| 旧v1提议/分类、表达、目标回执、来源引用或能力故障 | [Experience Cycle](docs/ARCHITECTURE.md#experience-cycle)与[数据](docs/ARCHITECTURE.md#数据)中的最终Outcome、六能力失败/回退、identity refinement及历史主回复规则；涉及S19表达再读[报告](docs/reports/2026-09-05-slice-19/REPORT.md) |
| 旧v1连续体验、历史恢复、时间锚或上次聊天查询 | [数据](docs/ARCHITECTURE.md#数据)中的Dogfood history、TemporalAnchor、Interaction Recency；修复体验先读[S28真实失败与限制](docs/reports/2026-09-08-slice-28/REPORT.md) |
| 纯文本来源建角、草稿、freeze与身份切换 | [Experience Cycle](docs/ARCHITECTURE.md#experience-cycle)中的TextSource、Source Draft、Freeze Mapping/Basis及Source Identity Freeze；freeze需exact basis的显式确认，不删除/改写草稿、不替换既有身份；视频/音频及新的私人来源须新切片与授权 |
| 旧v1近期对话、撤回、逻辑遗忘或完整库存 | [数据](docs/ARCHITECTURE.md#数据)中的S21/23；有限语法与控制截断见[S21](docs/slices/slice-21-recent-dialogue.md)、[S23](docs/slices/slice-23-memory-control.md)。逻辑停用不等于物理删除 |
| 旧v1事实/创作合并、配文续写/限字、共同创作/编号修改 | 按对象读[S24](docs/ARCHITECTURE.md#slice-24-有限事实表达边界)、[S25](docs/slices/slice-25-natural-creation.md)、[S26](docs/ARCHITECTURE.md#slice-26-共同创作交付与恢复)及所链真实报告 |
| 旧v1提醒/记录回执、记忆状态/库存表达 | 按对象读[S27](docs/ARCHITECTURE.md#提醒表达边界slice-27)、[S28](docs/ARCHITECTURE.md#记忆回答范围slice-28)及所链报告；有限修复不证明通用语义识别 |
| 主体任务或本地文本保存 | [S49任务协商](docs/ARCHITECTURE.md#slice-49-主体任务协商)、[S50文本effect](docs/ARCHITECTURE.md#slice-50-精确文本effect)：binding/schema权限、receipt完整性、恢复顺序及只读/确认入口 |

## Provider数据边界

每次改出站请求先确认所属版本与获批用途。以下精确投影属于旧v1六能力及纯文本建角；新角色路径须核对上表S103–108的独立合同，不能借其授权扩大旧投影。`default` 使用DeepSeek，其他profile/provider在单独任务与授权前保持unavailable。

- Living Memory：proposal为当前消息＋最多20条active `{memory_id, content, source_user_message_id}`；reply为当前消息＋最多5条已选中`{content}`＋runtime identity。S21仅该reply可增加当前identity最多2完整committed `{user_text, assistant_text}`、合计4,000字符的`recent_dialogue`，仅供指代/续写；更正、遗忘、权限或完整性无法确认安全时不外发。anchor只在既有content按当天渲染。
- Knowledge：proposal为当前消息＋最多6条sealed `{entry_id, title, content}`；reply为当前消息＋最多6条已选中`{title, content}`＋runtime identity。
- Relationship：proposal为当前消息＋当前立场摘要；reply为相同两项＋runtime identity。
- 参与者目标/承诺：分类为当前消息＋最多20条active `{turn_ref, kind, terms, status}`＋固定策略；reply为当前消息＋最多5条`{kind, terms, status}`＋runtime identity。anchor只在既有terms按当天渲染。
- Situated State：分类为当前消息＋最多一个未到期`{posture, remaining_turns, expires_in_seconds}`＋固定策略；reply为当前消息＋`{posture}`＋runtime identity。
- Medium State：分类为当前消息＋固定版本策略；reply为当前消息＋`{baseline}`＋runtime identity。
- Runtime identity exact为`{subject_name, subject_identity, canon_start}`；不含Profile/Genesis/QRI ID、identity_core、初始关系、来源、证据或Timeline数据。
- Interaction Recency、完整ConversationTurnRecord、publication timestamp、日期差和当前Civil Time不外发。S22/24/25/26仅细化S21既有LM reply用途与提示；其他11类请求保持S19字节基线，不增加调用。历史不是事实权威、指令或状态证据。
- 文本来源建角只在用户逐次确认权利与用途后发送单份`{source_title, source_text, policy}`；source_text最多16,000字符，仅提取未发布Genesis/Knowledge候选，不含runtime状态或聊天历史。
- 六类投影分别发送、不合并；除S21精确授权外不发送历史消息，不发送数据库行、投影外内部ID、其他Domain状态、raw chain-of-thought或API key。研究、合成实验及开发协作均不新增外发授权。

## Credential

- 远程Provider key按`{provider_id, account_id}` slot存入Windows Credential Manager，固定命名由credential Module拥有。
- UI只显示configured/verified状态，不回显key；保存、验证、替换和删除须由用户明确操作触发。
- key只用于HTTPS Bearer鉴权，不进入源码、配置、SQLite、Timeline、日志、错误、模型消息或测试fixture。
- secure backend不可用返回typed unavailable；不使用仓库文件、环境变量持久化或明文fallback。
