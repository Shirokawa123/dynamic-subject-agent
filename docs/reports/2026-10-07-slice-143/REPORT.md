# S143：生活、分享与聊天入口

2026-10-07，用户明确继续实际界面接入；基线main0462756与远端一致。唯一current已承接，开工证据见[浏览器生命周期与仓库比较](../../research/2026-10-07-s143-entry-lifecycle-evidence.md)。本片沿S142准确三用途/资料/DeepSeek/Windows默认slot；新独立入口默认暂停、分享关闭，不升级旧root或迁移记录。

开工只读health：8790、8791、8792均连接被拒绝。本轮没有停止或重启旧服务，也没有查其退出原因；不能据上一片的服务事实宣称今天仍在线。8792待新入口完成后初开验收；所有旧资源和临时目录保留。

本片的完成条件是实际页面可开启/暂停在线生活、控制分享、看到真实方案及助手-origin消息并接话；草稿/原请求/刷新/重启/多窗口不重复发送，查询不推进，默认空入口0模型。真实900秒HTTP驱动验收与浏览器可见持续15分钟分别报告；合成时钟不冒充现实等待，单链成功不证明长期人物质量。每stage1请求0retry、首次失败保留并停，不无限补抽。

源码阶段提交/push `dd62bc8fa50e6d9c78421eb920d56c71d9353506`，远端核对一致后，root已唯一执行真实900秒场景并交付新8792空入口。实际结果如下；后文实施检查按其历史阶段读取，不冒称整链/MVP通过。

## 实际交付与真实结果

