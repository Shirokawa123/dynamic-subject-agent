# S115：空白输出的证据、官方约束与最小干预

## 结果、缺口与验收

用户结果是得到可稳定交付的回复，并知道失败发生在哪一层。S112一个、S114三个最终正文仅含ASCII空格，均stop且远低于4096输出上限；现在不应继续优化人物提示而忽略交付失败。当前只能修复明确的请求引导缺口，不能在无新调用的情况下宣布服务稳定。

验收：用保存的最终字段重建安全响应，重现四次空白与成功对照的原解析结果；明确重建包不是原始HTTP包。新候选只追加一个合法输出JSON格式示例，全部原材料、原策略前缀、思考强度、JSON模式、模型、额度和本地结果裁决保持。新字节与旧字节逐项可审，无sender或自动重试。实际效果必须标未验证。

## 定向官方核对（2026-10-01）

已用context7-mcp解析`/websites/api-docs_deepseek`并查询JSON/思考/格式约束；同时打开官方原页。首次两个不带末尾斜杠的web打开超时，带斜杠重开成功，不据抓取失败推断产品网络故障。

- [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)：指引包括json_object、JSON提示与期望JSON示例；承认该模式可能空内容，并建议调整提示。它支持本次补充合法格式示例，不证明本样本唯一根因。
- [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：当前response_format只列text/json_object；high、thinking enabled、非流式和4096都在参数范围。文档对无JSON指示时一直空白到上限的警告，与本例“有JSON指示、stop、低用量”的表现不同，不能直接套用。
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)：content与reasoning_content是不同输出，普通无tools对话不要求回传隐藏推理。现有链只使用content并丢弃reasoning，不能从隐藏推理补答；没有找到支持“必须加temperature”或“思考与JSON绝对不能同用”的证据。
- Context7返回的[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)资料说明strict属于beta工具schema路径，不能把其他厂商的json_schema参数直接塞进当前response_format。暂不改endpoint、引入工具协议或新增凭据用途。

示例缺失是文档引导缺口，不等于已证明请求参数无效；接口参数说明强制JSON指示，没有把缺例列为HTTP错误。本项目直接发送HTTP JSON，thinking位于顶层符合API字段；SDK示例的extra_body仅是SDK参数装载方式，不应照搬为本项目wire字段。

没有引入第三方代码或依赖，使用现有stdlib/typed投影/严格解析器。该问题是生成协议与接口约束，哲学/心理学不能定位其工程因果，不套用人物心理理论。

## 竞争解释与仓库证据

1. **请求缺少合法格式示例可能影响输出。** 现有system只有`{reply_text,language,...}`字段名简写，不是有效JSON。若补例有用，同一失败输入在只追加示例后应更常得到完整且符合原schema的正文。既有很多成功请求也缺例，因此这是可试干预，不是已定根因。
2. **服务端JSON生成/处理偶发空白。** 官方承认这种现象；若补例后仍失败，需要进一步隔离JSON模式与普通text格式等变量，而不能继续堆人物内容或增大max_tokens。当前没有服务日志，无法区分模型生成与服务端后处理。
3. **本地取错/清理字段。** `_ObservedTransport`在后续严格解析之前独立json.loads(response.body)，直接保存message.content；清理reasoning_content在另一个解析对象上进行。四份保存的空格因此早于JSON正文解析/推理清理，并非这些步骤把正常正文清空。原始HTTP包未保存，不能宣称排除所有上游/传输实现因素。
4. **截断或token耗尽。** stop及239/212/213/321个completion tokens与该解释不符；不提高上限或将空白接受为成功。

复用：S113的typed候选builder已能恢复S114精确wire；严格DeepSeek parser、A三字段/B两字段验证不变。新预览另设版本，不更改S111–114已批准策略/manifest。只在固定system末尾追加格式例，不引用新的角色事实或额外历史，不拼入用户文本。

未采用：同时关闭思考/改温度/换模型/换JSON模式（无法区分变量）；beta strict工具协议（非必要新接口）；读取隐藏推理或修补无效JSON（扩大接受面）；自动重试/返回预写道歉（掩盖失败且触碰原0重试范围）。格式示例可能被照抄或影响披露选择，后续记录应独立标识，不把非空或合法JSON等同可用交流。

## 实际离线结果

新增`first_life_reply_protocol`只在S113候选system末尾追加合法JSON例，原user JSON/参数/原提示前缀均保持；旧builder、策略、资格、账本不改。预览不能成为ModelGateway任务，未注册sender。`prepare_s115_protocol_trial.py`验证原报告规范摘要与实际wire，生成3个空白输入＋1个成功输入各自原/新请求，交错首个变体，8次仅为待审上限。

独立只读审计核对全部34阶段出站摘要；现有两次实施提交的原parser在安全字段重建envelope上重现4个原空白码、28个成功JSON值，2次网络无响应跳过。新模块只处理回复阶段：24条中18条保持原结构化结果，4条空白仍失败，2条无响应明确unavailable；未保存原HTTP envelope或隐藏推理，不声称全包重放。

四次空白对照：S112花瓶A第3步57空格/13,033请求bytes/2,783 prompt＋239 completion；S114花瓶A首轮46空格/6,450 bytes/1,354＋212；纸船A重启后50空格/6,653 bytes/1,410＋213；纸船B表达61空格/6,087 bytes/1,292＋321。均stop、同high/JSON协议。相邻成功具有相同system或缓存命中量，故输入长度、冷缓存、重启或路线都不是已证实的充分原因。

必要检查55项通过（新协议11、S113候选11、既有安全诊断33）；随后只重验新增kind严格类型约束1项。独立复核通过：4对仅追加suffix、两份来源及包摘要一致、8个case/variant唯一、占位示例回声独立标识。没有产品调用、凭据读取、真实账本写入或实际可靠性提升证据。候选包摘要为`4e4ed6a664821d18f827d7a6f62d50aeec8b07222709ef238a9853bbba2e88e5`。
