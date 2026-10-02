# S131开工证据：原请求查读与安全继续

2026-10-02。用户结果与范围见[S131](../slices/slice-131-whole-request-recovery.md)。本次只读代码、核两处官方来源并写此文；未调用模型、读取用户运行root/草稿、操作8785或安装SDK。实施分工为core唯一所有者贯通Facade/Host/Runtime/Timeline，入口与其测试另有唯一所有者；先约定接口，不同时写共享接缝。

## 用户结果、已证实缺口与验收

用户遇到连接中断、服务重开或不确定交付时，可以查清自己原请求的当前结果，保留后来编辑的草稿，再明确决定是否开始一轮新请求。刷新不发送文字，查结果不重新生成；原尝试和已耗调用不消失。

[S127](../reports/2026-10-02-slice-127/REPORT.md)已经修复已知终态失败清旧nonce、保留草稿；这不是本片待修问题。剩余缺口是：入口pending handle及nonce映射只在Adapter内存；重启后只有浏览器原request_id/request_text，当前“继续上次发送”仍进入submit；UNKNOWN保留旧nonce，缺少明确放下不确定尝试后再发新轮的操作。S128–130的空白与技术停止不能被当作人物取材或事实问题掩盖。

验收围绕完整恢复链：已提交但HTTP响应未收到、在途请求、已知失败、canonical记录中的不确定交付、服务重开、原nonce未出现、同nonce不同原文、身份不匹配、完整性失败。多次查询都保持Admission/Publication/审计计数，不启动执行或cold recovery；成功只清匹配的原草稿，不覆盖用户后来改写的文字。只有用户明确确认放下原不确定尝试，再明确发送，才产生新的nonce与生成。

## 仓库能力比较与实际接缝

| 现有入口 | 已有机制 | 本片复用与限制 |
| --- | --- | --- |
| [ApplicationFacade.submit/follow/wait](../../src/dynamic_subject_agent/application.py) | submit按命令指纹与幂等key识别同一工作；follow看到pending会调用`_start_resume`，wait也可能进入follow | 已完成重取有效，但不能把lookup别名接到submit/follow/wait。纯query必须另行进入只读链 |
| [SubjectRuntime.admit/follow/_observe](../../src/dynamic_subject_agent/runtime.py) | admit在Timeline.admit之前仍做command校验、artifact恢复与Cognition preflight；Runtime.follow本身只观察；`_observe`按canonical状态读取Outcome或Failure | 复用结果映射/只读观察，避免经过admit、resume、cycle或恢复入口；Facade.follow的执行行为和Runtime.follow的观察行为不能混为一谈 |
| [TimelineEngine.replay_first_life_request及idempotency_claim](../../src/dynamic_subject_agent/timeline.py) | LIFE replay以`authority_scope_id + key_digest`找canonical操作，并比较原请求digest；通用Admission已经保存payload_fingerprint并检测冲突 | 复用同一canonical索引/原命令核验模式，给whole建立准确只读入口；不借LIFE/schema3权限，不增加聊天store或新claim |
| [RuntimeLease与_RuntimeWorker](../../src/dynamic_subject_agent/host.py) | Lease核当前binding permit；worker的单线程拥有Runtime及thread-affine SQLite writer，现有call同步排队 | 新读接缝仍须守active identity与worker线程归属。源码当前没有独立`worker_read_call`；若新增，只提供闭集读方法，不把方法名开放给Adapter。正在生成时不能为了查读启动另一writer或重开runtime；可以返回已核匹配的active pending，无法及时核实则明确unavailable，不猜not-found |
| [原人物Adapter与页面](../../app/desktop/original_whole_chat.py)、[页面草稿逻辑](../../app/desktop/static/original_whole_chat.html) | scope分离sessionStorage草稿；原nonce/request_text保留；成功匹配才清草稿；known terminal清nonce；pending和网络未确认不重发 | 刷新、原请求恢复、轮询改用pure query；查询参数用保存的request_text，不能用用户后来改写的draft.text。旧`/send`只用于用户明确开始新请求 |

原人物whole状态查询、当前active身份校验、历史开关及revision、模型票据/metadata账均已有；本片不改变Sender、系统政策、素材、输出schema或模型参数。canonical失败仍不是committed对话轮，不为了显示恢复结果把它送入两完整轮exchange。

## 两处一手来源与采用判断

