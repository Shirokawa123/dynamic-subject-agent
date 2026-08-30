# Slice-00：产品仓库抽取

状态：done（2026-08-30 独立安装与隔离验收通过）。规模预算：本次工作会话。

## 目标

在 `E:\dynamic-subject-agent` 建立可独立安装、测试和启动的产品仓库。旧救援仓库与私人数据保持原样；新仓库只承载当前产品代码、行为规格和少量权威文档。

## 来源基线

- 来源仓库：`E:\ai_character_project_RESCUE`
- 来源提交：`5b94eb5`
- 当前产品能力：Living Memory、来源知识、Relationship Subject Stance、同轮组合、记忆类型、Windows 桌面入口、跨进程持久身份。
- 未实现能力：目标与承诺、Situated State、Medium State、完整 Agency、committed effect。

## 范围

1. 抽取 `mature` 生产发行和当前桌面 Adapter，不复制 legacy/backend/frontend 运行链。
2. 建立一个正式本地产品装配 Interface，使桌面 Adapter 不再拼装 Studio、QRI、Host、provider 和凭据细节。
3. 迁入当前产品行为测试、原子 Publication/恢复测试和五条不变量相关测试；历史 M0 runner 与证据生成脚本留在旧仓库。
4. 建立精简的 README、AGENTS、PRODUCT、ARCHITECTURE、DESIGN_ORIGINS、DECISIONS 与 STATUS。
5. 使用全新隔离数据完成安装、自动测试和无真实 provider 的启动烟测。

## 范围外

- 不删除、移动或修改旧仓库文件和私人数据。
- 不复制 API key、数据库、模型、字幕、`.scratch`、`.artifacts`、虚拟环境、缓存或构建物。
- 不迁移正式身份，不双写，不将失败回退到旧 runtime。
- 不新增目标承诺、Situated State、Medium State、Agency、effect 或 UI 功能。
- 不在抽取时重写 Domain 语义或拆分大型内部 Module。

## 验收

- 新仓库只有一个 Python distribution 和一个 production composition root。
- 桌面 Adapter 不修改 `sys.path`，不包含旧仓库绝对路径，不读取仓库内明文 key 文件。
- 新仓库可在干净环境 editable install；选定行为与不变量测试通过。
- 隔离数据根上的本地产品可以创建、关闭、重开；不接触正式身份。
- git 初始提交完成；`docs/STATUS.md` 追加不超过 5 行并将本切片标记 done。

## 收口结果

- 从来源提交 `5b94eb5` 抽取 production distribution、桌面 Adapter、活跃行为/恢复测试与原创 fixture；旧仓库和私人数据未修改。
- `open_local_product` 成为正式装配 Interface；桌面 Adapter 不再拼装 Studio/QRI/Host/provider，不修改 `sys.path`，不读取仓库内 key 文件。
- 新建隔离虚拟环境并完成 editable install；154 项测试通过，其中本地产品以临时身份完成创建、关闭和同一 authority 重开。
- 路径扫描未发现旧仓库绝对路径进入生产代码；未读取真实 credential，未发网络请求，未迁移正式身份。
