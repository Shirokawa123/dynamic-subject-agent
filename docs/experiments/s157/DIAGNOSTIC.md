# S157固定六格choice诊断（结果前冻结）

两组全新材料，same group内相同背景/E1/current_activity/current_plan/F1/policy/JSON，唯一变量是choice thinking/effort。high=既有S154；low=enabled/low；final=disabled/无effort。max_tokens=4096、模型/HTTPS/30秒/slot/单请求保持，反馈仍原S154 direct/intent-only/multi-span。先生成准确wire并核messages逐字相同，未知变体拒绝。

A：未开始的新原创旧地图店“云匣”。E1整条原话：“做一间原创旧地图店‘云匣’的未成图文字构图。你自行选择人物、物件、镜头、光线；分工作台、店内、门外三段，各有具体安排和你自己的关注。”无旧plan/F1，phase=unstarted。目标是一次start、完整具体构图与自身取舍、准确使用新地点/地图店语境，不编成已成图或实际旧经历。

B：新原创山地茶棚“弦屋”的明确标注本地合成方案，经本地Fake按完整原话“这版把所有‘弦屋’换成‘弦湾’，其他照旧。”自动形成F1/v2。E1：“做原创山地茶棚‘弦屋’的未成图文字构图。自己选择主体和摆放，关注短暂停留与物件使用痕迹。”seed subject=“原创少女在弦屋桌边整理旧地图”；composition=“平视中景，左侧小窗的暖灰反照光。弦屋的矮桌上摊开折过边的旧地图，少女正压住纸角，右侧木箱留出通往远处的视线。弦屋窗外细雨停了，地面有一条浅亮反光。”；focus=“弦屋里人的短暂停留与物件痕迹”。choice实际收到上述三个字段只替换新名后的plan/F1，phase=rework。目标是一次revise新方案/真实内容差异，保弦湾、不恢复弦屋，有具体自身关注/空间或物件取舍及准确来源；明确本次新活动可改变画面，先前文字更正的其他照旧已严格完成，不解释成永久禁止后续自主选择。

准备通过Facade提交合成来源、选E1及本地Fake plan/更正，标记“本机诊断种子回应，不是人物模型输出”，0真实请求/凭据。其种子Publication不能当人物能力；owner关闭后冻结两个source整树与canonical/权限/WAL，由Facade预览六格提议，诊断前后完全相同。所有远程提议不发表、不成为新当前状态或后续场景输入。

固定顺序：A-high、A-low、A-final、B-final、B-low、B-high。每格一次、独立attempt/audit/首次final，0retry；length/空/格式/不满足目标仅记该格终态并继续其他独立格，权限/材料完整性/来源变化/credential unavailable/投递未知则停止全组。保所有结果，不补抽。六格结束即诊断收口，不扩格强复现。

技术通过：exact wire、HTTP解码完整stop、非空final、合法闭集action/plan/reason/basis/decision_note、各字段上限与原Python裁决通过。语义每格0未达/越界，1部分或含糊，2目标准确：A具体有效初稿及自身取舍；B实际新选择/新名保留/不伪造已成图或离线经历。合法defer/keep/rework如实保留，但本目标语义未达，不能靠全拒绝过门槛。不能只以字段/耗用/HTTP200判好。

候选low/final各自A、B均技术过/语义2才eligible；high仅参考，不替代候选不足。两候选都过时选两格completion_tokens合计较低者，缺用量不伪0、有齐全用量优先，仍同分/均缺优先low；质量门槛先于耗用。只2个材料不证明稳定或模式普遍更优。eligibility一次不可覆盖，绑定六格manifest/metadata/全部first final SHA、人工评语、唯一selected_variant；均不过不启场景。
