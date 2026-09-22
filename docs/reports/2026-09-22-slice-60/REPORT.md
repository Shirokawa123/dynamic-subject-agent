# Slice-60：本地人物材料选择预览

2026-09-22，基线69c9857。已实现可运行的Facade预览、CLI与页面入口，真实Provider调用0、凭据读取0，R2计划digest未改变。不是自由聊天的话题识别、角色回复或新生活事件。

## 用户结果

显式选“怎么开始画画”得到学画来由与童年题材两项；“绘画经验”只保留多年经验，不泄露职业身份细节；“作品反馈”可预览简短童年受肯定的材料。初次问候、家庭近况、构图观点不强塞个人往事。每次最多2项/400字符，附出处和其他候选未选中原因。

分享策略是助手在本地预览中的保守设计，不是人物已同意披露。特别是家庭称赞等个人回忆，即使可预览也不能据此自动外发。时间待定直播候选、家庭变故、场景归纳、未证实习惯及错误主体保持排除；暂无由关系升级解锁的入口。

## 实现与复用

`ApplicationFacade.preview_conversation_basis(BasisPreviewRequest)`是唯一业务入口。`ConversationBasisPreview`集中核验已审阅S59包digest、原EPUB/文档hash及逐字段落引用，再提供固定话题映射。默认未装配为unavailable；文件缺失为unavailable；变更/引用不一致为failed-closed；正常但无需往事为typed no-op。每次重新读取来源，不以旧成功结果掩盖新变化。

composition仅在显式离线lab预览参数下装配，仍经open_local_product创建独立承载身份。CLI阻止与真实批准/suite混用，root也阻止真实模式与材料预览并用。UI经本地受token/Host约束的POST读取Facade，不自行选材或装配store/provider。无模型、关系更新、canonical写入、第二store或新依赖。

复用S54/S59的EPUB定位与指纹机制、既有Facade/lab/HTTP入口。应用codebase-design技能将校验/选择/失败语义集中在一个小Interface后；成熟设计继续采用[既有研究](../../plans/character-chat-architecture-alignment.md)对[Generative Agents原论文](https://arxiv.org/html/2304.03442v2)经历与生成分责的结论。这里只用明确话题和人工审阅材料，不引入其检索打分/Reflection或声称通用语义检索已成立。

## 验证

- 34项相关Python测试通过（23.05秒）：新增10项材料预览行为与24项角色对话/local_product/Gateway回归。
- 另12项ApplicationFacade回归通过（6.02秒）。补充源文件变化后关闭/重开核验后，10项预览测试再次通过（7.91秒）。
- Node共5个UI情景通过：旧发送/幂等错误流程，以及预览成功/no-op/完整性失败。预览期间锁住话题选择，防止响应与所选话题错配。
- 隐藏IAB实测选中两项与家庭话题排除说明，未抢焦点。服务和临时页已关闭。
- 实际S59包经Facade验证六种话题，结果为0/2/1/1/0/0项；调用attempts保持0，R2 digest仍为e2e01984ef27017754a81571c9a5f73857f4818809cbcd030c93bd3b6d59e7d0。只读快照存于`.artifacts/s60-preview/`。
- code-review按规格/标准双线只读审查，未发现可证实的新问题。未重跑旧927项全量，也未声称人物生成质量改善。

测试使用合成EPUB/包验证完整性与失败行为，真实S59原文不进入测试fixture。Hash只能保证与已审阅材料一致，不是自动语义理解或原作真伪判定。

## 运行与限制

```powershell
.venv/bin/python.exe app/desktop/character_dialogue_lab.py --preview-topic drawing-origins
.venv/bin/python.exe app/desktop/character_dialogue_lab.py --basis-preview
```

第二条启动页面后展开“本地材料预览”。默认产品不读取S59包；该包和小说按用户本地路径存在，其他checkout没有文件时明确不可用，不回退至模型猜测。当前校验针对S59这个已审阅版本，不是任意EPUB导入器。

后续需将普通消息映射到合适话题并决定是否分享，才可能进入回复；当前UI话题选项只是检查工具，不能作为用户聊天必须选菜单的最终设计。实际新增外发数据范围仍须明确，不能因为本地选出材料就自动发送给Provider。