新入口[http://127.0.0.1:8792](http://127.0.0.1:8792)，启动器[Start-LivingActivityChat.cmd](../../../app/desktop/Start-LivingActivityChat.cmd)。实际独立正式root为`C:/Users/30252/AppData/Local/DynamicSubjectAgent/living-activity-chat/entry`，默认暂停/分享关闭、history开启、空聊天/无E1/无方案/0模型，health为living-activity-chat-s143。后台启动未打开浏览器或抢焦点；旧默认启动器及旧root保持。

自有隐藏IAB页面检查空态与中文控件，输入自有非私人测试草稿后点击刷新和本地重开，原草稿保留且未发送；只清理精确匹配的自有草稿，没有碰用户草稿。复核正式入口仍0消息/0模型、permission revision0及默认开关完全不变；[初开摘要](entry-empty-metadata.json)、[UI摘要](ui-verification.json)、[空页面画面](entry-empty.jpg)已保存。截图不含模型正文。验证的是桌面可用画面及恢复，未做风格重设计或全部窄屏/缩放审查。

真实DEV root独立为`C:/Users/30252/AppData/Local/DynamicSubjectAgent/living-activity-development/s143/live-http-first-20261007-1`。未缩短或注入时钟：181次5秒间隔presence、实际elapsed `900.0603903`秒，server累计900/due=true；等待阶段audit与transport始终0、无canonical活动，之后才消费一次机会。此证据是**真实HTTP驱动在线**，不是浏览器连续可见15分钟的证明；pending保持在场由Interface/Node合成行为另证。

| 首次阶段 | 实际结果 | 证据与限制 |
| --- | --- | --- |
| 活动选择 | start，新文字构图方案实际提交 | wire/raw final/audit/canonical摘要一致；真实事件simulated=false |
| 独立分享 | true，126字助手消息实际提交 | 无假user轮；重启及原nonce回取保持0调用 |
| 首次追问 | FailedClosed，未提交普通回复 | HTTP200/stop，content72字符且strip后0；非JSON正文，error=response-content-empty |
| 第二/第三追问 | 未执行 | 首技术失败即停；本轮不冒称两轮接话/第三真实过滤通过 |

共**3首次真实请求、2提交（1活动/1分享）、1上游纯空白、0重试**。第一次追问reasoning通道非空（只保长度/用量，不保存内容），未发现另一final/refusal/tool_calls；不是被普通控制词误拦，也不是应用解析删掉了已有中文正文。已证明问题位于Provider响应的最终正文边界，服务内部为何输出空白仍未知；不推断协议、采样或模型内部根因，不补抽、不伪造reply、不把这次失败抹成完成。

首失败后暂停且needs_attention；runner最后明确控制为paused=true/share=false，revision3、attention清除仅表示本次显式收口控制，不表示回复故障已解决。自有HTTP服务及product正常close，exit1为首技术失败，留证完整、无I/O/关闭未知。正式8792新用户入口仍空/暂停/关闭，实际失败没有塞进用户窗口。完整[安全metadata](live-entry-metadata.json)仅计数、usage、边界与摘要，正文仍只canonical。

root只读核独立audit逐值等于metadata（2complete+1failed-closed），另用全部生成POST关闭且transport拒绝任意请求的临时观察页查看已提交内容，观察前后audit仍3，0新增调用。画面中的消息确为assistant-share，当前方案及分享重点一致，保持构思想法语义，没有宣称已完成图片或催促回复。内容围绕原创人物草图、可爱优先与不熟悉武器画法的取舍；细节复述偏多，仍较像方案说明，不记为人物自然度通过。原文未另存报告/截图；临时观察服务已关闭。

安全首景/空态/UI metadata最后独立只读复核接纳，五层摘要一致、失败与exit1/最终控制记录一致，无新事实矛盾；未读取正文或追加模型。首景metadata SHA `c18eeda0d76627c3f2e58f557351fd4ae02f4509a9c1d18f12de7d5fde175184`。root语义判断与复核者的工程摘要结论分开，不让只读metadata证明自然度。

## 未解决与下一步

UI闭环和真实900触发/分享已成立，当前完整连续接话、上游空白稳定性和人物自然度未通过；S142旧五阶段成功证据保持但不能覆盖本片失败。下一优先在既有用途内有界改善最终正文交付与分享后的自然接话，使用真实内容和界面整体评，不继续堆规则或后移人物体验。浏览器真正持续可见15分钟、长程活动、离线生活仍分别需要验收/具体合同，未启系统服务/通知、Reflection/人格重写、云、删除迁移或新资料/凭据用途。

## 源码阶段已完成

独立entry和runner复核均通过，已发现的reload race与replayed误判P2均关闭。presence与has_prior最终源增量已接纳，root另读关键Host/Adapter/clock接口后接纳；没有Provider材料、字段、协议或权限扩张。正式初开、真实900和实际画面仍待此阶段提交/push后由root执行。

必要验证：新entry11去重用例按首批/修后全部通过，最终3项并发重核通过；49个S142/档案/composition/旧shared受影响行为通过（338.64s）。presence后4个新增/修改Interface和Node行为通过，最后旧S142直接online和准确三用途wire/重开窗口两项smoke通过（62.57s）；组间有重叠，不汇总成产品效果分数。全部合成transport、0真实/0key/0用户焦点，临时目录保留。

pending20虚拟秒验证先前10秒累计保留且只有原reply一次，presence无模型/DB与registry字节不变；90次合成presence到900不消费，wrong revision不消费、空闲仅一次choice，其他owner/暂停/断租/重开守界。Node证明独立timer不被pending阻塞、草稿不发送、隐藏停止；第三准确preview/wire exchange空而has_prior仍true。曾因测试中canonical_path探针排队model lane导致fixture超时，已将路径获取移到pending前，未放宽业务或抹去失败。

## 实施中已定位的接缝

新HTTP并发检查定位到状态查询与stage初始授权短锁竞争，可在发送前错误失败（0transport）。修复方向是pending只呈现已核cache，不拿cache做发送依据；纯权限查询仅由Authority验证当前active living identity并双次读取，不竞争普通历史锁。fullcanonical/UNKNOWN/资料及发送资格仍关闭；foreign nonce在已有stage期间只返回busy，等结束再查精确canonical。

UNKNOWN后的新入口应显示真实needs_attention，而非因旧whole entry读取失败直接退出。仅新living入口处理Facade精确typed状态，主聊天显示presentation_blocked，不把archive可读已提交前缀当作下一请求可发送；不修改旧Entry/原记录或未知恢复fence。

独立runner复核发现异步成功canonical回取为replayed却被误判失败，已最小修两处：接纳成功回取，同时两种成功状态均独立核真实elapsed≥900；恰1transport/audit与raw/value/canonical摘要核对保持。纯fixture/preflight0模型通过，增量复核接纳，runner冻结SHA `897dc71eee825f7e39aa7559a2a8c49d36ae341ae04774500dbf37e34767ca5a`。

独立entry复核另发现reload在父类解锁后清请求map，可能擦掉另一窗口刚登记的新nonce；实现owner正在将整个override收在同一临界区，再做必要验证与增量接纳。旧手动按钮由新HTML明确隐藏，未把隐藏残留当可操作缺陷。合成日限fixture曾先走到合法keep导致无新方案，已修fixture按真实阶段再revise，未放宽业务gate。

上述第一版增量复核已接纳，49个S142/旧受影响行为通过（338.64s），新Entry11去重用例及最后3定向修复复核通过，全部synthetic/0key/0真实。随后root评估代码证据发现pending>15会丢此前累计，不将“必须静默900秒”留作产品要求；在本片内补模型-free presence与活动请求分离，必要新行为完成后再次freeze/增量接纳再提交真实验收。原已通过旧集不因测试数量再全部重复。

presence已实现为Facade-only typed接口与独立5秒页面pulse，只续租/累计，不消费机会或读取fullcanonical/模型。stage空闲后online action才fresh核验并消费；客户端恢复/隐藏不补算。另按既有S132“仍表示此前确实交流过”合同修正verified原records的has_prior，第三完整历史过滤后仍为true；不新增字段、投影用途或人格事实。相关Interface/Node行为待最终结果承接。

真实验收helper随presence作技术适配：等待900为独立max_requests0/transport arm0 stage，再独立choice一次，原≤5首次/0retry/首失败或无方案/false停止保持。新runner SHA `f69b2d4f04bbc2eee1037c5dcf245f6cbb2ea8841d2f2150e59ff6d8df7859a6`、scene canonical SHA `badb3381b75958adb20c18bd7b54d24bb467dff3175ba5e7ecdb3e3149eda508`，只读增量复核通过；S142准确对象/observer原字节保留。纯fixture验证900、断租和提前due均符合闭锁，0新LIVE/模型/key。
