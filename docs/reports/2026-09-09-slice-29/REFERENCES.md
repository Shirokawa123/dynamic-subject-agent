# Slice-29 连续对话参考对照

调研日期：2026-09-09。范围由 `docs/slices/slice-29-conversation-continuity.md` 授权；只查阅公开一手资料，没有安装框架、启动服务或发送仓库源码、聊天和私人数据。以下是机制对照与待验证建议，不是实际效果验收。

## 结论

优先借鉴“先选择合适的内容，再在固定预算内交给模型”的机制；不能把存储上限、候选窗口和最终表达窗口视为同一件事。本切片更适合改进已有 Living Memory 的本地候选选择，而不是换掉身份、Timeline 或 Provider 架构。选择策略是否改善改述召回，仍必须由本项目的失败对照与未参与设计的改述验证。

## 一手资料与版本边界

通过 Context7 对 Letta、SillyTavern、Graphiti 分别执行了 resolve-library-id 和 query-docs，选择 `/letta-ai/letta`、`/websites/sillytavern_app`、`/getzep/graphiti`。SillyTavern 的检索结果偏向脚本示例，因此继续阅读官方概念文档。Graphiti 的部分结果是设计 spec，未将设计 spec 当成实现证据，另查实际 search recipes 源码。

本次没有安装或固定这些项目的发行版本：Letta 引用页面明确属于 **V1 SDK (legacy)**；SillyTavern 是访问日官方滚动文档；Graphiti 是访问日 `main` 源码。这里确认的是已文档化或有实现的机制，不宣称最新 SDK 接口兼容，不宣称经过生产稳定性比较。若以后复制代码或引入依赖，应另行固定提交、核对许可证和测试。

## Letta：常驻上下文与按需内容分开

Letta V1 将附着的 memory blocks 放入上下文，文件可按部分读取，archival memory 通过工具检索；不同规模与重要性的数据使用不同入口。其块既可由开发者管理，也允许 agent 经工具编辑。历史消息即使从上下文移出，仍可通过 API 或检索工具找回。[Context hierarchy](https://docs.letta.com/v1-sdk/memory/context-hierarchy)、[Stateful agents](https://docs.letta.com/v1-sdk/concepts/stateful-agents)

可学之处是明确区分“已经保存”“本轮可以检索”“本轮实际可见”。不能照搬整份 persona 常驻或自主 memory editing：本项目 runtime identity 仅有既定三个字段，Profile/Genesis 不属于任意外发上下文；模型编辑仍只能成为待 Python 裁决的提议。也不能引入 Letta 数据库作为第二份运行权威。现有 2 轮 `recent_dialogue` 仅用于获授权的 Living Memory reply，不可因为外部项目支持历史检索就扩到 proposal 或其他能力。

## SillyTavern：角色信息、对话与动态资料竞争预算

官方文档将角色描述、personality 和 scenario 作为常驻提示内容；示例消息在历史占满上下文时可被挤出。角色文本越多，留给聊天的空间越少。因此“更长的人设”本身不保证更好的连续对话。[Character Design](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)

World Info 先依据扫描范围和匹配条件激活，再受独立 token budget 与优先顺序限制；匹配到关键词也可能因预算耗尽而无法进入提示。向量匹配只替换关键词检查，不绕过其他过滤或预算。[World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)

可学之处是把候选匹配、合法性过滤、预算截断和最终注入分开观察。不能照搬将角色卡、世界书、整段聊天混入同一个提示的做法；本项目的六类投影仍隔离。也不建议为本切片新增题材词世界书：改述换词仍会漏检，递归激活或 sticky 内容也不能绕过本项目更正、逻辑遗忘及历史授权检查。

## Graphiti：候选检索与排序是独立机制

实际 recipes 包含 BM25 与 cosine similarity 的 RRF 融合；cross-encoder recipe 还配置 BFS。并非每种 hybrid recipe 都使用图遍历。它表明多路召回和最终排序可以分别配置，而不是仅按存储顺序取前几条。[search_config_recipes.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/search/search_config_recipes.py)

实际 search 实现在配置 cosine similarity 或 MMR 等路径时需要查询向量，可调用 embedder；完整框架还管理图数据。因此它不是当前零新增服务/零新增 Provider 用途下可直接安装的替代件。[search.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/search/search.py)、[官方项目](https://github.com/getzep/graphiti)

可复用的是“先相关性候选，再有限窗口，再选择/排序”的思路。不能把图中的模型抽取关系直接当 canonical 事实，也不能悄悄增加远端 embedding、reranker 或 episode 外发。纯本地词面排序不等于 Graphiti 的语义检索，更不能据此承诺同义改述理解。

## 映射到当前切片的一个优先建议

本节使用主执行者提供的基线观察，源码证据与最终根因以同目录实施报告为准：当前 runtime 从最多 100 条历史得到 active 后截前 20 条；Living Memory proposal 从候选选择 IDs；reply 最多得到 5 条，顺序来自 active 而非模型返回顺序。

**优先验证固定候选截断造成的漏召回，并在有重复失败证据时，仅调整本地只读候选排序。** 使用当前消息与当前 identity 已合法恢复的 active 内容计算通用词面相关性，在既有本地历史范围内先排序、再取最多 20 条；无信号时保留确定性回退。它只应改变本轮候选次序与成员，不新增 canonical 状态，不扩大字段、条数或调用，不扫描额外聊天，不改变目标/遗忘等控制查询的完整性路径。是否采用及具体算法由实际失败决定。

如果失败对象本就已在 20 条中，则该建议没有针对性：应继续区分模型没有选中、已选中却未进入最多 5 条、以及表达没有承接，不为引入检索而引入检索。若考虑保留模型 ID 顺序，先验证现有契约是否将其定义为排序；列表顺序不能自动解释成相关性权威。

验收至少分别记录候选命中、最终选中和回复承接。无关记录干扰、同一对象的新改述、更正后旧内容不可用以及重启应分别覆盖；诚实澄清独立记为澄清，不计作正确召回。中文词面重合弱、纯指代、候选超过本地 100 条或语义歧义仍可能失败；上述外部资料没有提供本项目这些条件下的收益证据。
