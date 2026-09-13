# Slice-40：混合自然目标

状态：实施验收中。基线6f9ea62 / dogfood-s39。

## 诊断与复用

独立混合验收13/14/21/22轮为原始样本。原文创建与带“诊断对照”前缀均路由None、Memory证据全句eligible；去除前缀补回“我”即命中确定性create、Memory participant-only。两组ApplicationFacade原始对照先 **2 failed in 1.58s**（故意模拟分类失败），证明本地识别缺口与Memory范围未排除并存，不证明能力在争夺同一写锁，也不能从黑盒反推原Provider具体错误。

按context7-mcp技能尝试resolve Rasa时fetch failed，回退2026-09-13核实的 [Rasa Command Generator官方文档](https://rasa.com/docs/pro/customize/command-generator/)。复用动作与参数绑定、区分无法生成命令与执行结果的思路；仓库已有typed candidate和Domain，无需引入其流程栈、额外上下文或依赖。新解析保留当前原文跨度，一份结果供目标路由、最终裁决和Memory分工使用，不复制Rasa实现。

## 有限实现

当前明确“换个话题：”“说正事：”“（诊断对照）”前缀保留原文；逗号连接的自述安排后“也给自己定个/一个目标”仅从当前第一人称安排继承主语，条件或不明结构不执行。支持完整“把目标〔引号旧条款〕改成/改为/换成〔引号新条款〕”；省略目标二字时仅在旧条款逐字命中当前active目标才进入该能力。新旧引号必须配对，旧条款完整库存唯一，不以引号内容生成指令；尾部只允许裸安排/计划不变、椅子/工具/材料/点心照带，其他尾句拒绝。

目标创建/修订继续原append-only裁决，Memory扣除已识别目标操作，保留独立连续原文；拒绝的明确目标修改不能覆盖安排。原主体、引用、条件、撤回、同轮多命令、完整库存及Provider原投影/提示/调用边界保持。没有历史新授权、pending状态或新store。

## 验证进度

初始原样及Slice39相关19 passed in 16.68s；扩大Interface/旧分工/最终回执 **73 passed in 60.35s**，目标Domain/Provider/时间 **31 passed in 7.82s**。包含恶意Provider截取条件/转述/引号修改的反例，不以Provider失败代替裁决验证。最终全量、复核和真实后台待回填。
