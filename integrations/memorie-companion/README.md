# 梅莫莉原生交流界面候选

S160本地准备：独立BepInEx IL2CPP插件，经loopback HTTP与ApplicationFacade薄Adapter通信。DLL没有模型、凭据、人物原文或聊天事实库。当前0.2.0以原HUD/uGUI/TMP承载入口、交流与记录；打开只读接通，只有明确发送才请求回复。原剧情、计时器和存档不由插件改写。

当前状态：candidate14已在确认游戏关闭时仅替换自有DLL，编译0警告错误、9项既有接口/C#检查通过，原生样稿经一轮看图细化；**尚未验证新视图的真实Unity画面、点击或IME，不称已可日用**。原10/18与10/19真实模型/旧面板结果全保，不能迁移为新UI验收。用户仍要求仅后台，本轮没有启动/操作游戏或新增产品模型调用，[本轮报告](../../docs/reports/2026-10-21-slice-160/REPORT.md)。

构建使用仓库脚本`build_memorie_companion.ps1`，明确传入隔离SDK、BepInEx目录、本机生成interop和新的`.artifacts`输出目录。Core/UI/TMP/YarnSpinner.Unity编译引用均Private=false，不进入安装包。脚本只生成包和逐文件SHA256，不安装或启动游戏。编译引用DLL、官方运行时、原字体和游戏素材不提交本仓。

`NativeGameUi`只读定位原MainUI的Left_DownArea、HUD/遮罩状态及Yarn.IsDialogueRunning，借原Sprite和字体元数据；不读取待办/笔记文字，不调用原业务按钮或Yarn命令。`NativeChatView`新建自己的原生按钮/ScrollRect/TMP输入，沿原Canvas缩放；原HUD隐藏、原剧情/遮罩占用时收起并保草稿，不自动抢回焦点。原素材缺失时保持不可用而非叠回旧工具窗。实例缓存与实际场景加载/动态弹窗的共存仍待验。

面板连接固定`http://127.0.0.1:8798/`，先核application/protocol，再读取状态；POST带本机会话token、当前人物scope、原消息和UUID。提交前服务端核scope；连接失败作未连接处理。失败保留输入，新输入不会被旧回执覆盖；原请求未知只查询，确认未找到后可明确继续提交同一UUID与原文。没有自动重发、离线补算或主动联系。

草稿/原请求仅保存于本机`BepInEx/config/MemorieCompanion/draft.json`，不作为聊天事实或自动Provider输入；磁盘失败保留内存新文字并阻发送。已提交交流来自既有Facade查询，客户端不另存聊天事实。等待时输入框可以保留新稿，记录面板单列完整“等待确认的原话（尚未加入聊天记录）”；查询确认缺失后，主按钮明确“继续发原话”，不误发输入框的新稿。开时先启用交互再激活输入，关时先释放自有输入再禁组；异步回执不聚焦。旧IMGUI/透明捕获实现已由原生控件替代，旧失败仍保留在报告。

手动重开工具为仓库根目录`start-memorie-companion.cmd`；后端脚本`start_memorie_companion.ps1`本身默认不打开游戏，cmd显式带OpenGame。日常启动默认intent-3/新experience-intent，旧baseline可显式选择且Python CLI默认保持baseline。启动器由只读描述取得绑定准确root、版本和批准摘要的entry key，对复用与新启动均核验，错入口保留进程并拒绝；POST仍用会话token。仅在8798空闲时隐藏启动，初始化不调模型，没有系统服务、开机任务或通知。它不能替代上述待验步骤。

依赖来源：BepInEx `6.0.0-be.785+6abdba4`官方运行时（LGPL-2.1），Il2CppInterop及Doorstop以该运行时实际版本/上游许可为准；原始构建来源记录在S160报告。上游游戏桥的GPL业务逻辑没有复制到本插件，调查中公开的Unity6000.3.6编译引用仅本机使用；运行时interop由BepInEx在用户机器生成。当前包仅用于本机验证，不发布游戏资源或二进制引用。
