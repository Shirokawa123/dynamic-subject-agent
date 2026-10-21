# M002：显式冷资格续接

本仓提供共用底座，唯一游戏任务仍在独立产品。此合同是工程候选，未应用于用户canonical；M002模型用途批准不包含数据升级/安装，续接必须另有准确计划的同意。

用户结果：保留原人物、Timeline、原请求及完整旧发表；原文字可接到typed点击/文字，重开仍可按原UUID只读查询。之前观察器只有元数据/拒绝证明，没有正向续接能力。现在增加ApplicationFacade.prepare_memorie_continuation / apply_memorie_continuation，沿LocalIdentityAuthority实施；默认open_memorie_native_product和普通非空rebind仍不隐式升级。

## 来源与取舍

复用Studio不可变资格后继、Host单写者/branch governance、完整Publication链校验、原UUID只读查询与生产composition。普通换绑创建新空存储，不能保留同一段经历；拷贝旧文本到新人物也不能保留原请求/发表。选择稳定binding_id、scope和canonical存储，只在显式续接事务内递增binding revision/epoch和当前资格，旧完整绑定像封入回执。历史governance成员仅能由这一准确旧像校验，旧qualification仍从Studio正式验证。

通过context7-mcp查[SQLite ATTACH](https://www.sqlite.org/lang_attach.html)与[super-journal](https://www.sqlite.org/tempfiles.html)：磁盘main、rollback journal和同步打开是多库原子提交的前提。本实现仅接DELETE/EXTRA，不用WAL、immutable、nolock或备份覆盖。按[SQLite安全表重建顺序](https://www.sqlite.org/lang_altertable.html)扩展subject_event的事件闭集，旧行逐值复制，提交前核两库外键，提交后重新启用外键。纯持久化工程，无人物心理机制变更或新依赖。

## 准备、批准、切换与恢复

1. 显式请求指定state/product parent、已批native receipt与新audit路径；准备只读，先核原intent-3/schema1、closed gate、无active/draining lease。核完整旧Publication、每个原UUID claim与所有操作均completed；文件摘要和源basis精确冻结。暂不接受旧失败/未发表操作，不重发它们。
2. 另一个typed consent必须准确匹配plan digest且data_upgrade_confirmed=True。旧观察器的apply_supported=false不变；元数据观察和M002用途回执均不能代替此同意。再次准备核源未推进，再写registry pending目标；普通开库会拒绝pending状态。
3. Studio发布准确intent-3→native的同来源/同snapshot后继，资格本身不授予非空Admission。进程registry和closed lease拒绝第二写者；原Host DB为main，原Timeline以ATTACH进入同一EXCLUSIVE事务，重新核源绑定/gate/文件摘要/lease。
4. schema11在原库新增typed输入和续接回执，扩展原事件闭集，原命令/claim/Outcome/摘要链逐值保留。Host当前绑定与新的branch governance事实、Timeline gate/manifest/receipt一起提交。Timeline控制库与旧审计不改，无第二canonical。
5. 切换后的完整前缀/资格/回执再次验证，再初始化新metadata audit并收口registry。pending前后可重用同一plan恢复；Studio successor按固定key恢复，DB事务前中断回滚，提交后只核验与收口，不回滚新记录。重复apply验证当前完整前缀后返回NoOp。

## 混合读取与当前写权限

schema10新生native路径保持原合同。只有schema11准确回执中有限旧operation/fingerprint/claim/head/outcome集合能读取成kind=text；不改原SubjectCommand、不补旧situation。当前Admission仍只接NativeInteractionInput，旧nonce不能用于新点击。新旧完整前缀统一校验，最多两完整轮/4000字符进入已批exchange；history关闭仍核完整性。旧协议请求/草稿不能自动拼接新计时状态或重发，客户端协议升级与安装由产品另行安排。

## 验证与限制

合成transport经Facade与真实production composition验证旧文字→点击→文字→重开、同身份/Timeline/原store及UUID、原表旧行逐值不变、历史关闭、nonce重用拒绝、源推进/活写者/错同意拒绝、旧未知投递保留、旧发表损坏即使history关闭也fail closed。五阶段异常恢复及数据库提交前/后os._exit硬终止恢复均验证，无模型补发或新canonical覆盖。精确结果由本轮日志与产品记录承接。

只适用准确Memorie intent-3且所有旧操作已完成的冷根；有旧失败/未知操作时需另补保留终态的合同，当前拒绝而不删旧失败。没有实际用户升级回执、实机UI或隔日验证。运行中的旧服务/游戏保持，资料/路径/批准计划/DB/测试输出仅本机忽略目录；不新增Provider字段、凭据、通知或自动生活。
