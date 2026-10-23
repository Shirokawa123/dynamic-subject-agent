# M027：同身份原生活动资格续接

独立产品执行M027–029，本仓仅提供M027共用接缝。原schema11的SubjectCommand和typed native记录在同一store/scope上保留；新schema12增加原生活动表与独立第二层续接回执，旧回执不改。新生schema12保持既有合同，带续接回执的schema12必须同时验证旧回执及准确历史前缀，旧记录的shared_record仍为None。

旧M002升级同意不能用于本次。新typed plan/consent绑定冷源五文件、完整请求证明、原资格/原gate/原registry与已批准M012用途；申请、预览和verify均不apply。复用现有多库事务与pending fence、发布后继资格、向前恢复。只有明确新同意后才写原库，合成验证不触碰用户根。

来源为既有续接/Host治理/timeline/shared源码及[SQLite多库原子提交](https://www.sqlite.org/atomiccommit.html)。保留单canonical、单写者、原子Publication、typed unavailable/NoOp/FailedClosed和原Provider最小投影；纯工程兼容，无新心理机制或依赖。验收由Facade/production composition覆盖原UUID、历史控制、共同经历/分享、重开和异常点恢复。

已实现独立typed prepare/apply/verify及仅打开已提交续接的production factory。第一层回执保持，第二层回执证明完整原请求/plan/claim/outcome；旧shared_record/准备记录仍为空，只对证明过的原前缀读取豁免，后续新Publication仍须完整记录。Host逐层核历史绑定、Studio仅允许准确同snapshot native资格的M012后继；provider authority和capability manifest同时切换。

复用原M002事务执行器，分别绑定新版request/consent和registry fence；提交后移存旧chat activation、启用新whole activation，历史开关不改，整理暂停/分享关闭。原子多库日志/原文件basis/无活动lease条件保持，不复制store或写旧Outcome。重复apply仅验证后NoOp，不重新初始化权限。

41项严格回归通过（357.28秒，-W error、无skip）：M027完整混合链、活源/错同意/错计划拒绝、五异常点和两处os._exit恢复、历史关闭与损坏拒绝，以及旧M002/M015/M018兼容。首轮源字段/治理历史版本/manifest/旧prepared假设、测试短nonce/缺cognition/rowid及旧SQLite未close告警全部保留；修正来源与读取路径、补显式close，未改断言或屏蔽告警。所有模型transport合成，用户原根未调用apply。

产品HTTP接续发现来源确认超出5秒期限；读取分析定位到多层QRI重复验证同一封存快照。先按已存资格ID选择准确父路径（实际选中的QRI仍完整验证），再仅在一次资格读取事务内复用已验证快照，事务结束即丢弃，当前事务自身写入计数改变也失效。没有跨请求缓存或跳过损坏检查。追加同一个Studio对象下一次查询发现快照篡改的用例后，42项严格回归通过（347.21秒，无skip）；HTTP最终时限仍由产品继续验证，未延长超时。
