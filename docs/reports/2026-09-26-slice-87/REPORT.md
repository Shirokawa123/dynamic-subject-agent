# Slice-87：安全失败分类与首项诊断准备

2026-09-26，基线`5e0f124`。修复的是已确认的诊断信息丢失；S86真实失败原因仍未知，新增真实调用0。

## 用户结果与实现

原来网络故障、截断、JSON或审核结构错误最终都显示reply-review-failed，无法决定下一步修什么。新增严格1项的thinking-diagnostic配置，在显式冻结批准下提供闭集安全码；不会把技术失败算成审核误判。

复用现有Facade、Gateway、DeepSeek Transport和FrozenAttemptRun，没有新增存储或依赖。输入及生成参数与thinking-high一致，仅本地分类不同；旧standard/high默认公开失败码和请求契约保留。推理正文仍丢弃，错误记录不含响应/headers/异常原文/凭据或候选片段。技术失败即停，缓存不能把任意字符串或跨模式码带回，重启不重发。

## 诊断依据

S86只有通用码及约21秒的文件时间差，没有保留原始响应，无法追溯实际HTTP、finish_reason或用量。待验证原因是截断、格式/引用、HTTP/传输；耗时不足以排序为确定根因。

本轮复用已核对的[官方Chat Completion协议](https://api-docs.deepseek.com/api/create-chat-completion)，机制为finish_reason、usage与最终content的阶段检查；只适配现有实现，不引入第三方代码。未采用记录raw response、盲加预算或同时改多个参数，因为它们超出诊断需要或混淆原因。本片属于错误可观察性的工程修复，心理学不解释协议错误。

## 验证记录

已先在完整Facade及假Transport路径运行红测，网络异常与length/空content原先确实都落为reply-review-failed。这个复现锁定信息丢失，不能冒充复现S86原始故障。

独立Sol high复核另发现生产Transport提前拒绝超大响应，使底层size分类被普通传输码掩盖；已修复，保持ProviderFailureCode.UNAVAILABLE，仅诊断审核模式保留response-size。复核者本地stub opener验证通过，无未解决实质问题；未重复全面测试。

最终覆盖115个唯一用例：原审核/thinking/生成trial/DeepSeek相关回归103通过（220.63秒）；新诊断专项12通过（初始11项87.46秒，补生产Transport超限1项6.63秒）。复核发现cache测试补充时变量解包缺失，修正后该同一用例另跑通过（7.57秒），不重复计数。原103项运行始于最后超限修复前；修复后定向补跑生产Transport→Facade用例，同时验证旧thinking-high通用码、诊断response-size及重启不重发。测试没有访问真实Provider。

文档相对链接检查46处无缺失，git diff --check通过。未增加raw调试输出或保存实际响应，原始失败无法重放这一限制保留。

## 已冻结但未执行

首项cal-02计划`a3034c2fab184b725e68be5de1bf9e0282681b8458c6668f4f82aa3fd5e471cb`。实际prepare和本地比较确认：request对象与S86首项一致，13018出站字节完全相同，high/4096/30秒不变，新计划无started目录。

原8项仍为1尝试、7未发送。需要恢复诊断时采用[有界诊断与修复验证方案](../../plans/review-failure-diagnostic.md)取得新指示；当前没有增加调用，也没有启用日常审核或达到新角色MVP。
