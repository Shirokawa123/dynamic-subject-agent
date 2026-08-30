# 当前决定

## D-001：建立独立产品仓库

2026-08-30，用户决定结束学习/救援仓库阶段，在 `E:\dynamic-subject-agent` 建立唯一未来产品主线。旧仓库保留为只读历史和未迁能力规格来源，不删除、不运行时依赖、不自动回退。

## D-002：保持 mature 单时间线架构

保留单写入者、原子 Publication、四 Domain、模型提议/Python 裁决和 provider 最小投影。产品抽取不等于重新发明架构。

## D-003：按产品缺口推进

当前已有能力冻结维护；下一顺序为目标与承诺、Situated State、Medium State、五能力整合、Agency、低风险 effect。历史治理流程、学习计划和证据生成体系不进入新仓库。

## D-004：软件内管理 DeepSeek credential

2026-08-30，用户确认由桌面软件配置 key。生产只使用 Windows Credential Manager，不使用仓库文件、SQLite、环境变量持久化或明文 fallback；“保存并验证”只对 DeepSeek `/models` 发 Bearer 鉴权请求。

## D-005：模型能力与产品语义解耦

2026-08-30，用户要求未来可接入其他云端或本地模型。所有含糊任务经 provider-neutral ModelGateway 和能力声明进入 Adapter；明确产品语法由 Python 直接处理。JSON mode 不被视为 schema 保证，只有无语义差异的 action-aware 规范化可在 Adapter 内执行；Provider 单项失败不再自动终止整轮。

## D-006：Situated State 为一次 carry 的短时姿态

2026-08-31，迁移 focused/gentle/cautious 闭集：set 当轮使用并保留 1 次下一完成轮 carry，绝对 TTL 30 分钟；replacement、consume 与 expiry 只向前记录。Provider 只提议，包含“必须”的直接命令不能成为证据，失败消费旧状态但不终止整轮。
