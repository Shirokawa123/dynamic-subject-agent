# S107：只读方案引用被误判为历史控制

用户结果：分享后可正常追问“保存的方案已有这个决定吗”，真实保存/撤回/删除请求仍不外发受限制历史。root的首次合成追问在Provider前失败，0新增调用；普通不含该名词的分享后追问在history开/关的Facade对照均通过，不能再归因为分享授权破坏了历史链。

已证实缺口：recent_dialogue.is_dialogue_control将任意“保存”命中为控制；character_dialogue_before返回restricted；v3规划只接available；上层broad catch统一报history-unverified。原检查服务于六能力的保守历史边界，不是完整中文意图识别。实际完整输入是询问既有方案/当前构思，不是写入记忆或要求保存。

可观察验收：同一Facade流程intro→advance→share→pause/share-off→重开→完整原问句，在history=True时此前红测，修后能正常进行；下一轮窗口与已终结未发布意图也不因同一只读引用持续屏蔽。真正“不要用保存的方案”“请保存…”“删除…”及混合请求保持restricted，history=False/未知pending/完整性失败、原六能力默认行为不改变。

资料与取舍：复核本仓库recent_dialogue、character_dialogue_before、_verified_dialogue_prefix、select_recent_dialogue及既有ARCHITECTURE的引用/控制边界。定向搜索[OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)的结构分隔/匹配限制，借其“不能让宽泛匹配替代内容用途区分”的工程原则，不把本正常问句称为攻击。本修复为本地控制语法，不引入人物心理假设、意图模型或新依赖，心理学不直接适用。

实施：给已有选择函数增加可选predicate，默认保持原行为；仅first-life字符历史使用有界只读名词引用识别，当前话/最近窗口/已终结未发布意图使用同一判断。完整问句中的“保存的方案/构图/版本”可以是只读对象，真实控制优先。未解决pending、数据完整性与撤回规则不借此放松；不删旧失败、不改policy字符串或冻结scope。不是通用中文意图识别，模糊表达仍可能保守受限。

不采用：从全局控制词表删除“保存”；遇history失败就伪造空历史继续；换问法重跑模型掩盖错误；重写已记录的失败或分享。先用零远程替身锁定原句反例，再在修复后做一次新的验证，不重发分享。
