# S143开工证据：在线页面、生活机会与分享入口

用户结果与缺口见[唯一current](../slices/current.md)：S142真实Facade/CLI闭环成立，但没有可体验的生活分享页面。先比较仓库已有能力，不重做模型选择、出站字段或持久生活机制。本轮context7-mcp resolve `MDN Web Docs`实际返回`TypeError: fetch failed`，按skill回退查官方一手文档，没有伪称查到Context7结果。

## 定向资料与适用机制

| 来源 | 已核机制 | 本片接法和限度 |
| --- | --- | --- |
| [MDN Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API) | visibilitychange区分可见与隐藏；focus/blur不能可靠代表隐藏，隐藏页timer会受节流 | 不按JS timer触发次数或Date.now差补900秒。页面只持有一个随机session，服务端原LivingClock以monotonic/短租裁决；隐藏时停止新机会，返回重新建在线基线。可见性是当前入口工作假设，不取消离线生活最终目标 |
| [MDN pagehide](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event) | pagehide并非每次关闭都能触发，移动端尤其不能依赖关闭事件 | pagehide/freeze用于尽力停心跳，不以收到关闭回执作为唯一停止条件；失联后的15秒租自行失效，恢复不累计离线，草稿仍沿既有保存逻辑 |
| [Chrome Page Lifecycle API](https://developer.chrome.com/docs/web-platform/page-lifecycle-api) | frozen会暂停timer/fetch callback；终止/丢弃可能不可观察，hidden是常见最后可观察状态；pageshow可来自缓存恢复 | 状态恢复先查读已提交结果和原nonce，不拿恢复事件重新发送；不装service worker、push或新后台服务来规避浏览器生命周期 |

以上是浏览器工程事实；15秒、900秒和只在页面可见时推进属于已有合同/当前产品选择，不由文档证明合理分享频率或人物心理。查询应保持只读，在线心跳应是明确POST用途，不能因GET/档案/refresh重播模型。

## 仓库比较与取舍

- `living_activity.py`已有LivingClock、permission、独立share gate与两轮窗口；`ApplicationFacade`/Host已有living查询、控制、advance与准确preview。保持模型提议、Python裁决、唯一canonical/Publication，复用而非添加时钟数据库、队列或第二写者。
- `app/desktop/shared_activity_chat.py`及其HTML已有异步动作、原request回取、当前方案、来源停用与whole草稿；`serve_shared_activity_chat.py`已有独立root/marker/health和new/reopen。在新living入口适配其生命周期，不将旧shared资格转换或复制旧记录。
- legacy S105已做单窗口短租及助手-origin消息；其60秒/单项目终点、旧budget和旧projection不适用新S142。只复用观察与失败呈现思路，不导入旧权限或调用额度。
- 新生活share为单独stage/明确状态，与choice异步完成分开。UI只显示真实已提交消息；false、失败和暂停不是分享正文，不伪造用户轮。
- 不新增第三方依赖或复制外部库源码；本仓现有标准库服务、原JS事件和server lease足够。Web Locks/BroadcastChannel等不作为前置：服务端唯一owner和单写者才是裁决权威，浏览器选主最多优化请求，不能代替后者。

本轮是UI/工程接入，没有新增心理、记忆或人格模型。S142分享相关性研究的类比仍不能证明自然度；实际消息是否有内容、接话是否忠实应在运行时另评，不能以字段与测试数代替。

## 可观察验证

新空入口0模型/默认暂停分享关闭；明确开启后在线唯一owner、900边界、断租/刷新/重启不补算；真实新方案后独立share与助手归属；未回/日限/false不重复；暂停、needs_attention与来源停用阻旧候选；query/nonce/草稿/另一页不能多发。合成时间和真实900秒分开记录，真实首失败保留且0自动重试。阶段源码复核后提交push再跑自有真实资源，正式空入口与验收root隔离。

## 接入证据触发的调整

第一版为避免pending查询抢stage授权短锁，只在空闲时发advance型心跳；Provider等待超过15秒会让lease失效，先前累计也丢失。这把“在线累计”变成必须静默900秒，对实际边聊边用不成立。root据该代码证据决定本片修复，而非将其记录成新的永久限制。

沿原LivingClock和Facade新增模型-free在场接口：核active identity/当前权限/session，仅更新进程内lease与累计，达到900也不消费或执行模型。页面独立presence计时器在聊天等待时仍续租，空闲advance再以freshcanonical资格消费一次机会。查询不续租；暂停/隐藏/失联/重启仍停止，不补离线。不增加Provider材料、policy、模型阶段、持久表或后台服务。MDN/Chrome生命周期证据仍适用，本次为工程交互接缝，不引入心理学机制。
