# S158：当前活动实际变化进入接话与分享的准确审阅

状态：待批准，只有本地只读功能和未发送候选。原三用途批准不自动包含旧稿片段；本次申请在同一已审人物包、同一DeepSeek default Windows slot下，为 **普通接话/自然反馈** 和 **分享表达** 增加 `current_result_change`。不增加choice数据或动作，不发送模型推理。

## 为什么需要

海港真实v3已修改左右手和重心，但末答只看到当前plan，没能具体回顾后来的变化。新视图把当前可见修订的实际证据交给表达，避免要求模型猜旧版。它不是完整历史或时间记忆，也不证明模型会忠实使用；批准后仍须独立新场景验证。

## 准确新增字段

`current_result_change` 为 `null` 或 exact `{action, changes, unexpanded_fields}`：

- action固定`revise`，只表示当前可见已提交结果。
- changes每项exact `{field,before,after}`；field只subject/composition/focus，连同未展开字段总计最多3个且不重复。before≤160、after≤240字符，允许真正插入/删除的一侧为空。
- 每字段去掉最长相同前缀/后缀，剩余完整连续片段覆盖全部变化。不裁剪、不抽取“最好”的变化；超界时整个字段只列入unexpanded_fields，不发该字段旧文字。
- null代表当前没有可安全提供的变化依据，不能被说成“从未变过”。不发ID、时间、head、原文来源引文、decision_note、整份旧plan、完整历史或数据库行。

权限由同一Timeline的verified Publication重建：旧plan依赖证明与当前result依赖都仍有效才输出。历史关闭、上下文边界、来源撤回或证明缺失时抑制；新独立方案可见不意味着可发送其差异中残留的旧before。批准后发送前仍需按当前head/权限重建并绑定一次票据，不能直接发送历史样例。

## 可核对的实际未发送样例

来自已终态海港的相同v3，保留原两份历史合法checkpoint：

- [末次接话候选](../../../.artifacts/s158/change-review-first/faithful-reply.json)
- [第二分享候选](../../../.artifacts/s158/change-review-first/second-share.json)

新增composition片段为：修改前“，右手扶栏，左手垂在身侧，动作保持安静”；修改后“。人物左手抬起轻搭在栏杆上，右手垂在身侧，身体重心略移向左脚，呈现刚停步的姿态”。focus是从空串插入“人物刚停步的手部动作强化驻足感，”。其余原payload逐值不变，策略只说明新字段的事实范围与未知边界。

这是从保存的终态证据派生的历史样例，不是当前share资格，不重发原场景。最终准备只读原工件，77文件hash全同，零产品打开/请求/凭据。真正的本地Facade已用6个行为场景验证权限、查询不发表、重开和旧来源反例；另29纯函数和2未发送wire检查通过，双复核接纳。

## 保持与批准后动作

沿现有review basis `35da99cca813588f534a83be0a2fdeab5730f2e2793ba03726fd5f06d50d3d95`的原资料、Provider、凭据用途和所有既有投影界限。Endpoint仍`https://api.deepseek.com/chat/completions`，model `deepseek-flash`，4096，单动作一次、0自动重试；原≤8目标/≤4编辑/160/240/唯一/不重叠/完整“其他照旧”不变。新增字段为证据，不能成为编辑命令或直接持久状态。

若批准，在S158内接独立候选的claim/consume/Publication一致性与入口装配，先本地验证并提交推送，再冻结一个未见普通完整场景，验证实际变化→分享→换题/重开→忠实接话。保留所有旧首稿、失败与评分，不重跑旧场景；不继续用随机新稿补抽长距门槛。

本审阅不申请8797常驻、实际隔日后台动作、通知、云、新材料/Provider/credential、迁移删除或人格重写/Reflection。服务启动须最终候选的具体运行对象准备好后按原边界处理。

冻结摘要和精确review basis见[change-review.json](change-review.json)；原审阅文件及批准记录保持。
