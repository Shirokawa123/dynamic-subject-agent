# 后续准备：可重复打开的新交流入口

2026-10-02。当前执行S134；这里只准备后续完整用户结果，不启动新服务、不改变旧启动器或当前root。

缺口：`scripts/serve_original_whole_chat.py`与`Start-OriginalWholeChat.cmd`只创建S127/schema1入口；S132新边界及后续依据功能当前由开发者scratch服务在8787提供。用户需要正常可重复启动的入口，而不是依赖开发窗口。新入口应初次创建独立空历史context身份，以后返回同一段本地交流；旧入口、记录与运行服务保持。

已核源码：现有Entry已有精确review/freeze、初始化witness、严格pointer/identity核对、重开与空新分支验证，可提取共享生命周期；context必须freeze后直接以identity_id激活，不能复用旧select创建schema1。现health只有application标签，若新旧同标签，端口探测可能误把旧服务当新入口；新入口需准确独立标识，不能看到任意200就复用或自动杀端口占用者。

工程依据由context7 resolve/query Python标准库取得：[HTTPServer/ThreadingHTTPServer](https://docs.python.org/3/library/http.server.html)接收明确server_address，并由后者在线程处理请求；[server_close](https://docs.python.org/3/library/socketserver.html)负责清理server资源。只复用本仓已有`ThreadingHTTPServer(('127.0.0.1',port),Handler)`，不采用文档示例中的空bind地址，不改变Host/Origin/session-token保护。启动和资源释放不是模型生成，只有普通明确send进入原流程。

用户入口的设计类比沿[HAX G7](https://www.microsoft.com/en-us/haxtoolkit/guideline/support-efficient-invocation/)：需要时易于主动打开。此处纯工程与可达性即可解释，不需要心理/意识模型。无新库、服务、复制第三方代码或额外许可证成本；现有Python与浏览器继续使用。

候选接入：共享受限Entry生命周期，旧默认版本/root/marker字节和行为保持；另一个闭集context版本、固定新root与独立启动命令/health标签。只在首次建角读已审源包，之后重开读取完整sealed资产，不要求原EPUB常驻。初始化残缺/marker或identity不匹配保留现状并失败，不能删除、重建或自动迁移。新UI入口能力复用Facade和同一薄Adapter；不让Adapter装配Authority/Provider/Studio。

验收：真实新root首次为空、0模型，重开同profile/timeline且空历史保持；占用端口正确识别或明确失败、旧入口不被替换；缺源重开、marker/身份错误与旧生命周期兼容以独立合成Interface验证。真实交流效果继续用自有开发分支，不把验收台词预灌入供用户打开的空入口。不开云、不放局域网、不改credential/用途/旧数据；用户点击启动器才打开其浏览器，后台验收不抢焦点。
