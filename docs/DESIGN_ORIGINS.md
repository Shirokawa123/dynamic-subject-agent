# 设计来源

产品起点是“过去经历应真实影响角色，而不是只靠静态人格提示词”。梅洛-庞蒂的处境、身体能力和习惯沉淀启发多时间尺度状态；拉康关于语言、他者、关系位置和非透明自我的问题启发 SelfModel、NarrativeIdentity 与多层 Relationship。哲学只提供问题，不直接成为代码字段或意识声明。

CharacterGPT、CoSER 与 Character-LLM 启发有来源的 Genesis 和场景证据；Generative Agents、Letta、Mem0、Graphiti 启发选择性记忆、检索与版本语义；verification-gated persona update 与 OpenPersona 启发“模型提议、程序验证、提交或拒绝”；CharacterEval、TimeChara 与 InCharacter 启发分项和时间边界评测。

项目的工程贡献是将这些启发收敛为同一条可审计 lived continuity：认识对象分离、模型无写权、单写入者、原子 Publication、显式失败语义与最小 provider 投影。
