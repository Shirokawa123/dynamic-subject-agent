# S113：空白正文与安全网络分类

2026-10-01开工证据。本任务只做离线诊断/修复；真实Provider调用、真实凭据读取和网络探测均为0，不使用S112余20次。公开官方文档检索不访问产品Provider接口。

## 用户结果、证据与验收

用户结果是让一次失败返回可区分、可审计而不泄漏内容的原因；不宣称因此消除了服务端空白或实际网络故障。

已核对`CONTEXT.md`、D-004/D-005、S112报告与已提交`continuous-comparison.json`：A花瓶失败阶段`finish_reason=stop`，最终正文57个空格，旧码`response-content-json`；两个B表达阶段仅留`transport-network`，耗时约5.019/5.003秒，无响应模型/用量。旧证据没有异常类型或errno，无法追认DNS、代理、TLS、连接重置等根因，旧结果保持原样。

可观察验收：同一57空格正文离线重放区分为`response-content-empty`；非空坏JSON仍为`response-content-json`，`length`仍优先`response-truncated`。真实urllib传输接缝的合成`URLError(reason=typed exception)`及直接异常能产生闭集安全码，未知/字符串reason仍是泛化网络失败。经现有safe_diagnostics调用者传递，非诊断路径保持ProviderFailure的code/失败语义，请求字节不变；0自动重试，不记录host、URL、exception str、header、key或隐藏推理。

## 一手来源与适用性

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)：JSON模式仍可能偶尔返回空内容；示例与JSON提示有助输出但不是无空白保证。这里只据此把空白识别为独立技术失败；不原地改S111/S112提示、不增加重抽。官方说明不能证明本次空白的服务端具体原因。
- [CPython 3.13.9 urllib.error](https://github.com/python/cpython/blob/v3.13.9/Doc/library/urllib.error.rst)：URLError.reason可能是字符串或异常；HTTPError是URLError子类。类型检查只展开异常reason，HTTP分支仍先处理；字符串不做关键词猜测。
- [Python socket异常](https://docs.python.org/3.13/library/socket.html#socket.gaierror)：gaierror对应地址解析失败，timeout为TimeoutError别名。只使用类和数值错误码，不保存地址/描述。
- [Python ssl异常](https://docs.python.org/3.13/library/ssl.html#exceptions)：SSLCertVerificationError是证书验证失败，SSLError表示TLS层异常。类型足以分类，不读取verify_message/reason/library等可变文本，不改TLS安全配置。
- [CPython OS异常](https://github.com/python/cpython/blob/v3.13.9/Doc/library/exceptions.rst)：ConnectionRefusedError/ConnectionResetError/ConnectionAbortedError/BrokenPipeError由特定OS错误对应。使用本平台errno符号（含有定义的WSA别名），未列出的errno继续泛化；不凭耗时或错误字符串推断阶段。

已用context7-mcp解析并查询`/python/cpython/v3.13.9`与`/websites/api-docs_deepseek`；Python的精确reason/SSL定义补看官方文档/源码。无第三方依赖或代码引入；复用现有stdlib和Provider失败封装，没有新增许可、维护或数据用途成本。心理/哲学解释对本次传输及解析工程不适用。

## 可证伪假设与实施选择

1. 最直接的空白分类缺口：现有解析在检查content类型后立即json.loads。预测在JSON解析前增加严格字符串空白检查，即能让已知57空格与坏JSON分离，而不把截断空白误作普通空白。
2. 最直接的网络信息丢失点：DeepSeekUrlLibTransport先把URLError及其他异常统一成NETWORK_FAILURE，safe_diagnostics已拿不到其类型。预测在该catch处只保留一个闭集类别，并在已有诊断路径消费，即可区分合成DNS/TLS/connect/reset；默认ProviderFailure code仍不变。
3. 不能验证的历史网络根因：没有原异常类型且本轮不允许实际探测，故不排列DNS/代理/TLS的发生概率，不把合成重放当成复现真实故障。

采用本地固定类型/errno分类，复用既有DeepSeekResponseDiagnosticFailure承载闭集类别；通用ProviderFailure code不变，helper未启用safe_diagnostics时只抛原ProviderFailure。未知异常不带原对象/文本到诊断字段。未采用错误日志全文、环境/代理扫描、连通性探针、异常字符串匹配、新HTTP客户端或自动重试：均不是修复分类缺口所必需，部分会扩大数据或执行边界。

## 已验证结果

先写`tests/test_reply_review_diagnostics.py`再改实现。确定性红反馈命令（先设置`PYTHONPATH=src`）：

```powershell
python -m pytest tests/test_reply_review_diagnostics.py -q -x --tb=short -k 's112_committed_blank'
python -m pytest tests/test_reply_review_diagnostics.py -q -x --tb=short -k 'url_transport_preserves_only_type_diagnostic and transport-dns and urllib-reason'
```

分别得到1失败（0.81秒，实际`response-content-json`不等于预期`response-content-empty`）和1失败（0.61秒，实际`transport-network`不等于预期`transport-dns`）。第一条直接读取已提交S112记录的57空格最终正文并核验文件未改变；第二条穿过实际`DeepSeekUrlLibTransport`的`_opener`接缝，注入`URLError(socket.gaierror)`，使用纯本地假resolver，不是真实凭据或网络。

实现后的同一测试文件33项通过，0.33秒。新增空白码在原size/model/finish/usage等检查之后、JSON解析之前判断，因此`length`空白仍优先截断；非空JSON错误保持原码。网络类包括地址解析、TLS证书/TLS、连接拒绝/不可达、重置/中止、断管和已有timeout；类型优先、errno补充，reason只有限展开异常，未知或循环包装均回到泛化网络错误。两个已有first-life Gateway调用场景分别保留空白/DNS安全码。

每种合成网络异常分别核对单次opener调用和原ProviderFailureCode；未开启safe_diagnostics的helper不暴露新增诊断对象。直接TimeoutError保持DELIVERY_AMBIGUOUS；被URLError包装的异常仍保持原NETWORK_FAILURE语义，只在明确诊断层细分为timeout。所有异常分类都不证明服务器是否收到请求，不返预算、不触发重试。

必要合并回归106项通过，147.55秒：`test_reply_review_diagnostics.py`、`test_character_reply_review_diagnostics.py`、`test_deepseek_cognition_provider.py`、`test_first_life_reply_live_provider.py`、`test_first_life_reply_routes.py`。使用本轮独占的新系统Temp目录作为pytest basetemp；包含旧诊断Facade审计/重启与默认模式、真实urllib接缝/固定请求、S112预算发送0重试及S111精确wire兼容。原有两个未跟踪测试目录未操作。`git diff --check`通过（仅既有Windows换行提示），没有debug日志、环境探针或临时修复脚本。

## 剩余不足

本改动改善的是失败分类。它没有修复Provider生成空白，也没有让历史两次网络失败重新拥有已丢失的errno/类型；相关原因继续未知。未来遇到新异常才可能得到细分码。类型/errno只能指示系统报告的失败类别，不能证明代理/服务端故障、准确发送阶段或是否计费。没有拿离线合成异常冒充真实网络故障复现，也没有新的真实成功率证据。
