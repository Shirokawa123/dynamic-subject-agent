# Slice-10：来源草稿封存映射预览

状态：done（2026-09-01）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用户加载一个未封存 Source Draft revision，输入角色显示名称后，系统用纯 Python 确定性生成 exact Profile、GenesisPremise、Knowledge members 和 Freeze Basis 预览。页面明确说明“尚未封存、将创建新身份且不替换 Avery”；本切片无 freeze、publish、身份创建、Provider 调用或 Timeline 写入。

## 映射契约

- 请求必须指定当前 draft revision 和 `display_name`；名称必须逐字出现在一条已选择 identity 候选的 evidence 中。
- Profile `identity_core` 只由已选择 identity 内容按候选顺序组成。
- Genesis `subject_identity` 由已选择 identity + trait 组成；`canon_start` 由已选择 origin、voice 和固定“尚无运行时经历”政策组成；未选择候选不得进入。
- `initial_relationship_premise` 固定为新身份与现实参与者尚无信任、承诺、共同记忆或既有关系状态；来源文本不能预写已赚取关系。
- Knowledge members 只来自已选择 Knowledge，保留 title/content/evidence/source digest；不得把 Genesis 候选复制为 Knowledge。
- Profile identity 使用映射 basis 派生的稳定新 ID；重复预览同一请求得到同一输出和 Freeze Basis。
- Freeze Basis 绑定 source digest、draft revision、candidate selections、mapping policy version 与完整映射；stale revision 冲突。

## 架构宿主

- SubjectStudio 读取并校验完整 Source Draft revision 链，再调用纯 Python mapping Module；`ApplicationFacade` 是唯一 Presentation Interface。
- mapping preview 不写 source draft、不创建 existing Genesis draft、不调用 `seal`、不生成 QRI，也不修改当前 local product authority。
- Desktop 只显示用户可理解的映射内容、来源证据、draft revision 和 Freeze Basis；不暴露 profile/draft 内部 ID、路径或原文。

## 实施顺序

1. 建立 mapping request/view/status 与确定性 policy，覆盖无草稿、stale revision、名称无证据、无选择 identity、超长映射和重复预览。
2. 经 ApplicationFacade 行为测试证明 mapping 不写草稿 revision、ProfileStore、Timeline 或 runtime 状态。
3. Windows 页面从已保存草稿生成 exact mapping，展示 Profile、Genesis 三字段、Knowledge members、证据和 Freeze Basis。
4. 使用全新 project-original 草稿完成真实 preview→save→restart→mapping；对抗未选择候选混入、关系预写、名称伪造和 stale revision。
5. 全量回归、文档、commit、push；停在真正 freeze 前请求单独确认。

## 范围外

- FreezeDecision、seal、snapshot、QRI、创建/替换身份或启动 runtime。
- 模型参与映射、再次发送来源、自由编辑候选、自动补全人物背景或关系。
- PDF、视频、音频、私人来源、Agency、effect、Reflection 或主动消息。

## 最小验收

- 同一 draft revision + display_name 重复预览 byte-equivalent；名称无 identity evidence、stale revision、草稿 absent 均 typed 拒绝/冲突。
- unselected candidate 不进入任何映射；Knowledge 与 Genesis 分离；固定初始关系不能被来源内容覆盖。
- Freeze Basis 改变当且仅当 draft revision、display_name、selection 或 mapping policy 改变。
- 真实 Windows 映射预览刷新后可由草稿重新生成，但没有任何 sealed snapshot、QRI、Timeline head 或 Avery 状态变化。
- 全量测试、真实页面、控制台、commit、push 完成；任务书记录剩余 freeze 风险。

## 收口记录

- 新增根级 `CONTEXT.md` 固定 Source Candidate、Source Draft、Freeze Mapping、Freeze Basis 与 Sealed Identity，避免将候选/草稿/预览误称为已创建角色。
- 纯 Python mapping 要求 display name 逐字出现在 selected identity evidence；identity→Profile，identity+trait→subject identity，origin+voice+固定无运行经历→canon start，selected Knowledge 独立映射，初始关系固定为无信任/承诺/共同记忆/既有状态。稳定 profile identity 和 Freeze Basis 均由 exact mapping basis 派生。
- ApplicationFacade/SubjectStudio 只读 Interface 覆盖 absent、stale revision、伪造名称、无 identity、映射超长、重复稳定和 selection revision 变化；预览前后 Source Draft revision、ProfileStore、Timeline 与 runtime 不写入。Desktop 不显示内部 profile ID 或原文。
- 真实 project-original Windows/DeepSeek 流程完成 3 Genesis + 2 Knowledge 草稿 revision 1、伪造名称 Rowan 拒绝、Avery exact mapping、产品重启后相同映射复现。真实输出暴露候选句尾导致 `。；`，在组合边界去除末尾句号/分号后复验；重复点击 Freeze Basis 完全一致：`e99264f690cc278d702ecf0470a3cf5b1e06fd43060b645db02cb2a902311343`。
- 真实验收 Timeline head=0，Profile/genesis draft/genesis snapshot/QRI 数量仍各为当前 Avery 的 1，没有新 snapshot、QRI 或身份，控制台无错误；全量 `243 passed`。隔离 Temp root 中保留这份未封存 project-original 草稿作为下一切片可选 freeze basis，本切片未获授权删除。剩余风险：现有 Studio seal/Knowledge snapshot 是否能承载多 member 仍需下一切片验证，不能因 mapping 成功假定可发布。
