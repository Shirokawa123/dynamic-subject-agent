# S159：梅莫莉本机只读勘察结果

2026-10-18。用户明确剧情已全部通关并允许查看本地游戏目录。本轮结果：**实际读出原作剧情与中文台词，找到现有文字呈现及动作/表情机制的接缝候选，适合继续准备通关后的自由交流插件。** 运行兼容、游戏内新面板与模型效果尚未验证，不把静态资产解析当作插件已经可用。

## 本机事实

安装目录 `D:/SteamLibrary/steamapps/common/Memory_of_Memorie`，Steam app4337440/build25527425。资源头实际为Unity `6000.3.6f1`；global-metadata.dat头部版本39。脚本为IL2CPP，Addressables下有2259个bundle，StreamingAssets共2263文件约478MB。本机未见已安装的BepInEx桥接。

目录中的SavesDir仅枚举到一个.vdf文件；本轮未读取其内容，也未读取目录外的存档、Steam用户资料或实际私人待办。通关进度来自用户明确答复，不假称通过存档审计得出。

## 实际读出的剧情与人物来源

| 资源 | 实际结果 | 适用边界 |
| --- | --- | --- |
| `Assets/App/Localization/YarnSpinnerStringTable/YarnSpinnerStringTable_zh-Hans.asset` | 807条简中条目、合计15439字符；全部能关联shared表的line ID | 这是条目与字符数，含日常交流、剧情、选项等，不全是独立人物事实 |
| `Assets/App/Dialogue/YarnProject.yarnproject` | compiledYarnProgram398549字节，按官方protobuf格式解析677节点；主剧情节点scenario_Story_001至055共55个 | 静态解析，不是恢复未经分支判断的实际播放顺序，也不是执行剧情 |
| 编译程序与简中表关联 | 770次台词指令、30次选项指令，800个不同line ID，800/800均有简中内容 | 807条中7条未被本次程序台词/选项指令引用；shared表964键不等于964条有效剧情 |
| `DataStringTable_zh-Hans`及shared表 | 256条，可关联55话标题/集数与日常独白等资料 | 不把UI标题或独白配置直接当现实已发生事件 |
| `MonologueTable.asset` | 20条独白配置，含本地化key、表情与语音资源引用 | 证明有既有表现素材，不证明任意生成台词已有配音能力 |

第52话实际描述重新建立联系、梅莫莉与村庄等迁移至新的地方，并询问是否身处玩家PC；第53话继续研究魔法/药草与照顾花，第54–55话回顾相处并期待平常日常继续。结合用户通关事实，**助手建议以这个通关后处境为人物起点**。原作前史与插件启用后的真实自由聊天分别处理，不重置成刚认识，也不把原作台词冒称新系统已有的聊天记忆。

本地已保留[通关后起点草案](../../../.artifacts/s159/memorie-postgame-basis.md)，逐项回指节点和line ID；这只是本轮关键节点草案，尚非完整人物分析或freeze。剧情内停服台词不是现实发行公告，原文“看到玩家”也不构成真实摄像头/读屏能力。

## 游戏内交互的接缝

实际解出 `Assets/App/Prefabs/YarnSpinner/Custom yarnSpinner System.prefab`。其序列化引用与Addressables MonoScript表相互对应，确认：

- `Yarn.Unity.DialogueRunner`拥有YarnProject、variableStorage、Unity本地化lineProvider与4个dialoguePresenters引用；prefab的autoStart为false。
- 本地化组件对应`Yarn.Unity.UnityLocalization.UnityLocalisedLineProvider`，有stringsTable和assetTable引用。
- 两处文字呈现组件对应`App.YarnSpinner.SonityVoiceAndLinePresenter`，含lineText、characterNameText、canvasGroup、逐字显示/自动推进及字体切换字段。
- `App.YarnSpinner.YarnSpinnerUtility`引用同一个DialogueRunner以及语音/文字与对话文字呈现组件。
- 编译剧情包含既有`act`、`face`、`look`等命令及实际动作/表情名；类型与资源中可定位YarnCharacterControl、YarnAnimationControl、YarnCharacterMonologue、ScenarioManager、StoryManager、PomodoroTimerView。

