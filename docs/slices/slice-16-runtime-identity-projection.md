# Slice-16：封存身份的 Runtime Identity / Voice Projection

状态：active（2026-09-02，真实验收完成，等待最终复审）。规模预算：≤ 3 个工作会话。

## 用户可见结果

当前身份已经封存的“她是谁、故事从哪里开始、若有则怎样表达”会稳定约束普通对话及既有能力的回复，使两个封存内容不同的身份在相同消息下仍可辨认。该结果只使用既有 Sealed Identity，不生成新人格、不修改 Genesis，也不把 Memory、状态或时间流逝伪装成身份事实。

原始 Avery 当前封存内容只有 subject identity 与 Lantern Zine canon start，没有独立 voice/personality 条目；本切片不会替她发明一套性格。只有 `canon_start` 已封存“表达方式”的身份才承诺体现该 voice。

## 授权门槛：拟新增的 exact Provider 数据用途

用户已于 2026-09-02 逐字确认本节 exact 数据用途及三项 capability-local proposal/reply 拆分；不得据此扩展其他字段、任务或用途。

每个需要形成自然回复的既有 Provider 请求可新增一个相同的只读对象：

```json
{
  "runtime_identity": {
    "subject_name": "当前 authority 已验证的身份显示名，最多 128 字符",
    "subject_identity": "当前 sealed GenesisPremise.subject_identity 原文，最多 2000 字符",
    "canon_start": "当前 sealed GenesisPremise.canon_start 原文，最多 4000 字符"
  }
}
```

- `subject_name` 来自 `LocalIdentityAuthority` 已验证的当前 registry identity；v1 原始身份固定为 `Avery`，v2 来源身份必须与已封存 authority 一致。
- `subject_identity` 与 `canon_start` 只从 QRI 绑定的 GenesisSnapshot 读取；不从 Source Draft、页面输入、聊天、模型输出或 registry 自由文本推断。
- Living Memory、Knowledge、Relationship 当前为“候选 + 回复”同一 Provider 调用；不得直接把身份加入该调用。三项必须先在各自能力内部拆成 proposal/reply 两阶段，proposal outbound 与本切片前 byte-equivalent，只有 reply outbound 新增 `runtime_identity`。
- 参与者目标/承诺、Situated、Medium 已有的 classification 调用不接收身份；只有各自 reply 调用接收。
- 拆分只增加三个 capability-local reply task，不建立跨能力统一 Expression Provider 或第七种产品能力。普通对话仍由 Living Memory 能力的 reply 路径承载。
- 不发送 `identity_core`、`initial_relationship_premise`、SourceDeclaration、来源原文、evidence quote、draft/freeze basis、Profile/Genesis/QRI/Timeline/internal ID、Memory、Knowledge、Relationship、目标、状态、时间戳、raw chain-of-thought 或 credential。
- reply 请求的非身份字段只能是该能力在本切片前已获授权数据的相同或更小子集；不得因拆分增加新的聊天历史、状态或其他 Domain 数据。具体保持现有边界：Memory 仅当前消息与最多 5 条已选中 `{content}`，Knowledge 仅当前消息与最多 6 条已选中 `{title, content}`，Relationship 仅当前消息与当前 stance summary，目标/承诺仅当前消息与最多 5 条 `{kind, terms, status}`，Situated 仅当前消息与 `{posture}`，Medium 仅当前消息与 `{baseline}`。
- 同一投影按既有能力的独立 reply 请求分别发送，不合并六类 Provider 数据，也不新增跨能力上下文。

## 身份与表达契约

