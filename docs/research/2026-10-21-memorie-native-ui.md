# 梅莫莉：原版互动与视觉整合

## 用户结果、缺口与验收

2026-10-21用户明确要整个系统尽可能融入原版互动、新增按钮/界面接近原版。当前插件是IMGUI默认深色窗体混合原生TMP/透明按钮捕获：原生点击仍未完整验，独立连接步骤和常驻工具布局也打断原作体验。用户此前要求后台测试，本次不推定已允许窗口/键鼠操作。

本轮在同一S160，把既有已批聊天做成游戏内自然入口：从原HUD找她说话，打开只读接通，在角色仍可见的画面下方交流；完整记录按需展开；关闭立即释放自有输入，草稿/原UUID保留。原剧情或原菜单优先。正常路径不显示连接、地址、审计或请求技术名词；遇故障才出现保留文字、重新接通/确认结果等具体操作。游戏计时/笔记/待办保持原入口，不造第二套数据。

可观察验收分开：编译与C#协议/草稿/一次提交检查；离线原素材样稿的中文阅读、布局和状态；实际游戏中HUD随隐藏、剧情/菜单让位、开合/IME/发送/原请求查询与滚动。最后一项不能在后台约定下假称已验。此次不调用模型，不重跑已终态人物场景。

## 本机证据与方向

只读当前安装资源中MainUI_Root、UI_Note、UI_StoryLog、UI_DialogBG、UI_Telop、UI_StoryFrame、UI_ToDo及Custom yarnSpinner System。MainUI的Left_DownArea是原剧情/休息/环境/相机入口，原按钮90×90、相机位置x472/y60；原入口与MainUI的Active_Root共隐显。UI_StoryLog有木棕装饰边框，原对话有靛蓝半透明底与暖白字，Note又有自己的蓝色表面，不能把“原版风格”简化为一块通用紫色圆角卡片。

原Image有现成sprite、type、颜色；TMP/LocalizedFontSwitcher负责原版字体。新组件只借这些可见样式值与素材引用，不克隆带剧情/存档回调的完整业务对象。优先在原HUD旁增加一个“聊聊”入口，下方对话区沿原作文字框，聊天记录沿原日志面板；保留角色为画面主体。采用这个已由用户选定的原版方向，不探索无关视觉方案。

官方[画面页](https://bexide.co.jp/memorie)用于核对整体语言（其中标明截图为Switch版），本机prefab是PC实现依据。官方示图仅作视觉参考，本机资源/私有预览不随仓库发布。原作版权属于BeXide；不新增外部分发资源的许可推定。

## 官方机制与接入

本轮Context7已可用，已解析并查询`/unity-technologies/ugui`、`/yarnspinnertool/yarnspinner-unity`，不沿用此前“不可用”的工具事实。

- [uGUI Image](https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Documentation~/UIVisualComponents.md)：借原Sprite/type与颜色，九宫格保边角；不修改共享材质或原Image。
- [CanvasScaler源码](https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Runtime/UGUI/UI/Core/Layout/CanvasScaler.cs)：原HUD子节点继承其尺寸/缩放；避免另叠一套IMGUI坐标与输入画布。
- [Button源码](https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Runtime/UGUI/UI/Core/Button.cs)、[Selectable源码](https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Runtime/UGUI/UI/Core/Selectable.cs)：创建自有Button及监听，借可见样式/按下反馈，不执行原业务回调。
- [ScrollRect官方说明](https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Documentation~/script-ScrollRect.md)：viewport/content/mask同属原生事件系统，替代此前剥离失败的IMGUI ScrollView和透明捕获混用。
- [Yarn DialogueRunner](https://github.com/YarnSpinnerTool/YarnSpinner-Unity/blob/main/_autodocs/api-reference/dialogue-runner.md)：只读IsDialogueRunning作为原剧情优先判断；本机生成interop确有getter。不调用StartDialogue/Stop，不把模型文字当Yarn程序或强塞原Presenter的语音/剧情生命周期。

原uGUI/Bep/TMP依赖已存在，本轮不新增外部运行依赖。只使用公开API/现有本机interop引用。纯交互工程与视觉一致性改版，无新增人物心理机制，哲学/心理学理论不适用；自然度仍待实际操作和用户判断。

## 取舍与数据边界

同日用户后续已明确最终目标是角色点击/当前状态/统一生成与原生反馈的整链，见[最新设计](../plans/memorie-companion-integration.md#2026-10-21最终目标与整条互动链)。以下“不接管角色单击”是首份原生面板的当时实现取舍，不是产品目标的永久排除；当前尚未验证互斥与新用途，不能直接启用或把先做HUD当最终完成。

不继续给旧工具窗仅换颜色：输入与按钮仍跨两套事件系统，且默认布局不融入原作。不克隆整个原菜单/对话Runner：可能复制持久监听与存档/剧情副作用。不接管角色单击或改变原故事入口：暂没有足够运行证据证明不抢占原交互；先在同一HUD增加可发现入口，并让原窗口/剧情优先。

开合自动执行的只是本地health/session/status读取，不自动提交草稿、查询后重发或调用模型。提交仍是用户按下主按钮后使用原scope/UUID/精确原文；未知结果只能显式查询，缺失后继续原消息仍须明确操作。新输入不被旧回执覆盖。所有回复/事实仍通过ApplicationFacade与canonical Timeline；DLL不另建事实库。

“整个系统”作为整体体验方向：聊天、续接、记录和失败恢复融入本轮；原专注/待办/笔记各自仍可在游戏内使用。把原游戏事件作为人物记忆、让角色主动评论计时、自动动作或通知是后续有数据/行为差异的接入，不由UI改版自动启用。当前character/personality/exchange/current_message四字段、原Provider/凭据与用途保持。

本地提取、官方参考图、Sprite定位、metadata只存`.artifacts/s160/native-ui-20261021`；不提交游戏资源、台词原文、用户草稿或存档。所有旧候选/首次/未验保留。
