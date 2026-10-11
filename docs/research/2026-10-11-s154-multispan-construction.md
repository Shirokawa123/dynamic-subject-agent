# S154开工证据：短跨度、唯一上下文、完整覆盖

用户结果/已证缺口/标准先定[S154](../slices/slice-154-multispan-continuity.md)。S153先末跨度165只因单段算法受160限制，不是原多项协议没有表达能力。沿[前研究](2026-10-11-s153-local-edit-construction.md)确定内容归Python/模型仅意图；本次仅局部工程。

定向核一手[Google Diff Match Patch Python源码](https://github.com/google/diff-match-patch/blob/master/python3/diff_match_patch.py)：patch_addContext扩上下文以定位唯一，patch_splitMax把超匹配长度补丁拆小；[官方仓库](https://github.com/google/diff-match-patch)归档且Apache-2.0。借拆小/唯一上下文机制，不安装或复制代码。其模糊best-effort匹配、重叠上下文和顺序应用不适合本仓基线坐标/不重叠/逐字保护，因此自建有界目标组窗口枚举＋路径选择，不引入diff/patch新依赖。纯工程构造无心理学新增解释力；角色关注仍由来源与真实首结果验证。

仓库复用requested_frame≤8目标、validate_proposal/apply_edits旧≤4/160/240/唯一/不重叠/变化与exact expectedplan、SCOPED最终重算/来源过滤/同canonical恢复。为每个连续目标组枚举满足旧界限的唯一窗口，保留起点更晚/终点更早的非支配窗口，再以基线坐标选择最少段完整覆盖；各字段独立，合计超4仍拒。新增精确技术资格但保持原raw/policy/出站数据/HTTPS slot，零额外judge/模型请求。

未采用：提升160/240或4项（放宽）；只取前4目标（漏改）；模型挑before（倒授范围）；替换整field（仍超限）；直接上通用diff模糊匹配（误位置/侵入授权外/归档依赖成本）；改冻结S153构造后补发至过。旧首失败本机保存原decoder继续拒，离线新构造效果不重判真实失败。验效先Facade多段/冲突/界限与最终保护，再只跑新冻结首景。
