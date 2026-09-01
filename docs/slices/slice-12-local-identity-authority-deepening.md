# Slice-12：本地身份 Authority 深模块化

状态：done（2026-09-01）。规模预算：≤ 2 个工作会话。

## 用户可见结果

现有用户行为不增加也不减少：Windows 产品仍可从 exact Freeze Basis 创建来源封存身份，在“原有身份/来源封存”之间切换并跨重启恢复。身份 registry、Studio、QRI、Host、Timeline 或 Knowledge 任一绑定损坏时，产品在打开或切换前失败关闭，不出现标签属于 A、运行时属于 B，或 active 已改变但旧身份仍可继续提交的状态。README 与当前实际能力一致。

## 长期问题

Slice-11 为完成真实 freeze 闭环，使 `local_product.py` 同时承担 state schema、identity registry、freeze 编排、authority 校验、Host 准备、Knowledge 注入和 composition。行为已通过审查，但 locality 较差；继续叠加来源类型或发行流程会扩大 shotgun surgery 风险。本切片先把身份 authority 复杂度收进一个深 Module，再考虑任何新能力。

## Module 与 Interface

- 新的本地身份 authority Module 隐藏 v1/v2 state 读取、原子写入、registry 校验、exact freeze、list/select、Host/Timeline 准备和 active authority 加载。
- production composition root 只消费一个已验证的 active authority，并装配 cognition/ApplicationFacade；不理解 registry 字段或 freeze 恢复步骤。
- 外部产品业务 Interface 仍只有 `ApplicationFacade`；Desktop 只处理 credential 与 composition 生命周期，不读取 Studio/QRI/Host/canonical store。
- 不为单一实现新增 port/adapter；本地 SQLite、文件 state 与 Studio 属 local-substitutable/internal seam。
- 既有 Interface 行为测试是主测试面；只保留确有价值的持久化篡改/并发故障测试，不新增测试类别。

## 不变量

- exact Source Draft revision 在 `BEGIN IMMEDIATE` 期间保持稳定，直到 deterministic target QRI 与 registry visibility 完成。
- 同一 Freeze Basis 在草稿后续 revision 或删除后仍回放同一 sealed identity；未成功的 stale/tampered basis 零可见写入。
- registry identity、display label、experiment root、Studio、Profile、Genesis/Knowledge snapshot、QRI、Host 和 Timeline 必须形成同一 authority。
- select 只有在目标 authority 可打开后才提交 active；composition 重开失败必须回滚到仍存活的旧 Facade，回滚失败则关闭产品。
- 旧 `local-product-deepseek-qri-v1` 是唯一可使用代码 fixture Knowledge 的兼容身份；来源身份严格读取自己的 snapshot，0 member 即 0。
- Freeze、list、select、replay、启动校验均不调用 Provider，不扩大 credential 或 Provider 数据用途。

## 实施顺序

1. 固定现有 Facade/Windows 行为测试和真实双身份 authority 事实，记录 `local_product.py` 当前职责。
2. 把 registry/state/freeze/select/load 实现移动到一个深 Module；用小 Interface 返回已验证 active authority 和 typed identity 结果。
3. 缩小 `local_product.py` 为身份初建兼容入口、DeepSeek cognition 装配和唯一 production composition root。
4. 更新 README 的 freeze/身份能力说明；不增加 onboarding、历史展示或发行能力。
5. 全量测试；对真实 Slice-11 双身份状态执行 open→list→switch→restart→switch-back→freeze replay，确认原 head 0、新 head 4、草稿 revision 1 和各 snapshot/QRI 计数不变。
6. 两轴独立审查、commit、push；记录首次用户体验点仍需的下一切片。

## 范围外

- 新 UI 流程、聊天历史展示、安装包、遥测或用户反馈收集。
- 新来源类型、视频/音频/PDF、私人来源或正式身份迁移。
- Agency、effect、人格发展、Reflection、主动消息或任何新 Provider 用途。
- 删除、迁移或重建 Slice-11 真实双身份数据。

## 最小验收

- `local_product.py` 不再解析 identity registry 字段，也不拥有 freeze/select/replay 实现；删除新 Module 会迫使这些复杂度重新散落，满足 deletion test。
- v1 首启、v1→v2 registry 显式创建、v2 active 打开、0 Knowledge、草稿后续 revision/delete replay、并发 revision lock、registry/Host 篡改和 lifecycle rollback 行为不变。
- `ApplicationFacade` 与 Desktop 可见 payload 不增加内部 ID/source digest；Provider outbound bytes 不因重构变化。
- 真实双身份无需迁移即可由新 Module 打开与切换，canonical head 和 snapshot/QRI 计数不变。
- 全量测试和两轴审查无阻塞，README/ARCHITECTURE/STATUS/current 与实现一致，commit 已推送。

## 收口记录

- `local_product.py` 从 1090 行降至约 244 行，只保留 `OpenedLocalProduct`、DeepSeek cognition 装配和唯一 production composition root；新 `LocalIdentityAuthority` 以 `load_active/freeze/list/select` 四方法 Interface 隐藏 v1/v2 state、registry、exact freeze/replay、authority 校验和 Host/Timeline 准备。删除该 Module 会迫使上述复杂度重新散落，满足 deletion test。
- codebase-design 深模块审查阻止了浅层搬文件：初版 `freeze()` 仍要求 composition 回传 `authoring_studio_location`，独立 Standards 审查判为 Interface 泄漏；已改为 Module 内部解析 authoring authority。v1/v2 load、select 与首次启动共用 identity/Host helper，`local_product` 不再读取 registry 字段或 Studio 配对。
- 新增 Host/Timeline 持久化篡改验收：把来源身份 registry 指向原身份 Host，或改为随机 Timeline，production open 均在产品可用前失败关闭。既有草稿并发锁、basis 在 revision/delete 后回放、0 Knowledge、registry/QRI 篡改、composition 失败回滚和 Provider 单次 authority load 行为保持。
- 真实 Slice-11 双身份 state 无迁移完成来源→原有→重新加载→来源切换及 exact basis replay；原身份 head 0、来源身份 head 4，各 Studio 的 Profile/Genesis/Knowledge/QRI 计数仍为 `1/1/1/1`，最终 active 恢复来源封存身份，身份操作未调用 Provider。
- README 已与 freeze/多身份实际能力同步；两轴复审最终 Standards/Spec 均无阻塞。全量 `254 passed`，额外首次启动/身份目标测试 `13 passed`。首次用户体验建议再经过一张 dogfood 发行基线切片，重点是可重复启动、历史连续性与可理解错误，而不是扩展主体能力。
