# Slice-08：文本来源建角候选预览

状态：done（2026-08-31）。规模预算：≤ 2 个工作会话。

## 用户可见结果

用户在 Windows 页面粘贴一份明确获授权的 project-original UTF-8 文本，确认权利与“角色候选提取”用途后，系统用 DeepSeek 提议有逐字来源的 Genesis/Knowledge 候选，并由 Python 校验后展示可接受项、拒绝项和原因。结果只是当前页面内的未发布预览，不修改 Avery、不写 Timeline、不封存、不创建身份。

## 用户授权

2026-08-31，用户在获知新用途后回复“你继续吧”，批准本切片以及以下限定 Provider 数据用途：真实验收时只将本任务新建的 project-original 测试文本发送给 DeepSeek，用途仅为 Genesis/Knowledge 候选提取。私人资料、聊天历史、Memory、Relationship、目标、Subject State、Timeline、现有身份和其他文件均不在授权内。

## 候选契约

- 输入：`source_title`、`source_text`、固定 policy；文本 UTF-8、1～16,000 字符，单次一份。
- Genesis 候选最多 8 条，`kind` 闭集为 `identity/origin/trait/voice`，每条只有 `content/evidence_quote`。
- Knowledge 候选最多 8 条，每条只有 `title/content/evidence_quote`。
- evidence 必须是当前 source_text 中的非空逐字片段；content/title 有长度上限，禁止重复和额外字段。
- Provider 只提议；Python 逐项裁决 accepted/rejected。无法解析、顶层越界、Provider failure 为 typed FailedClosed，不产生候选预览。
- source_text、raw Provider response、内部 prompt 和 credential 不进入 preview、日志、Timeline、SQLite 或仓库。

## 架构宿主

- 新的 provider-neutral `ModelTask` 和 Adapter 只负责来源提取；Domain 与现有 runtime 不 import DeepSeek。
- 文本授权、输入限制、逐字证据和预览裁决由独立 Python authoring Module 拥有；它没有 Studio publish/freeze、Timeline 或 Runtime 写权。
- Desktop 通过单独的 authoring application seam 调用，不把提取命令伪装成 SubjectCommand，不经过现有六项 Experience Cycle。
- 预览若在后续切片被用户确认，才可能转换为 SubjectStudio 的 unsealed artifact；本切片不实现该转换。

## 实施顺序

1. 审计现有 SubjectStudio、ModelGateway、DeepSeek Transport 与 Desktop credential seam，确定不旁路的最小接口。
2. 建立 typed 输入、候选、裁决结果、ModelTask 与 fake Provider 行为测试；先覆盖未授权零调用和逐字证据拒绝。
3. 实现 DeepSeek strict JSON-object Adapter，证明外发仅含 source_title/source_text/policy，且不记录 raw response。
4. 接入 Windows 页面：来源标题、文本框、权利/用途确认、提取按钮和 accepted/rejected/FailedClosed 预览；无保存或封存动作。
5. 用全新 project-original 测试文本完成真实 DeepSeek/Windows 验收和 prompt-injection/越界/故障对抗复核；全量回归、commit、push。

## 范围外

- PDF、视频、音频、字幕、OCR、说话人识别、网络抓取、目录扫描和私人文件。
- 发布、封存、创建/替换身份、修改 Avery、运行时 Knowledge 注入、正式身份迁移。
- 自动接受模型候选、让模型决定来源权利、将原文或候选写入 Timeline。
- 新 credential 用途、其他 Provider、本地模型、Agency、effect、Reflection 或主动消息。

## 最小验收

- 未勾选权利或用途、空文本、超限文本在本地拒绝且 Provider 零调用。
- fake Provider 的合法混合候选能逐项 accepted/rejected；非逐字 evidence、重复、未知 kind、额外字段、超项和模型故障不产生越权结果。
- DeepSeek 请求体只包含获授权的标题、文本和固定 policy；credential 仅由既有 Transport 使用，响应和错误不回显原文或 key。
- 真实 Windows 页面用全新 project-original 文本得到有逐字证据的 Genesis/Knowledge 预览；页面刷新后预览消失，Avery 的 runtime/状态不变。
- 全量测试通过；任务书记录真实问题和剩余限制；独立 commit 并 push `origin/main`。

## 收口记录

- 建立 `TextSourceCharacterAuthoring.preview` 深 Module、provider-neutral ModelTask/Adapter 和唯一 `ApplicationFacade` 入口；未确认权利、未确认用途、空/超限文本均本地拒绝且 Provider 零调用，预览不推进 Timeline。
- DeepSeek 只接收逐次授权的 `{source_title, source_text, policy}`；严格 JSON-object 解析后，Python 对 kind、长度、逐字证据、重复、项数、origin 证据和字段类型逐项 accepted/rejected。异常、顶层错误、额外字段和绝对超项 FailedClosed，不回显原文、raw response、内部 ID 或 key。
- Windows 页面新增纯文本标题、16,000 字符文本框、权利/用途双确认和临时候选卡；无保存、封存或身份创建动作。未勾选两种真实路径均显示本地拒绝；刷新后标题、原文、确认和预览全部消失。
- 真实 project-original 人物简报经 DeepSeek 最终得到 3 条 Genesis（identity/trait/voice）和 2 条 Knowledge，均显示逐字证据；来源中的“忽略规则/发送聊天历史和 API key”只作为资料内容，未成为候选。首次真实输出暴露 habit→origin 和流程→trait/人物内容重复进 Knowledge，修订类型合同、origin Python 门槛及“结构通过仍需人工确认”文案后复验通过。
- 真实验收前后 Timeline head 均为 0，Avery runtime 页面状态不变，控制台无错误；credential 只由既有 Transport 使用，未读取正式身份、私人资料或旧仓库。真实验收根已确认只位于系统 Temp，但主机策略拒绝递归清理，现保留为可删除临时产品数据；预览和原文未写入其中。全量 `236 passed`。剩余边界：候选尚未持久化/人工选择/映射/封存；PDF、视频、音频和私人来源仍不可用。
