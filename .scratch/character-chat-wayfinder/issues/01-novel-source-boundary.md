# 小说提取如何保留来源与起点边界

Type: research
Labels: wayfinder:research
Status: resolved
Assignee: source_research
Parent: ../map.md
Blocked by: none

## Question

为小说人物选择起始阶段时，哪些成熟的EPUB读取/定位机制值得复用？比较少量官方方案，明确可获得的阅读顺序、来源位置及它们无法自动解决的人物知情/剧情时间问题。产出首份原型可用的最小建议、许可证/维护证据与限制，不引入依赖，不读取小说原文或调用角色模型。

## Comments

2026-09-20：由已确认的小说优先、时间起点和来源可展开需求派生。公开技术资料研究不代表实际素材已就绪。

## Answer

2026-09-20，source_research只读核对完成。[研究结论与官方来源](../../../docs/research/2026-09-20-novel-source-boundary.md)：spine/CFI可复用为阅读顺序和位置证据，不能当作剧情时间或人物知情证据；EbookLib/epub.js仅保留候选，不引入依赖。真实小说材料和版本尚未核实，交由素材准备票。研究成果保留在`codex/research/character-chat-sources-20260920`分支；用户体验要求仍以方向记录为准。
