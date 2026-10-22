# M018–020：原生互动与有限活动的单Timeline组合

独立产品唯一任务由`E:/memorie-companion/docs/slices/current.md`承接。本次复用已批准M012准确三用途wire、policy、同用户跨根日账与schema6活动机制，增加独立`memorie-native-activity-m018-1`资格和schema12。只通过新的unserved开发身份激活；不升级/复制旧schema6、10、11或用户原Timeline，没有新增迁移apply接口。

## 工程接缝

组合Timeline同时持有native输入、whole context、shared输入/记录与prepared表。每个SYSTEM操作必须且只能属于一种canonical typed输入；完整Publication前缀分别验证，原生历史跳过活动/控制事件，保留真实点击/文字和原head。共享来源只能是已发表文字，点击和助手回复不成为用户原话；不是把点击转成SubjectCommand。

原生回复从同一前缀、同一来源资格构造M012 reply。typed两轮/4000字选择独立于旧speech投影；来源撤回后，原话、依赖的文字方案/分享和后续点击/文字整轮同时过滤。所有回复继续四Domain typed NoOp，方案由Python有限动作/实际差异裁决。新Sender复用相同grant/一次票据/Windows slot与日账，点击回复额外裁决≤120字；不新增模型字段或改变已批policy。

prepared活动沿既有原子恢复发表；重开不调用模型。原生UUID查询在新的runtime合同下读取同一canonical操作，不重送。旧native与schema6保持独立分派、原默认factory不变，旧服务身份不能被此开发factory换资格。

新增Facade `suspend_living_presence`只清当前会话的瞬时presence/在线计时，其他会话不能重置拥有者。它不写人物事实、不更改用户开关；产品在剧情/不可用/陈旧观察时调用，避免故事占权期间的时间进入下一900秒机会。启动/重开仍默认关闭活动或恢复真实既有开关，瞬时计时不恢复。

## 可观察结果与限制

Facade合成链：点击→文字→确认原话→方案→分享→点击接话→重开→原UUID查询；另核来源停用派生过滤、点击不可选、prepared恢复、超长点击拒发表、900秒与presence清空。具体定向回归结果在本次STATUS和本机日志，首次缺环境/引用错误/沿用speech摘要选择器及共享事件误走点击正文裁决均保留。

兼容定向59 passed（317.96秒、-W error、无skip），含旧M002、M015、living-live和shared；最后只在新native分支复用M002计时澄清例外后，新native全部7项严格通过（64.67秒），明确披露控制0外发。普通subject文字的边界不变，全部首次日志保留在`.artifacts/native-activity-018-*`。

随后按实际DeepSeekUrlLibTransport调用顺序收紧出站：消费票据之后及Windows凭据解析之后、进入最终HTTPS opener之前，分别重建同一canonical权限/材料/日期并核准确字节。只有ScopeTransport入口复核不能覆盖其内部的凭据解析等待，故默认生产composition明确装配受控opener；没有更改通用transport或凭据用途。合成撤权分别发生在consume后与凭据解析中，两者均0下层投递，默认URLLIB正向路径用假凭据/假opener验证。最终新native10项＋原M015九项共19 passed（132.01秒、-W error、无skip）；0真实凭据/网络用于这些假opener用例，日志`native-activity-018-https-final.log`。

生产组合可用于上述隔离开发；不证明用户旧schema11的迁移/旧资格读取权限已经实现。schema12旧库治理、原生客户端协议3/UI/呈现和真实人物效果由独立产品后续承接；原两次真实defer不改、不重跑，不以合成分享冒充真实分享。
