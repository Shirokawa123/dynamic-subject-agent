# 独立人物的LOCAL共同经历与文字活动接缝

2026-10-22，为`memorie-companion`的M010/M011提供共用接缝；不并行执行游戏任务或操作用户根。

## 结果与机制

旧shared/living的LOCAL合同也依赖旧人物的APPROVED_BINDING，独立人物无法用正式composition复用。新增只在LOCAL production composition中选择的独立sealed binding：完整对象仍由Authority/Studio验证，projection携带local_preparation与local/none凭据标记。原remote factory及其shared/living合同继续使用严格旧binding；没有新Sender、grant或remote用途。

独立人物通过同一Facade选择已提交用户原话，跨窗口保留、替换或停用；来源只证明用户曾说过。已有SharedActivityInput、来源依赖过滤、revision、单Timeline原子Publication、冷恢复、分享频率与未回抑制继续复用，不另建记忆或活动数据库。

LOCAL闭集增加herb-note-outline：仍使用CompositionPlan的subject/composition/focus三字段，分别表示笔记题目、编排、待核问题。它只形成文字方案；不宣称采药、药性、疗效、剂量、食用安全或研究完成。结构与实际差异由既有裁决校验，语义忠实与人物自然度不能由合成响应证明。背景的encounter明确为隔离验证，不把旧社交软件场景套给独立人物。

## 复用证据与边界

定向来源是shared_activity/living_activity、对应Facade/Host及production composition源码和既有S139/S142合同；这是已提交原话、有限文字方案、来源停用与恢复的工程适配，不设计自动记忆提取、情绪/关系/人格更新，未作心理真实性主张。

test_independent_local_activity通过新sealed对象、无APPROVED_BINDING替换验证来源重开/修正/停用、无来源/助手台词/过期revision拒绝、实际方案/分享/接话及远程gateway在根访问前拒绝。既有shared/living和remote合同回归另记结果。没有Memorie schema11接入、数据升级、原UUID重发、通知、后台服务或离线推进。

严格首轮72项中70通过、1失败/1setup错误均为旧损坏注入测试的未关闭SQLite连接，保留原失败日志。Context7核[CPython 3.13 sqlite3文档](https://github.com/python/cpython/blob/v3.13.9/Doc/library/sqlite3.rst)：Connection上下文仅处理事务，不关闭连接。只在两项旧测试补closing，保留原事务提交和全部损坏/拒绝断言；不屏蔽ResourceWarning，也不改生产判据。独立对象/旧whole回归27通过，新增remote反例专项通过，修复后两项损坏及原受影响后续4项严格通过（25.67秒）。不是重新宣称首轮72全绿；产品批次另跑自身完整验收。
