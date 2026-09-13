# Slice-35：刚交付作品的连续修改

状态：实施验收中。基线9626670 / dogfood-s34。

## 根因与有限修复

Slice-34真实head75交付两句作品，但同轮目标能力FailedClosed；76修改第二句时LM reply recent_dialogue为空。仅“目标查询→作品→改句”的Interface最小例原本通过；加入真实差异（作品轮目标分类失败）后1 failed / 1 passed in 3.02s，复现相同“没有可安全用于修改的对应句子”。

根因是TimelineOutcome.memory_revision对没有Memory片段、只有已知目标局部失败的完整结果返回unknown。历史筛选因此拒绝整轮，尽管作品已原子发布、Memory没有写入且目标失败不依赖Memory。

修复不改变目标结果或历史原文，只认可五种既有闭集失败码与exact `{status:failed-closed,action:noop,reason_code:同顶层code}`，且rule_version=experience-1.0、顶层无Memory/其他未知片段时，能够证明没有Memory revision。闭集由目标Domain与解释器共享，避免重复规则漂移。字段缺失/额外、类型未知、原因不匹配、非noop、Memory null均不作为证明。

仍经同一identity完整Timeline完整性、冻结basis、权限、pending、记忆控制与预算校验；仅LM reply按既有最多两完整轮/4000字符授权接收文本。目标消息本身仍被control规则截断，编号修改只取最近安全轮，不能回找旧作品；不新增存储/字段/Provider用途/调用，也不改UI。

## 验证

五类目标局部失败与无失败对照均连续修改两次，6 passed in 10.34s；早期原复现与既有历史相关33 passed in 35.11s。结构反例、全量与真实重启结果待回填。

## 真实进一步发现

3221857真实head83作品已可进入84的reply上下文，但模型只返回改过的第二句；产品把这一句当作整份作品，85遂只能在半份作品上修改。该阶段不计为完整连续修改成功。新增Interface反例先1 failed in 1.42s。

有限修复：编号修改定位同一已授权稿件或当前完整重贴原文；模型返回一条句子则作为指定位置的替换，返回同句数完整稿则只取指定位置，其余原句保留。不对应的句数或指定句完全未变则报生成失败。重组全文再次经过原contextual检查，不能用局部文本绕过整体限制；不引入新稿件来源/历史范围，不恢复来源尾注或回执为诗句。
