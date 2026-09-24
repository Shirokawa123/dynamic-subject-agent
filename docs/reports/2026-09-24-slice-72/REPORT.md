# Slice-72：明确起点与相识依据

基线e9b2ebc。本片使离线上下文能说明“过去/当时相对哪个阶段”，并提供具体相识动机、时间安放与同源公开开场。没有调用模型或改变实际聊天。

## 改动

证据草稿可新增独立审核的chat_stage_description（最多500字符），由原草稿digest与来源核验一同约束。该字段不是作者anchor.description的自动复制；缺失时作者模型仍可读，但聊天预览明确unavailable/chat-stage-not-reviewed，避免携带无定义before/at继续装配。格式非法则failed-closed；内容语义仍需审核，哈希不能代替语义判断。

v8资料明确知识截止于当天已预告绘画直播开始之前，已具职业与先前直播经验，当天这场及后续事件未发生；相对时间不以用户现实日期解释。未修改30项适用知识或12项排除判断。

相识分支提案：她想看看其他人的绘画/插画想法，有合适话题可聊几句；首次私信安放在明确起点的一段短暂交流空档。未补精确分钟数、注册时长、习惯或预先好感；不强制每轮重置此空档，也不宣称后续忙闲/时间机制完成。这是助手可审提案，非原作事实或用户逐字确认的新设定。

新增PublicOpening仅由Encounter字段组织渠道和兴趣推荐，单独标为proposed-branch。推荐卡解释双方初识、用户可私信、对方可选择回应；不从self_knowledge或当前消息取真名/家事/职业信息。内部人物知识和公开页面信息仍分开。

## 复用和验证

继续复用[S70成熟机制研究](../../research/2026-09-24-coherent-character-context.md)的核心背景/场景分区及既有Facade和核验链，无新增依赖。现有recent_dialogue实现已核对：它依赖旧Living Memory状态，不能直接拿来装新角色历史或伪造accepted；后续契约见[历史接续草案](../../plans/character-history-integration-contract.md)。本片没有历史写入。

66项相关测试通过（48.64秒），涵盖人物模型、Facade、local_product、旧聊天；新增验证显式阶段摘要、不复制作者锚点备注、缺失/超长/空白失败、公开开场只用情境字段。小范围diff由主助手本地复核，无声称独立助手复核。

真实v8经Facade核验仍有30项适用知识，并成功生成起点/相识/公开开场预览。所有产物在`.local_indexes/eromanga-sensei/s72/`，原文未外发。v8 SHA-256：82a9a9ed9ce26f2f6d0733598c6b8350b304cdba9fc76dbfa868b245bb77dcdd。最终实际CLI验证另见本地cli-preview.json。

## 剩余工作

provider_ready/can_chat仍false，history_status仍not-connected。下一步将这份具体背景/情境装成独立角色回复候选的最小请求及离线验证，再列新增外发摘要和真实验收范围。不能直接把整个作者View送出去，也不能沿用旧已消费试聊额度。持久接续还须完成新角色绑定与Publication路径，当前不声称F7已完成。
