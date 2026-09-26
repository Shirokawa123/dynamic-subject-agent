# Slice-102：含人格的完整只读定义与聊天用途准备

S101实测收口后，将原v9的30条认识/起点/组织与S98四条人格解释合入同一自持运行资产。没有调用Provider、保存正式草稿、封存/切换身份或读取真实历史；额度仍61/200、余139。

## 实际变化

现有Facade.preview_character_identity_preparation增加typed含人格请求，复用S98相同的sidecar读取/摘要/主体/起点/eligible依据校验。带人格时产生character-runtime-definition-2，解释与Knowledge事实分开，保留author-interpretation/belief支持标记；解释ID/claim_ids只留本地trace，原文证据/排除项不进运行资产。不带人格时保留v1算法和资产。

新版character-definition-approval-2将确认状态与被批准内容分离：source中的rights_confirmed不参与新内容basis，独立confirmation请求默认false。源用途、内容mapping、persona摘要和运行资产仍被绑定；人格或用途变更改变basis，勾选同意本身不改变目标。旧save/freeze请求仍None、execution_ready=false、original-only-freezer；没有将小说派生资料标成原创。

## 导出与校验

本地`.local_indexes/eromanga-sensei/s102/complete-character-review.md`将身份、起点、全部30条认识、四条人格解释、试验局限与拟数据用途放在一页可读文档中；不是只给用户拼JSON，也不称知识/人格已穷尽。

- 完整JSON：`full-definition-v2.json`，definition basis `8b492ec9f7a047a4b0f4ae3fdb4eaa4326348f1607d89bd0abe96ae56924769c`。
- 运行资产SHA：`eab3ee8b1f7c88756154010f0542fc2af918376fec88613d5e1a073bc5554c82`；30项eligible、4项人格，12项排除仍在诊断侧。
- `review-request.json`将定义与准确的拟聊天用途一同指认；scope digest `4a843dc82b8ebd82d3fd058c6b91811fdf2eecfcfb6064a52b1f556cde9b40ce`，整体basis `4fa287fc4f12b5c4fb2608d0e58fa914d486013b2eaccfb8daed3279f14f631e`。这是本地可审请求，不是权限已经执行/持久化的证明。
- `continuity-use-example.json`是两轮合成字段样例，明确非真实聊天/非模型结果；不用它冒充已有连续性。

8项完整包行为检查＋5项旧v1/人格兼容检查通过，共13个唯一用例。覆盖确认不改变v2目标、persona/用途变化改basis、缺失/摘要错/foreign refs/主体起点不符拒绝、旧v1保持、零Provider/身份写入。主窗口检查差异、真实导出与运行资产摘要，并实际重建v1核对：原6e68…46957及asset原字节保持。没有新上下文独立reviewer，不将定位/哈希测试当作语义保证。

## 实际停止点

人格用于规划/表达已经获准；本次待用户决定的是[本完整定义的私人建角与真实聊天本地保留/限定历史用途](../../plans/character-continuity-consent.md)。最多2完整已提交轮/4000字符、同Provider、可关闭；最小身份与仅有无既往交流的前景，原文只在canonical Timeline中保留，不另留整包prompt或自动复制开发报告。

准确派生来源的Authority、生产聊天提交/恢复和历史控制仍待实现与验证，当前不伪称可以直接调用旧封存或MVP已完成。确认后沿同一内容继续常规设计/实现，不逐片询问；新生活/后台通知不在本次授权范围。
