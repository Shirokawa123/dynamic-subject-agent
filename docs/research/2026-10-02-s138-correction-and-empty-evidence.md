# S138开工证据与有界诊断

用户结果/完成条件见[S138](../slices/slice-138-correction-continuity-and-empty-diagnosis.md)，当前main80e2276的真实生产接缝合成复现见[baseline](../reports/2026-10-02-slice-138/BASELINE.md)。0真实请求已证普通纠错误拦＋持久阻断；只改current predicate仍被旧failure堵，单独改变prefix predicate才恢复，拆证7.12秒通过。临时全false monkeypatch不作为修复或产品权限。

whole应拥有独立disclosure-scope规则，区分交流内容/引用/过去转述与真实停止使用的当前行为；旧v1/FirstLife作用域不改。准确已知history-stage终态failure须complete frozen/terminal/canonical证明才能向前接续；无法证明一律关闭。真正撤回当前0外发，其后只允许cutoff后的安全窗口，原记录保留，不伪造成功回执。

此处修复是出站权限语义/恢复工程，不需要心理模型；语义判断不能由普通词是否出现定义。[Nissenbaum contextual integrity](https://nissenbaum.tech.cornell.edu/papers/Privacy%20as%20Contextual%20Integrity.pdf)的场景/行为区分仅为设计类比，不引入其理论作为可执行解析器或真实性证明。工程安全依据沿既有S131纯查询/S132完整冻结前缀合同；不加新依赖、Provider字段、schema或资格迁移。

## 空白路径：已证事实与假设

独立只读调查已执行Context7 resolve→query DeepSeek，再以官方API页补齐响应结构。当前safe parser在单choice、assistant role、合法model、stop、reasoning类型、无tools及整数usage/预算核验之后，对content=str且strip为空报response-content-empty；null/缺字段是response-content-json，JSON内部空reply是expression-invalid。Transport返回response.read原bytes，_ObservedTransport只独立观察并原样返回；cognition直接把validate后的reply_text作为Expression，没有其它正文候选。既有188/207 completion与stop不能证明非空正文，也不支持先扩大4096上限。

- [官方JSON Output](https://api-docs.deepseek.com/guides/json_mode)明确承认偶发empty；S129合法示例已实装，不能重复当新修复。
- [官方Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)将content与reasoning_content区分；推理不可拿来补最终回复。
- [官方Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/)描述content、finish_reason、可选reasoning token breakdown；未文档化message.final/refusal替代正文。

排名假设：①上游收到的content确实为空（当前更支持）；②重复JSON关键字段导致后值覆盖/本地解析失配（未证实）；③最终正文交付丢失（静态路径不支持，须实际digest对照排除）。stop表示停止，不承诺非空或正确；14/51不是统计因果结论。

观测脚本`observe_whole_reply_boundaries.py`仅安全标量/长度/摘要和固定协议字段存在性，不保存HTTP body、reasoning、任意错误或凭据；原请求/返回bytes不改变。零请求三种fixtures已区分raw empty、JSON内部空reply、合法最终正文，另核重复关键字段探针。Interface真实链里若已有清晰raw空content观测即可定位层并停止额外请求；原content非空却报empty或最终digest不同，立即停止真实调用并离线修本地缺陷。若未重現则最多六次有区分力观察，超限后只记录未知触发因素，不反复扫提示。

text-mode或thinking-disabled仅是可能后续对照，须准确新技术variant/审计，不在Transport偷偷改body绕过资格；本轮优先不改现行wire。无新依赖或第三方代码，纯Python标准库和已有生产Transport/Parser。真实话语仍仅canonical，日志/报告仅metadata，缺token breakdown保留None，不当0。

2026-10-03真实观察收口：首轮HTTP200/stop，原`message.content`为94字符字符串、strip后0，无重复语义键/替代final/refusal/tools，Facade报response-content-empty且0提交；证据见[S138 metadata](../reports/2026-10-02-slice-138/correction-metadata.json)。因此此次上游实际返回纯空白，尚未进入reply JSON解析；不是null/JSON内空reply或本地错选正文。completion219含reasoning_tokens124，不证明最终正文有效。服务内部为何返回空白仍未知，停止额外调用与猜测，不把现象定位冒称根因已修复。