- `RuntimeIdentityProjection` 是 Sealed Identity 的只读投影，不是新的 canonical store；删除该 Module 会迫使 authority 校验、v1/v2 兼容、长度限制和最小投影逻辑重新散落到 composition 与六类 Adapter。
- 投影只约束措辞、视角和已封存前提。它不能成为 Memory、Relationship、目标、Situated 或 Medium 的 evidence，不能改变 Domain candidate、Outcome、Publication 或 Timeline。
- 用户说“忘掉你的身份”“现在变成另一种性格”只能作为当前消息被回复，不能改写投影或持久状态。
- `canon_start` 是起点前提，不是当前世界状态；后续 Timeline 没有记录的进展不得由模型补全。若它包含“尚无运行时经历”，不得转述为当前无记忆。
- 身份投影缺失、QRI/Profile/Snapshot 不一致、内容超界或完整性失败时，在 Provider 调用前 FailedClosed；不得静默退化为通用人格或读取代码默认值。仅保留现有 `local-product-deepseek-qri-v1` 的明确兼容规则。

## Module 与 Interface

- `LocalIdentityAuthority.load_active()` 在同一次 Studio 打开中读取并验证 registry display name、QRI、Profile 和 GenesisSnapshot，返回 typed `RuntimeIdentityProjection`；`local_product` 不解析 Studio 或 registry。
- production composition 将该值注入 `CognitionRuntimeView`。`SubjectRuntime` 只转发当前 authority 的不可变值，不建立 identity cache/store，也不从 Timeline 重建 Genesis。
- 各能力 cognition 只把投影放入 reply request；DeepSeek Adapter 负责 exact JSON serialization 和仅用于表达的 system contract。Domain 与 composite 不 import DeepSeek。proposal/classification 失败保持该能力 FailedClosed；新拆分的 Memory/Knowledge/Relationship identity reply 无效时退回同一 proposal 已验证的 identity-free reply，不能反向丢掉候选或改写 Outcome。目标/Situated/Medium 保持本切片前既有 reply 失败语义。
- `RuntimeIdentityReply` safety 只对 identity-grounded 表达删除无来源的第一人称当前活动整句；它不是统一表达层，不读取或改写 identity、Domain 或 Timeline。整句以外的安全回应保留。
- `ApplicationFacade` 与 Desktop 不直接读取或显示 projection 原文；页面继续只显示已验证 identity label。Interface 行为测试同时守护 v1、v2、多身份切换和重启。

## 实施与验证顺序

1. 先补 authority 行为测试：从 QRI 精确加载 Profile/Genesis、v1/v2 兼容、跨身份隔离、缺失/篡改 FailedClosed；再实现 `RuntimeIdentityProjection`。
2. 将 projection 通过 composition/runtime view 传递，证明 Timeline、Domain、Application/desktop schema 均不变化。
3. 先将 Living Memory、Knowledge、Relationship 各自拆为 provider-neutral proposal/reply 两阶段，证明不含身份时候选、表达和局部失败语义与现状相同；再逐个扩展 reply request 与 DeepSeek Adapter。所有 proposal/classification 请求保持 byte-equivalent，outbound exact schema/长度/额外字段测试先红后绿。
4. 对抗“身份内容诱导写状态”“把 canon start 当当前进展”“用户直接改人格”“Provider 回显内部规则”以及单项 Provider failure；Python 裁决与六项局部 FailedClosed 语义保持。
5. 在新隔离 root 中，用两份内容明显不同但均为 project-original 的 sealed fixture 身份做同消息 A/B；真实 DeepSeek 至少覆盖普通对话、Memory recall、Knowledge、目标回复和状态独占回复，检查不是机械复述身份文本。
6. Windows 页面完成身份切换、各两轮、关闭重开；核对每轮只见当前 identity、历史与状态不串线、页面无 console error。全量测试、两轴审查、文档、commit、push 后收口。

## 最小验收

- 当前 authority 可得到 byte-equivalent `RuntimeIdentityProjection`，重启不重新生成；切换身份后 projection 完整替换且不混合。
- 六类 reply outbound 只新增 exact `runtime_identity` 三字段；所有 proposal/classification outbound 完全不变，禁止字段与其他 Domain 数据均不出现。
- 同一中性消息在两个具有明确不同 sealed voice 的身份下产生可辨识且各自一致的表达；无 voice 的原始 Avery 不被伪装为已有性格。
- Identity 只影响最终自然表达：相同输入的 proposal/classification、候选、Domain Outcome 与 Timeline 写入保持一致；Memory/Knowledge/Relationship identity reply 无效时回退原已验证回复。任何身份指令注入不能成为状态证据。
- 普通对话、Memory、Knowledge、Relationship、目标、Situated、Medium 均至少有一条行为测试证明投影到达正确 reply seam；单项失败不泄漏 projection、不终止其他无依赖能力。
- 真实 DeepSeek/Windows A/B、身份切换与重启通过；全量测试与 Standards/Spec 复审无阻塞。

