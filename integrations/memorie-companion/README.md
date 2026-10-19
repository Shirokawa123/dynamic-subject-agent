# 梅莫莉游戏内交流面板候选

S160本地准备：独立BepInEx IL2CPP插件，经loopback HTTP与ApplicationFacade薄Adapter通信。没有模型、凭据、人物原文或聊天事实库放进DLL；启动只创建收起的入口，连接与提交均由用户点击触发。原剧情、计时器和存档不由面板改写。

当前状态：exact人物/用途已批准，intent-3在独立后台5轮真实场景中有限保留用户意向、区分助手建议/用户采纳/完成。新的空日常入口experience-intent/8798已隐藏就绪，正式聊天0/模型0、C#只读连接过；旧体验根及已披露合成记录保留。游戏内曾验证面板展开、中文测试文本与草稿落盘；candidate10已安装，修复原生销毁后的清理访问，但最终按钮、最近入口及实际退出行为仍未验证，**目前不能称游戏面板已可日用**。用户要求仅后台，不操作游戏窗口或草稿。

构建使用仓库脚本`build_memorie_companion.ps1`，明确传入隔离SDK、BepInEx目录、同Unity版本的私有编译引用和新的`.artifacts`输出目录。最终输入候选使用本机BepInEx生成的Core/UI/TMP interop引用；引用均Private=false，不进入安装包。脚本只生成包和逐文件SHA256，不安装或启动游戏。编译引用DLL、官方运行时及游戏资源不提交本仓。

面板连接固定`http://127.0.0.1:8798/`，先核application/protocol，再读取状态；POST带本机会话token、当前人物scope、原消息和UUID。提交前服务端核scope；连接失败作未连接处理。失败保留输入，新输入不会被旧回执覆盖；原请求未知只查询，确认未找到后可明确继续提交同一UUID与原文。没有自动重发、离线补算或主动联系。

草稿/原请求仅保存于本机`BepInEx/config/MemorieCompanion/draft.json`，不作为聊天事实或Provider输入；磁盘失败保留内存新文字并阻发送。已提交交流来自既有Facade查询，客户端不另存聊天记录。实际发现旧IMGUI ScrollView/Scroller/TextArea不可还原，改用BeginGroup裁剪/滚轮、原生TMP输入与透明按钮捕获；程序清稿和用户输入双向即时同步，不靠下一次OnGUI延迟更新。最终按钮、收起焦点、物理拼音候选、窄屏与完整长文本仍需实际验收。

手动重开工具为仓库根目录`start-memorie-companion.cmd`；后端脚本`start_memorie_companion.ps1`本身默认不打开游戏，cmd显式带OpenGame。日常启动默认intent-3/新experience-intent，旧baseline可显式选择且Python CLI默认保持baseline。启动器由只读描述取得绑定准确root、版本和批准摘要的entry key，对复用与新启动均核验，错入口保留进程并拒绝；POST仍用会话token。仅在8798空闲时隐藏启动，初始化不调模型，没有系统服务、开机任务或通知。它不能替代上述待验步骤。

依赖来源：BepInEx `6.0.0-be.785+6abdba4`官方运行时（LGPL-2.1），Il2CppInterop及Doorstop以该运行时实际版本/上游许可为准；原始构建来源记录在S160报告。上游游戏桥的GPL业务逻辑没有复制到本插件，调查中公开的Unity6000.3.6编译引用仅本机使用；运行时interop由BepInEx在用户机器生成。当前包仅用于本机验证，不发布游戏资源或二进制引用。
