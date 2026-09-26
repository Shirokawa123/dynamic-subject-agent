# S102：知识、人格与批准状态的完整绑定

用户结果：正式建角前看到一份包括知识、起点、四条已试验人格解释的精确定义，确认不会漏掉人格或意外批准另一个版本。S101已经提供有局限的真实行为证据，现停止叠单轮测试，准备连续聊天所需定义。

## 现有能力与缺口

已读CharacterIdentityPreparation的SourceDeclaration、runtime_asset_json和_definition_basis，以及S98人格sidecar读取/本地验证。S97只将v9认识和组织写入运行资产，没包含人格；旧definition basis因此不能批准新角色。另一处预先发现：v1 basis连rights_confirmed=false一起散列，后续若直接把声明改true再算会改变目标。批准状态应独立于被批准的内容，不能让同意动作本身变成内容变化。

正式PolicyKernel和Studio仍只支持原创。本片不修改它们，不调用旧save/freeze、不创建身份；准确派生来源的实际执行路径仍是后续受限实现。先做到可审材料完整，不能把旧封存执行能力与本片预览混称。

## 来源与设计决定

复用S97对[W3C PROV-DM](https://www.w3.org/TR/prov-dm/)派生与引用的核查，本次定向查看[Entity](https://www.w3.org/TR/prov-dm/#term-entity)与[Activity](https://www.w3.org/TR/prov-dm/#term-Activity)区分：被描述对象与作用于对象的活动不同。工程适配是把固定人物内容/来源/用途，与用户确认这一动作分开；这不是W3C要求的某种散列算法，也不引入RDF。

人格内容仍使用S98/S101来源/效果结论，不加心理理论、人格条目或Provider用途。本文处理只读组合与完整性，新的心理机制研究不适用。既有四条仍是author-interpretation，不改成原作fact，不用本次模型台词增补新性格。

选择复用同一Facade身份准备Interface与同一人格读取校验：请求可显式附本地sidecar及预期digest，先验证同一v9/主体/起点/eligible refs，再将经过剥离作者ID的解释和来源指纹放入自持运行资产。原始引文、待核两项、真实对话都不加入运行资产。

新版definition-approval-2绑定内容mapping、不可变来源/用途、persona digest、runtime asset digest；rights_confirmed/confirmed是另一个确认请求的布尔值，不是人物内容。改变人格、知识、主体/起点、用途必须改basis，单纯确认不得改被批准内容的basis。未带人格时保留S97 v1预览，以免暗改已保存预览；新版才能表达本次完整定义，不声称旧版本可执行正式小说建角。

未采用：把人格写成Knowledge事实、靠旧basis另挂未绑定的sidecar、批准后偷偷改写定义、把小说摘要标原创绕过PolicyKernel。无需新存储或外部依赖，许可证/维护成本无新增项。

验证：两来源/选择匹配、persona变化会改basis、确认状态与内容身份分离、独立自持资产涵盖完整四项但无排除/引文、缺失/损坏明确失败、原v1预览稳定；同时prepare始终零Provider/零身份写入。真正的SourceAuthority冻结执行、生产接续/历史控制需后续实现和具体数据用途确认，不在这里伪造ready。
