# 仓库协作规则

默认用普通中文沟通：开工说明这轮用户会看到什么变化，过程中说关键发现，交付说明改好了什么、在哪里试、还缺什么。技术细节按解释需要展开。

## 当前任务与决定

- 开工先读[当前工作](docs/slices/current.md)，只执行其中承接的完整用户结果。当前无后续任务时，按最新阶段安排收口。
- 文档职责：PRODUCT记录目标，ARCHITECTURE记录实际合同，DECISIONS导航有效决定，STATUS记录现状，current承接当前工作。用户最新明确决定优先，按对象和阶段替代旧要求；不能消解的实际冲突再报告。
- 重新规划或选择方向时，读[用户决定](docs/plans/character-chat-direction.md)和[总体方案导航](docs/plans/global-product-architecture.md)，按需进入专题。已答决定不重问，用户主动重议时以最新答复为准。
- 普通纠错先修当前理解和实现。临时要求写清适用任务/阶段，稳定长期决定才进入常驻规则；每轮明确答复落盘，用户答复、助手建议和未决项分开记录。暂缓不等于取消，历史快照不作为默认执行清单。
- 已确认、已授权的当前范围内，设计、实现、验证和提交自主完成。需要新授权时先准备具体方案再集中说明。每个有改动的工作会话提交到工作分支，每个完整阶段推送已配置远端；保留已有未提交成果。
- STATUS只保留现状，每次新增或更新不超过5行事实；详细过程和失败放对应报告，历史归档保留。无需因普通文案修正增加产品规则。
- 组织协作或复核时按[协作策略](docs/plans/agent-execution-strategy.md)处理；按任务和实际工具能力选择，单个写入目标只有一个所有者。

## 实施与验收

- 新增或实质改进功能前，明确用户结果、已证缺口和可观察验收；先比较仓库能力，再定向查一手论文、官方文档或源码，决定复用、适配或自建。
- 人物认识、记忆、动机、情绪、关系和交流需核一手研究或权威学术资料；纯工程可说明不适用。区分研究发现、设计类比和待验证假设，不用理论证明AI具有心理或意识。
- 开工证据覆盖来源、具体机制、接入、未采用方案及理由、效果验证，规模与改动相称；复用研究核本次适用性与变化，引入依赖核许可、维护、成本和数据边界。
- 每阶段交付一个完整结果，重构范围按实际缺口确定。人物依据、共同经历和状态是否影响行为，用具体互动验证；模拟输出、框架和测试数量不能代替人物体验。
- 检查围绕本次改动与实际风险，达到验收就交付；仅新改动、失败或明确疑点触发扩查。Interface为测试表面，保留行为、能力随迁及五项不变量检查，不增设独立测试类别。
- 验收默认走后台接口；有焦点的UI操作先与用户约定，未提交草稿不得发送或覆盖。

## 数据与授权

- 删除、不可逆迁移、新凭据用途、新Provider数据用途先获用户批准；后台运行/通知按具体已批合同执行。自动人格重写、Reflection仍须具体授权，成长与坚持仍是长期产品目标。
- 已授权材料、Provider和凭据用途内，开发/诊断/复测无旧次数上限，记录用途与结果；准确旧批准按原对象适用，不将历史实验限额或技术参数推广为全项目规则。
- 修改业务路径或出站请求前，按[合同导航](docs/ARCHITECTURE.md#按改动对象加载合同)读取对应版本；旧v1投影与新人物/梅莫莉用途分别核对。旧身份、数据、binding和schema不随产品目标自动升级。
- 远程key按`{provider_id, account_id}` slot存入Windows Credential Manager，固定命名归credential Module。UI只显示configured/verified；保存、验证、替换和删除由用户明确操作触发。
- key仅用于HTTPS Bearer鉴权，不进入源码、配置、数据库、Timeline、日志、错误、模型消息或测试fixture。安全后端不可用返回typed unavailable，不持久化到环境变量或明文fallback。

## 永久不变量与接口

1. 一条RuntimeTimeline只有一个写入者与一个canonical store。
2. Publication原子且具有崩溃恢复语义。
3. `unavailable`、typed `NoOp`、`FailedClosed`严格区分。
4. 模型只提议，Python裁决；模型输出不能直接成为持久状态。
5. Provider只接收当前能力获授权的最小投影，由行为测试守护。

- ApplicationFacade是唯一产品业务Interface；open_local_product是production composition root。桌面Adapter不直接装配Studio、QRI、RuntimeHost、Provider或canonical store。
- LocalIdentityAuthority独占registry、v1/v2 state、freeze/replay/select、authority校验和Host/Timeline准备；local_product只消费已验证active authority并装配cognition/ApplicationFacade。
- 含糊模型任务只经provider-neutral ModelGateway.execute(ModelTask)；Domain/composite不import具体Provider。明确查询和闭集语法优先由Python处理；Adapter只规范化无语义差异的格式，状态变化由Domain裁决。
- 旧v1路线仅在任务明确涉及它时读`docs/plans/v1-completion.md`；旧救援仓库只按明确迁移任务查具体文件，不作为默认上下文或运行依赖。
