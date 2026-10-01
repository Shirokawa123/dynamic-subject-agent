# Linux云端开发与离线联调

本指南将既有云环境准备成果保存到仓库，支持Python测试、打包与本机HTTP联调。产品方向仍按[当前任务](../slices/current.md)和S109讨论；此工作流未实现手机访问、生产部署、Linux安全凭据后端或常驻角色生活。先读仓库`AGENTS.md`，不复制原用户身份、私聊、小说文件或凭据。

## 安装

需要Python ≥3.12、venv/pip和Node.js。进入仓库后执行；安装脚本也可从其它目录用完整路径调用，自行定位仓库根目录。

```bash
bash scripts/cloud/install.sh
source .venv/bin/activate
python -m pip check
```

安装遵循`pyproject.toml`的dev依赖范围，不安装Windows桌面extra。包安装沿环境现有网络/认证配置，不要求产品API key。既有环境解析版本见[版本记录](resolved-dependencies.txt)，该记录不包含后续加入的扫描工具，也不是锁文件。虚拟环境和构建产物保持忽略，不提交到Git。

## 测试与打包

以下命令在仓库根目录执行。每次pytest使用独立临时目录，避免同时写同一basetemp；输出记录在被忽略的`.scratch/`。

```bash
mkdir -p .scratch
.venv/bin/python -m pytest -q \
  --basetemp=/tmp/dynamic-subject-agent-cloud-pytest \
  --junitxml=.scratch/cloud-pytest.xml
node tests/character_dialogue_ui.cjs
node tests/subject_task_ui_drafts.cjs
node tests/subject_task_ui_editing.cjs
node tests/text_artifact_ui.cjs
.venv/bin/python -m pip wheel --disable-pip-version-check \
  --no-deps . --wheel-dir .scratch/cloud-wheels
```

已有云端初始化记录为1533项Python检查全部通过；本次入库重新执行的检查、来源和限制见[S111报告](../reports/2026-10-01-slice-111/REPORT.md)。这些是离线/替身Provider验证，不代表真实模型人物效果或Windows界面验收。

## 启动与检查离线HTTP lab

不需要常驻服务时直接跑测试。需要联调时，先核对已记录PID对应的完整命令和`/status`，只有确认为本任务的离线lab才复用；不会随文件系统快照恢复进程。没有可复用进程时启动默认离线lab：

```bash
mkdir -p .scratch
nohup .venv/bin/python -u app/desktop/character_dialogue_lab.py --port 0 \
  > .scratch/cloud-onboarding-lab.log 2>&1 &
cloud_lab_pid=$!
printf '%s\n' "$cloud_lab_pid" > .scratch/cloud-onboarding-lab.pid
```

日志出现启动端口后执行：

```bash
bash scripts/cloud/check_lab.sh
# 或显式指定已核实的离线lab地址：
bash scripts/cloud/check_lab.sh http://127.0.0.1:PORT
```

检查脚本从日志读取端口，或使用显式地址，调用同一份[HTTP检查源码](../../scripts/cloud/smoke_http.py)。检查页面可读、固定回声、revision/attempt递增、同请求幂等重放及关闭历史；每次只消耗一个本地回声请求，没有外部模型调用。达到lab的20次限制后使用新的隔离lab，不通过改记录重置额度。

不要添加`--approve-plan`、`--grounded-chat`等远程授权参数。离线lab仅绑定`127.0.0.1`，不作为外部手机产品入口；进程重启创建新临时会话，产物在已忽略的`.artifacts/character-dialogue-labs/`。停止时只处理核对过的、自己启动的PID，不停止既有用户服务，不删除其数据。

## 已确认的平台限制

生产凭据后端仍只支持Windows Credential Manager；Linux生产入口会报告`secure-backend-unavailable`/`credential-setup-required`，不能用环境变量、明文文件或内存存储替代。云端产品的登录、HTTPS、手机入口、持久盘、迁移与后台生活仍需落实S109的新方案，不能从离线开发环境准备推导为已完成部署。