这些是**有具体资源和对象引用的候选接缝**，还没有验证运行时对象获取、方法签名、线程调度、原剧情与新增聊天互斥，也没有自由文字输入框已存在或可直接复用的证明。原第三方桥仍仅提供计时API；不能从上述发现声称其已开放任意动作或对话。

## 建议的第一版接法

1. 以当前build验证桥接/运行对象读取，再增加游戏内自由交流入口的最小探针，保留原剧情及进度；如需启动或有焦点操作，先准备准确动作并与用户约定。
2. 从已定位原文继续整理连贯的通关后人物资料。优先保留她自己的关注、能力边界、原作前史和表达方式，避免变成通用学习督促助手。
3. 现有Python底座经Facade承担新身份的持久交流与共同经历；游戏插件承担输入、显示及有来源的状态观察，新增能力通过实际合同接入。模型输出只作为文字/有界提议，不能当Yarn脚本或游戏命令直接执行。
4. 首个完整结果仍是开工交流→真实专注→休息接话→重启/下次接续。原声素材存在不代表自由生成配音已实现；动作与表情可在文字闭环成立后按需要接入。

这是助手方案细化，并未确定剧情生成分支规则，未安装插件、冻结新人物或新增出站用途。后续先准备精确人物/共同学习投影和未发送样例；不借旧S158人物Grant外发新资料，不把游戏原作或存档全文提交远程模型。

## 工具、来源与保留验证

- 按context7-mcp技能核当前工具，Context7无可调用接口；格式与库行为回退[UnityPy官方项目](https://github.com/K0lb3/UnityPy)、[MIT许可](https://github.com/K0lb3/UnityPy/blob/master/LICENSE)、[Yarn官方protobuf定义](https://github.com/YarnSpinnerTool/YarnSpinner/blob/main/YarnSpinner/yarn_spinner.proto)、[Line Provider说明](https://docs.yarnspinner.dev/components/line-provider)与[Presenter说明](https://docs.yarnspinner.dev/api/csharp/yarn.unity/yarn.unity.dialoguepresenterbase)。旧定位的Yarn文档URL失效后，使用当前官方文档入口。
- UnityPy实际版本1.25.2及二进制依赖仅装入`.artifacts/s159/tools`，通过单次进程sys.path使用；未修改生产依赖或游戏目录，未执行游戏程序集。pip针对全局已装包显示兼容警告，但本次为--target隔离安装，未据此改动全局包。本轮无产品模型/凭据调用。
- 只读Unity资源，按类型树提取所需对象；本地小型解析器只读取公开protobuf字段，不执行Yarn指令。类名首次因程序集名是否带.dll过滤差异未命中已修正；prefab脚本引用须用Addressables MonoScript表关联，未把初次空结果当不存在。
- 游戏2299个文件的前后相对路径/大小/mtime一致，新增0、移除0、变化0。该检查证明所查元数据保持，不冒充整树内容hash对照；另对9个关键来源资源记录SHA256以便定位。
- 原始提取、编译节点、研究工具及来源hash仅在本地忽略目录保留：[台词索引](../../../.artifacts/s159/extracted/dialogue-zh-hans.json)、[节点与分支指令](../../../.artifacts/s159/extracted/yarn-nodes.json)、[解析汇总](../../../.artifacts/s159/extracted/yarn-summary.json)、[来源定位](../../../.artifacts/s159/source-assets.json)、[只读核对](../../../.artifacts/s159/game-readonly-check.json)。不提交游戏全文/资源、私人记录或工具依赖至远端。

本轮由主窗口直接处理，文件读取、格式核对与方案判断相互依赖，未新增子代理。是纯工程/来源可用性勘察，没有新增心理机制；原文中的人格表达只作设计资料，不作为AI具有心理或意识的证明。

S159以本轮只读勘察结果收口；游戏插件、模型数据用途和真实体验仍待后续具体任务承接。S158原未完成事实与旧身份/资料保持。
