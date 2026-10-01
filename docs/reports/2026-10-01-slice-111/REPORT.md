# S111：云端开发准备成果入库

2026-10-01，Asia/Shanghai。将仓库外已经准备的Linux开发、离线联调及验证成果整理为可随Git分支保留的源码与指南；产品方向仍是S109整体重规划。

## 已有云端成果与保存位置

源文件来自`/workspace/cloud-setup/dynamic-subject-agent/`，此前不属于Git跟踪清单。对应保存为：

| 已有成果 | 本轮保存 | 调整 |
| --- | --- | --- |
| `install.sh` | `scripts/cloud/install.sh` | 从脚本位置定位仓库，沿现有pip配置安装dev依赖 |
| `check_lab.sh`与`smoke_http.py` | `scripts/cloud/check_lab.sh`、`scripts/cloud/smoke_http.py` | 检查源码逐字保留；包装脚本复用该源码，支持显式loopback地址，消除重复内嵌代码 |
| `resolved-dependencies.txt` | `docs/cloud/resolved-dependencies.txt` | 逐字保留初始化解析版本，作为记录而非锁文件 |
| `start.md` | `docs/cloud/start.md` | 以仓库内脚本为入口整理安装、测试、打包、联调和平台边界，移除固定工作目录依赖 |

README新增指南入口。没有修改产品业务代码、Provider数据用途、生产凭据后端或依赖声明。

## 既有完整验证证据

解析现有`.scratch/cloud-onboarding-pytest.xml`确认：**1533 tests、0 failures、0 errors、0 skipped，373.821秒**，记录开始时间为2026-10-01 00:14:39（Asia/Shanghai）。报告文件SHA-256为`9a54a17b7b46d63eace079ec3ba786c3c8f494f6afdea630d523b7cdcb98a3ee`；源指南另外记录四项JS检查与wheel构建成功，现存初始化wheel也可定位。

上述1533项来自已有云端初始化执行，本轮没有重新跑完整Python套件。S110另有127项近期离线回归通过。测试计数不等于人物体验或真实Provider验收。

## 本轮重新执行的验证

- `bash -n scripts/cloud/install.sh scripts/cloud/check_lab.sh`通过；实际运行安装脚本，editable安装、`pip check`及Python/pytest/keyring/SQLite导入通过。
- 四份既有Node检查均重新通过：角色对话页面7情景、身份草稿隔离、无关取消保持编辑上下文、保存必须显式确认且关闭/跨身份预览不能保存。
- 新建本轮隔离离线lab，并从`/tmp`调用完整路径的`check_lab.sh`，验证脚本可在仓库外运行。页面、精确固定回声、revision/attempt递增、同请求幂等重放和关闭历史均通过；只终止本轮创建的子进程，既有服务未修改，临时合成产物保留在忽略目录。
- 实际运行`pip wheel --no-deps .`成功；生成`dynamic_subject_agent-0.0.0-py3-none-any.whl`，111个成员。检查为产品Python包及元数据，未包含运行数据库、小说来源、测试/报告或本地生成物。wheel保存在被忽略的`.scratch/cloud-s111-wheels/`，不提交二进制。
- 新增文件/增量均按S110规则检查。只提交脚本、指南、依赖版本快照及切片/状态/验证记录，不提交环境、PID/日志、JUnit原文件、wheel、合成lab状态或真实用户数据。源文件的密钥扫描关闭远程验证且无候选；报告中的JUnit SHA-256为公开文件指纹，不是密钥。

## 已实现与限制

已验证Linux离线开发、完整既有测试记录、打包和本机HTTP联调；均无需产品API key。现有生产凭据后端依然只支持Windows，Linux生产入口的凭据不可用限制仍在。手机入口、生产登录/HTTPS、常驻服务、真实角色生活、云数据迁移与新模型调用尚未由本轮实现或启动。

本轮是原提交授权下的补充阶段，沿`codex/verified-checkpoint-2026-10-01`新增commit，不改写`64404cc`回退点，不直接改main。提交后以远端SHA核对成功才交付链接。收口后回到S109方向讨论，不由环境准备自动进入产品部署。
