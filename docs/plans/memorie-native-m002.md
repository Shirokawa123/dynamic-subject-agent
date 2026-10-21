# M002：同一人物的typed原生互动底座

游戏产品唯一执行结果在`E:/memorie-companion/docs/slices/current.md`；本仓只提供共用底座，不并行运行另一个游戏切片。用户对准确review basis `081866a662cd62d469c2ea40ac195e8e2bd2191e9faad75a6df0963c169792a4`答“同意”，批准显式点击/文字、最小计时阶段及最多两轮typed已提交交流。批准不含安装、迁移或旧Timeline升级；冻结review与单独回执由产品本机保留。

## 用户结果与实现依据

点击生成后，文字接话看到同一条Timeline中已提交的真实点击和最终回复，不能把点击伪造成用户说过的话。复用现有ApplicationFacade、LocalIdentityAuthority、reviewed-chat独立QRI、Memorie单次Gateway/Windows slot/audit、Timeline原子发表和原请求只读查询。定向核现有SharedActivity/FirstLife typed system input、全前缀验证与冷恢复，采用相同单写者机制；没有另建Domain/store、活动或心理状态机制。新SQL仅沿既有基本DDL/事务/外键，无新依赖或库API假设；界面合同与官方Harmony/Yarn依据由产品M002承接。

## 实际合同

`memorie_native.NativeInteractionInput`独立输入版本和fingerprint，明确`interaction_json`/`situation_json`；点击没有text，兼容属性utterance在点击时为空，不能成为SubjectCommand。schema10只新增`memorie_native_input`，输入与Admission同事务；输入、完整Outcome和最终表达沿同一Publication链核验。没有客户端历史/第二canonical或JSON伪原话。

新资格`memorie-native-interaction-m002-1`独立scope/review/policy hash；沿reviewed-chat来源家族封存，与旧S160版本分派。Host只据准确QRI设置native能力/intent/runtime contract；仅空白未封SubjectEvent的资格后继可创建schema10。`open_memorie_native_product`要求独立准确回执和已冻结同definition的身份；旧chat_activation即使为空也拒绝自动变更，非空旧数据/当前游戏入口更不迁移。

Facade使用`submit(NativeInteractionInput, idempotency_key)`、`lookup_subject_request`及`query_memorie_interactions()`；静态`preview_memorie_native_message`仅用于无sender的审阅。生成器只从已验证同身份完整前缀选择≤2完整轮/4000字符，关闭历史仍核前缀；点击在模型和历史中均为typed事件。旧CONVERSATION_HISTORY不将点击投影成speech，native调用者必须使用新查询。

出站只有character/personality/exchange/interaction/situation，精确人物与策略hash绑定原样例；计时仅idle/work/rest/paused或未知null，点击未知则拒绝。无scope/源ID/观察时间/时长/草稿/笔记/存档/动画名。DeepSeek现有slot、4096/thinking disabled/30秒/0retry；点击≤120字符，文字≤1200。Provider与Session均核正文，最终Publication再次核上限和当前history/identity版本。普通typed NoOp不写知识、人格、关系、活动事实。

审计独立purpose/授权摘要、先claim后投递、metadata-only；旧审计不能冒充新账本。重复UUID/不同payload冲突，未知/故障不重新投递；冷恢复沿既有未发表whole尝试关闭为失败，不补模型。原子发表中断不产生部分聊天，旧/新失败均保留。

## 验证

初组新9+旧36共45 passed，最终10新Facade/production检查passed，另Host binding/recovery及FirstLife原子发表43 passed。覆盖click→text→重开/查询、源样例4份逐字节一致、关闭历史、UUID变化拒绝、旧资格/旧root不升级、凭据不可用/超时/截断/过长、授权撤回与冷恢复无重发、canonical输入篡改拒开。均为独立临时数据与合成transport，0真实Provider/当前用户canonical。日志在本机`.artifacts/m002-native/`，首次native激活继承旧intent而拒绝的失败保留，已按准确新QRI修复空白后继权限。

本合同不证明原版点击命中、IL2CPP patch、原生视觉、人物自然度或隔日体验通过；实机由游戏产品沿用户“稍后更新”决定承接。此实现不开放自动活动、通知或旧资料迁移。
