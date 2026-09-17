# Slice-41：共同写作连续修改闭环

状态：完成。基线d9a4452 / dogfood-s40，代码/测试提交cf4b0e6，实现dogfood-s41。

## 诊断与复用

独立混合验收19/20原文及第2轮首稿在ApplicationFacade先复现 **3 failed in 3.01s**（包含重启对照）。外部模型测试桩已返回合法creative；本地不识别“第一句再改成”和“那就请写两句”，因此未进入既有创作/编号修改路径。原始真实失败没有保留模型输出，本次确定性复现证明本地识别缺口，不反推原Provider输出。修后原对照与既有自然写作/连续稿件 **35 passed in 23.38s**。

2026-09-17按context7-mcp尝试resolve Aider，返回fetch failed；回退核对 [Aider官方Edit formats](https://aider.chat/docs/more/edit-formats.html)：whole返回完整版本，diff以search/replace绑定修改对象和替换内容。借鉴“明确目标、局部替换、保留未改内容”的机制；本仓库Slice-35已有编号目标和单句/完整稿重组，因此只补当前语言识别，直接复用现有实现。未复制代码、引入依赖或采用Aider的文件状态体系；无需增加第二canonical store或模型阶段。

## 实现与复核

natural_writing在直接写作动词前规范化“那就”衔接语，在既有编号动作前接受“再”；题材、意象不设关键词名单。沿用引用/条件/转述/撤回检查、单一编号目标、当前原稿优先、最新安全历史及只替换指定句机制。“那就请写两句”也进入已有两句数量检查和LM reply当轮格式指示；没有改Provider system模板、字段、预算或用途，其他11类请求不变。

新增17项ApplicationFacade用例；原两轮、重启、不同编号表达、条件/转述/撤回/多目标、历史控制与首稿句数拒绝。相关 **101 passed in 74.95s**。没有借“再”恢复被控制的历史；“别再提”仍需当前重贴。

按code-review技能本地复核d9a4452工作区含新增测试：检查当前语言解析调用方、LM许可/正文定位/重组、两句动态提示和最终失败路径。小型差异本地审查，未调用独立子代理。无已确认新增缺陷；有限句式并非通用自然语言理解。

## 真实验收

自动审核最初拒绝启动，理由是缺少具体payload/凭据用途/目的地的明确授权。用户随后明确批准api.deepseek.com、既有Windows Credential Manager DeepSeek slot、脚本10条合成文本及原六类最小投影，才开始真实调用。没有读取正式身份或显示/保存key。

全新隔离根C:/Users/30252/AppData/Local/Temp/dsa-s41-isolated-20260917，默认合成Avery；production DesktopState/HTTP/ApplicationFacade。临时只读observer记录合成LM公共DTO、回复和HTTP状态，不记录鉴权、其他Domain内容或raw reasoning，不改变请求/返回。

| Head | 结果 |
| --- | --- |
| 1–2 | 原19/20原样：第二句改为邀请后，下一轮第一句改为风吹纸边，第二句逐字保留。 |
| 3–4 | 原第2轮“那就请写两句”交付两句；继续修改第二句，第一句保持。 |
| 5–6 | 新陶艺桌题材首稿、第二句轻声邀请修改完成，第一句保持。 |
| 7 | 重启后修改第一句，第二句保持。 |
| 8 | “别再提”仍阻断历史并请求重贴；不把安全拒绝计作编辑成功。 |
| 9–10 | 当前完整重贴后改第二句；下一轮改第一句，另一句保持。 |

共10轮，9轮交付一份两句稿，1轮按既有历史控制要求重贴；全部Memory no-op，未把作品保存为用户事实。62次Provider HTTP200，没有transport failure。只读DTO确认编号编辑仅一轮历史，控制轮与当前重贴轮无历史。见 [逐轮原文](TRANSCRIPT.md) 和 [结果检查](raw/checks.json)。第一次重启及最终移除observer后的再次重开，display_name/build_id/memories/participant_goals/conversation_history_status/conversation_history六项均一致，见raw两份comparison。所有服务已CLOSED，隔离数据保留。

原始响应保留在raw，不把数量/结构通过当文学质量保证。第7轮“指尖沾着泥土的感觉慢慢有了形状”措辞仍显生硬；本轮不宣称文风已经自然。

## 剩余范围

仍限现有有界句式、单稿、前三句编号及最新安全轮。自由“第一句我想更轻一点”未列为新增支持；换话题后回找稿件、自由偏好澄清和记忆框架迁移不在本切片。没有新权限或持久稿件状态。

## 最终回归

代码/测试cf4b0e6：**795 passed in 665.24s**。命令 `.venv/bin/python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s41-full-20260917`。包含既有Provider最小投影/字节、原子Publication、恢复及其他能力回归。其后仅文档和合成验收记录变化；`git diff --check`通过。