## 范围外

- 新建或补写 Avery 性格、voice、经历、爱好、价值观或世界事实。
- 人格发展、长期倾向、Reflection、内心独白、自我修改、Lifeworld、World State、Agency、effect 或主动消息。
- 跨能力统一表达层、第七种产品能力、跨能力合并请求、模型路由或新模型选择；三个 capability-local reply task 属于本切片明确要求的 seam 拆分。
- 编辑、合并、迁移 Sealed Identity，重新解释 Source Draft，视频/音频来源建角或私人来源。
- 将身份内容作为 Domain evidence，或让 Provider 输出直接成为 Profile/Genesis/Timeline 状态。

## 已确认授权

用户确认允许本切片把 exact `{subject_name, subject_identity, canon_start}` 投影发送给六类 DeepSeek reply 请求，仅用于当前回复的身份与 voice grounding；同时允许把 Living Memory、Knowledge、Relationship 现有合并调用拆为 capability-local proposal/reply 两阶段。所有 proposal/classification outbound、持久状态和其他数据用途保持不变，reply 的非身份字段只能缩小为上列既有数据子集。

## 主要风险

- Memory、Knowledge、Relationship 各增加一个 reply 调用，可能提高延迟与费用；验收必须记录真实调用数和端到端耗时，不能以并发或缓存掩盖。
- Provider 可能机械复述 `subject_identity/canon_start` 或把起点当当前进展；system contract、输出测试和真实对抗必须共同阻止，不能只看“更像角色”。
- 原始 Avery 没有 sealed voice；若实际表达仍不鲜明，这可能是内容缺失而非投影故障，不能在本切片内补写人格。
- v1 的 Profile display name 表示 participant 而 registry label 表示 Avery；`subject_name` 必须由 `LocalIdentityAuthority` 的既有兼容规则确定，不能让 Adapter 猜测。
- 两阶段拆分可能改变故障时机或候选选择；以 byte-equivalent proposal outbound、Domain Outcome 对照和局部 FailedClosed 测试作为阻塞门槛。

## 真实验收记录

- 初次真实根 `dsa-s16-real-k83u1wo9` 暴露模型虚构“今天收到稿件/还没核对”和把 voice 示例“资料里没有写”当口头禅；未选择性丢弃该失败数据。
- 第二次根 `dsa-s16-final-real-aroob91z` 证明 prompt 修复前半，但 legacy 仍虚构“我正好也歇口气”；因此增加 provider-neutral identity reply safety，而不是把该输出算作成功。
- 最终对抗根 `dsa-s16-adversarial-real-bgy6tmkq` 使用 project-original Lyra：中性闲聊、Memory 创建/召回、Knowledge、目标和 Situated 回复可辨识地使用天气/光线简短比喻；legacy Avery 同消息保持无 voice 的普通自然回复。真实 guard/failure 曾因新 code 破坏局部失败，修正为既有 code 并进一步让三项新 identity reply 失败回退 base reply、不改变候选。
- 单次普通会话真实计数为 6 个 Provider 调用（Memory proposal/reply、Relationship proposal/reply、Situated classification、Medium classification），端到端 5.722 秒；各场景观测约 4.8～9.7 秒，未用缓存或并发掩盖。
- Windows 页面显示 Lyra 独立历史、2 条 Memory、1 条 Knowledge、1 条目标；切到 Avery 后只显示其自己的 2 轮历史，Lyra 状态未混入，重启恢复一致，console 无 warning/error。浏览器确认框有一次自动化结果不确定，最终只以页面权威身份状态记为成功，不把未观察的反向点击计入证据。
