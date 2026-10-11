# S153开工证据：确定的修改不交给模型重复生成

用户结果/缺口/验收先定于[S153](../slices/slice-153-python-frame-continuity.md)。已有S152独立frame准确定位2处，但三字段首输出含冗余无变化编辑；原严格拒绝有效，不放宽或用旧原题抽到过。

定向核对一手来源：[Guidance官方README](https://github.com/guidance-ai/guidance/blob/main/README.md?plain=1)展示普通Python确定控制与select/gen混合，已知结构不需全部由模型生成；[Dafny官方modifies](https://dafny.org/latest/DafnyRef/DafnyRef.html)规定可写范围先由规格确定。前者借职责拆分、后者沿S152借frame机制；都不能证明通用自然语言意图或角色心理。Guidance官方旧notebook页面抓取失败（过大），改核官方README，不以非官方镜像代替。当前不依赖库行为/SDK更新、不引入Guidance/Dafny/解码hook或外部代码，故无新依赖/许可成本。

仓库复用：requested_frame唯一expectedplan、apply_edits/validate_proposal旧真实变化/唯一跨度/大小边界、scoped_feedback_record最终重算、同SCOPED能力Manifest/schema8、原canonical/权限/来源闭包/恢复和同DeepSeek投影。只新增独立技术intent-only contract/Grant/audit，raw两字段转内部六字段。每个实际含目标字段一项确定编辑，未含目标字段零项，原byte范围外保护保持。

未采用：删除旧无变化edit后重新判首验通过（放宽旧验收/改原证据）；加提示继续重抽同题（缺乏结束条件）；全新plan本体或二模型judge（本次不必要且后者新增用途）；让模型输出字段选择再授范围（同旧问题）。新构造算法仍需满足既有160/240边界，不能表示则无effect，范围限制明示。哲学/心理学在此纯工程构造不提供额外解释力；人物关注和后续选择沿既有来源，效果由新首次内容观察而非理论推断。
