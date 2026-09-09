# Slice-32：记忆写入确认与最终结果一致

状态：已收口（有限范围，真实剩余失败保留）。基线f0b2bf1 / dogfood-s31，实现dogfood-s32。

## 实现与证据

ApplicationFacade先复现4个失败，4 failed in 3.64s；存储回执读取最终Experience Outcome，原文中的条件、否定和时间不由模型再次改写。详见 [DESIGN.md](DESIGN.md)。回执在express阶段生成，与Outcome一起原子Publication后才向用户显示，不新增写入者或存储。

纯记录消息不使用自由确认。已检查的当前创作或明确独立问题可保留；无效refinement不能退回错误base确认。Knowledge命中时仍遵守原有完整来源边界，不让Memory自由事实回答混入。Goal最终确认仍依据其所属Outcome，不能吞掉独立Memory创作或问题；关系控制与提醒边界保留。

创作置于首段，记录/目标确认置于独立后段，沿用既有首段稿件定位。重复改写只比较历史作品首段，不把新增回执尾段算作作品变化；当前生成正文仍按原完整正文检查，不靠截段满足限字。

## 阶段测试

- 新失败转绿4 passed in 3.16s。
- 记录/组合/提醒37项中36通过，唯一失败是旧生日测试依赖模型确认台词；已改为实际保存原文的确定性回执断言，仍核对accepted状态。
- 组合对照修复两处实际问题：独立问题的无效refinement不能回到误解条件的base；Knowledge命中时不能让记录回执标记豁免Memory自由事实回答。Goal测试桩曾因原有identity guard拒绝提前成功台词而失败，改用符合原契约的中性reply，未改变Goal生产语义。
- 存储回执/来源/字节基线53 passed in 24.61s；只有LM reply提示哈希改变，其他11项相同。
- 创作续编/重复检查与既有对话、自然创作回归78 passed in 55.01s。

## 边界

回执保证实际保存结果，不保证提取候选已覆盖用户所有原意。独立问题采用有限直接问句识别；间接邀请、任意多意图及自由讨论的语义质量不宣称全部解决。历史主回复保留原文，旧错误不会被本次回执规则重写。

## 真实后台验收

复用已授权的合成Avery根 `C:/Users/30252/AppData/Local/Temp/dsa-s31-live-20260909`，核实既有登记与路径后使用原DeepSeek slot；未操作正式身份、凭据或缺失登记的旧林柚根。HTTP走现有Desktop/ApplicationFacade，Memory观察包装只记录公开DTO并原样调用真实Provider。原始响应及合成文本投影见 [raw](raw)。

| Head | 输入与结果 |
| --- | --- |
| 26–27 | 新增砚河手册安排，再更正为周一；两个回执均完整保留未收到校样就顺延的条件，与实际canonical内容一致。 |
| 28 | 记住浅金色封面偏好并询问风格；记录回执与独立建议均保留。 |
| 29 | 记录祝福偏好并写一句月光诗；作品在首段，记录回执单独后置。 |
| 30 | 记录有条件的星溪安排并问纸张；保留完整记录、《创刊号规格》原文和来源限制。 |
| 31 | 记录安排、提出读书目标并写树影诗；诗和Memory回执保留，目标实际NoOp，明确未新增目标。Memory保存内容包含用户的目标句，不能把此轮算作目标创建成功。 |
| 32 | 重启后查询砚河手册；引用更正后的周一安排及完整顺延条件。 |
| 33–34 | **真实失败保留**：记录苔桥安排并要求写两句诗，模型已返回creative文本，但既有explicit_creation_request不识别“写两句”，最终只显示真实Memory回执，未显示作品或创作失败说明。后续改第二句因无已提交作品而拒绝；不能算作创作/续编验收通过。 |
| 35 | 普通闲聊正常回复，没有伪造写入确认。 |

共10次追加；26–31在b55ceb9阶段，32–35在0fbb736阶段，不合并为单版本全成功率。重启前后display_name/build_id/memories/conversation_history_status/conversation_history五项完全相同，见 [比较](raw/restart-comparison.json)。服务均已CLOSED，数据保留。两句诗的有限句式缺口记为后续体验工作，不扩展本次已核准语法范围；本切片不宣称所有独立意图稳定保留。

## 独立审查

Standards初审及至0fbb736增量无新增规则问题。Spec初审发现Goal最终表达会丢弃独立Knowledge创作的P1，8f3cfdd以只在最终Knowledge accepted时恢复的临时字段修复，并补目标accepted/failed两例；增量确认P1关闭、无新增Spec问题。审查未替代真实验收，两句诗失败仍公开保留。

专项最终24 passed in 14.48s；相关既有确认/身份投影/历史交接/记忆58 passed in 67.05s。初次全量601 passed / 6 failed，失败为旧确认措辞依赖和过窄的否定词断言；更新为canonical回执及准确目标失败表达，状态/内容/隐私断言保留。最终全量 **609 passed in 629.97s**，命令 `.venv/bin/python.exe -m pytest -q --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s32-final-validated`，测试代码基线0fbb736。其后仅文档与脱敏合成验收记录变更。
