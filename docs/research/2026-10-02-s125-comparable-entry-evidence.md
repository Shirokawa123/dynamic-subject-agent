# S125开工证据：比较入口与记录隔离

用户结果/缺口/验收见[S125](../slices/slice-125-comparable-chat-entry.md)。多个逐片端口不便比较，而S124有明确反例，故保留原版默认、提供候选，不能自动替换旧记录。

复用仓库TrialEntry、WholeReplyChatAdapter和既有页面：启动/重开不生成，Host活跃lease保护单runtime，HTTP只映射Facade；四个UI case分别指向两个variant各自两场景的独立canonical root。[MDN sessionStorage官方说明](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage)经本轮核对：存储按origin/页签区分，刷新仍保留、关闭页签清除。复用原`scope_key+case_id`草稿键与opaque nonce，不把它当第二聊天历史；独立新manifest组合scope及带variant的case_id防草稿串位。

只改入口组装和说明文字，保留页面JS逐字和原CSS，不引入UI库/依赖/来源迁移。哲学心理资料对纯呈现/资源隔离不适用；候选效果沿S124真实证据，不在入口证明人格或新权限。许可/维护成本只涉及自有代码和标准库。

后台Interface验证选择/模型wire/各自历史、重开和设置零调用及旧服务不读。隐藏页面检查四按钮、草稿切换/刷新/取消恢复保留；不抢焦点或操作用户旧草稿。真实新入口仅开发合成消息。禁止合并模型上下文、复制旧私聊、停止旧进程或创建云端；局部候选不冒称全面winner。
