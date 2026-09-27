# S107：保留原账的开发额度追加

用户已明确批准开发累计24→36，从原200内最多新增12，日6/2及数据用途不变。用户结果是继续有限验收，同时已用次数不丢、旧窗口不被悄悄算错；当前109/200、开发24已满，不能仅改显示或改成非开发调用。

仓库已具CharacterChatBudget全局账与FirstLifeBudget同事务life/day/dev claim；life链初始描述固定24，旧reader遇第25个development row必拒绝。直接把常量24改36会改旧链初始摘要、破坏历史；另建账或改DEVELOPMENT_SCOPE/False会绕过已用量，因此不采用。

复用既有BEGIN IMMEDIATE/Synchronous FULL事务，不新增SQLite配置/依赖。定向查[SQLite原子提交说明](https://www.sqlite.org/atomiccommit.html)：单事务修改要么全部成立，要么不成立；用于grant与存在见证同事务追加，以及claim前额度核验。复核[OWASP逐请求授权](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)：无明确授权保持旧限额，每次claim重新验证。这里只借成熟机制，不复制外部代码；本纯预算工程不引入心理学类比。

实施选择：同attempts.sqlite3新增一次性grant表，精确固定批准ID、DEVELOPMENT_SCOPE、24→36、原config摘要、批准时不可变life前缀与grant摘要。原config/stage/life rows和既有hash链保持原值。SQLite user_version=0表示原格式、1表示grant格式的存在见证；本仓库两budget类原先未使用该字段，root只读真账确认当前0。表/行/摘要缺失或不合规则拒绝，不自动补回授权。预算被移出或截短的异常仍需原累计head/前缀验证。

旧reader兼容边界：grant本身不会把已用24改掉；若测试确认，追加时旧reader仍可读原全局/day数。第25次开发调用后旧FirstLifeBudget必失败关闭，不能宣称一直兼容。因此真实追加调用前必须让所有服务该账的旧FirstLifeBudget进程重载新版reader。正常CharacterChatBudget只读原全局账仍应兼容；需要明确测试，而非凭未报错推断。

验证：未批准仍24、精确确认幂等36、批准前旧行/链完全相同、损坏与未知version拒绝、并发最后一个名额只成立一次、真实日期/全局200继续限制、正常用户调用不吃开发子额度、旧reader在24及25两侧行为。测试只用新临时账；生产授权由root在稳定复核后明确执行，不由测试初始化顺便增加。
