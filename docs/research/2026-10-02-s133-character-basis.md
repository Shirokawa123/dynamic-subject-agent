# S133准备：在聊天里核对人物依据

2026-10-02，S132仍是唯一执行切片。本文件只形成后续开工证据，不启动新增运行能力。

## 用户结果与已证实缺口

用户可从当前人物聊天入口展开起点、已审认识与作者解释，知道哪些内容确实属于当前封存版本；查看后回到原草稿继续聊。S129/130真实回复仍有无据过去细节，当前入口只有历史/开关/恢复，用户无法核对已有资料支持到哪一层。此结果不自动判定每条模型回复真假，也不改变人物定义。

## 来源、机制与取舍

- [Microsoft Research的人机交互指南](https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/)与[G11](https://www.microsoft.com/en-us/haxtoolkit/guideline/make-clear-why-the-system-did-what-it-did/)要求在适合时让用户获得解释。这里采用按需展开、明确能力和限制；查看“既有依据”不能标成模型真实思考过程或本轮全部采用的资料。
- [W3C PROV Overview](https://www.w3.org/TR/prov-overview/)区分产生资料的实体、活动与负责者；本次只借鉴来源分层，不引入RDF、PROV库或新图存储。封存事实/信念、作者解释、模型表达属于不同对象，不能把后者冒充原作事实。
- 仓库`validate_reviewed_envelope`已完整校验asset、definition、source mapping，`sealed_model`重建可运行的认识。`runtime_asset.eligible`保留fact/belief、before/at、direct/linked-evidence；`personality`明确author-interpretation；`chat_organization`有core/episodes/details及claim_ids。Authority持有当前已验证envelope，Facade是唯一业务Interface。复用这个快照，避免UI打开本地EPUB或直接读Studio。
- 当前sealed资产不保留原EPUB页码/原文定位，`sealed_model`将evidence_ids设为空。不能给界面编造逐句原作出处；准确说明这里可核对的是已审封存依据，原始段落追溯尚未接入。源文件后来移走不应使完整封存资产的本地查看失效。

这是资料透明度和用户控制问题，不需要心理学模型解释，也不据透明度假设证明人物有心理或意识。搜索限于官方HCI指南、PROV规范及仓库实际接口；不复制第三方实现、不新增依赖，因此无额外许可证或外发边界变化。

## 最小接入与可观察验收

ApplicationFacade提供当前whole人物的只读basis DTO，经Authority核当前身份/准确版本/资产完整性后输出起点、认识条目、组织分组与作者解释，带清楚的资料性质与缺口说明。Adapter只呈现，不重新组装人物或读取磁盘路径；basis不进模型消息、不存第二份人物权威、不改资格/开关/Timeline。

入口按需打开/关闭，保留草稿和原请求；已知事实/人物信念/作者解释有可辨标识，起点前/当前有限知情仍显示。旧合同若无法安全给出同样来源则明确unavailable，不把空清单当人物没有知识。

验收：真实已审30项/4项解释与sealed内容一致；可按内容查看；打开/刷新/关闭/重开0模型、0Timeline写入，草稿保持；失效身份、篡改资产或关闭Facade不返回旧缓存；模型回复不自动被列为人物依据。原始定位缺口保留，不以“查看30条”宣称完成忠实度纠错。

不采用另一个角色卡文件、模型总结档案、聊天时强插来源、直接展示内部digest/ID、自动修订人物或将全部历史变成长记忆。其风险或成本超出本片结果，且不能解决已见的错误归属。