| 来源 | 官方事实 | 本次设计类比及排除 |
| --- | --- | --- |
| [RFC 9110 §9.2.1–9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1) | safe讨论请求语义的只读性；idempotent讨论重复同一请求的预期效果。规范限制不具备幂等保证的自动重试；“重复效果相同”并不等于没有写入 | 查询与重新提交分成业务入口，不能因原nonce幂等就让刷新调用submit。若本地HTTP为避免把原文放入URL而使用带token的POST查询，仍需以实现证明其无业务写入，不把POST称为HTTP标准safe方法。RFC不能替本项目证明零模型或零Admission |
| [Google AIP-151：Long-running operations](https://google.aip.dev/151) | 操作返回可追踪token；GetOperation提供进度/部分失败metadata，最终response/error与未完成状态区分。启动失败与执行中失败分开处理 | 采用独立操作状态/结果读取的形状，复用本仓OperationRef和canonical结果。Google的Operation、SDK、服务、保存期限和并行策略不引入本仓；本项目的UNKNOWN表示交付不确定，不能套成普通pending |

两出处已足够，停止扩查。纯工程请求恢复不需要新增哲学/心理学解释，不证明AI记忆或关系成长。仅借机制，没有复制外部源码或安装依赖；RFC文本保持链接归属，AIP页面标CC BY 4.0、样例Apache 2.0，本文不复制样例代码。不存在金融、云端或外部账户操作。

## 最小Facade接口建议（待core所有者落实）

最初建议`ApplicationFacade.lookup_original_whole_request(request_id, original_text)`；root/core协调后选择复用现有`SubjectCommand + idempotency_key`作为纯query输入，入口复用发送时同一构造函数，不再另发一套消息指纹算法。方法名/typed wrapper由core定稿。仅接受当前Facade绑定身份/Timeline、whole闭集chat字段、原文字规范化及`original-whole-<request_id>`命名；nonce合法但文字不匹配明确报冲突；无当前scope内claim返回not-found，未知资格或identity不匹配不披露别处记录。

返回要区分两层，而不只给一个模糊ok：

- **查读是否可核实**：外层`query_status`为found/not-found/unavailable/failed-closed，冲突、未授权或完整性失败用闭集code表达。不可核实不能当作“原请求未提交”，不修改全局ApplicationOperationStatus。
- **已有请求状态**：仅found时有匹配的OperationRef及原ApplicationOperationResponse，包含pending、terminal、failed-closed、unavailable、unknown；只读取既有已裁决Outcome/Failure，不启动resume。active pending只表示原工作仍在，不提供另发许可。

尤其是canonical本地FailedClosed映射出的UNKNOWN，与本次查读自身失败要分开。前者的原工作已被本地终态fence保护、远端交付仍不确定，允许UI展示“明确放下此尝试”；后者未核实结果，不允许悄悄清nonce或启新请求。若接口采用outer verified标志加inner operation响应，需要保证verified不能由Adapter猜测。

Core查读不得admit、execute、claim、record、cold-recover、懒恢复、初始化账本或变更身份/history；应复用同一canonical store按scope查claim，再核完整原命令指纹和已有结果完整性。root/core本轮选择Host独立readonly connection与single read transaction，避免排队等待同步模型请求；它只读同一个canonical store，不增加writer，也不把连接本身当完整性证明。具体方法及permit/事务核验由core所有者落实。停止/重开本身的已批准cold recovery与query分开，query不能调用composition重开来“修好”结果。

## 入口草稿与UNKNOWN操作合同

刷新和初次加载若sessionStorage有原nonce/request_text，只查原结果；已知pending继续纯轮询。not-found只说明当前已核scope未有此claim，保留草稿，不自动发送；用户下一次明确点击发送才决定新请求。网络或完整性未确认继续保留原nonce。查询成功的已提交结果仅在nonce、scope、原request_text及当前draft都匹配时清文字。

canonical本地终态的UNKNOWN可以显示说明并让用户明确确认放下本次尝试；此动作只清自己的旧nonce/request_text，保留当前草稿及canonical尝试/metadata/用量，不宣称撤销远端发送或删除数据。确认之后仍不提交，下一次用户明确点击发送才产生新nonce。不允许对仍在执行的pending这样处理。

不采用：lookup内部调用submit或Facade.follow；刷新重发；自动重试；未知时重置预算或伪造取消成功；第二份聊天记录；清用户改写草稿；扩大历史、引入生活/S1或改变旧服务/原variant。数据、Provider、slot用途不变，恢复query只有本地已存在数据读取。

本文件为开工准备，尚未实施core或入口，未运行真实调用。最终方法名/DTO/读接缝由root与core所有者约定；入口所有者接到该约定后才实现。
