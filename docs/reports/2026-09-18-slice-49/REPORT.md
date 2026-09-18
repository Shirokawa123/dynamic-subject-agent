# Slice-49：主体任务协商与恢复

用户已批准D-026路线A。本切片把显式文字任务接入ApplicationFacade和Windows任务面板：接受、缺信息澄清、容量暂缓、有限不支持动作拒绝、修订与取消可查询且跨重启。任务属于主体Agency，与用户目标/承诺分开；accepted当前仅表示待处理，尚未生成成品或执行文件保存。

## 复用与取舍

复用已有Agency Domain、ModelGateway、canonical Timeline、幂等Admission与原子Publication。参考已核对的[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)，修订绑定任务revision、恢复重验状态；不引入checkpointer或第二任务store。采用既有reason中的typed状态碎片机制，重放重算裁决，与原始Admission及完整canonical任务快照核对。未引入新依赖/源码/许可证，也未扩大发往既有12类模型请求的数据。

新binding以持久contract version派生exact权限；旧binding不自动升级。现有effect数据库硬约束仍为false/empty/unavailable，本切片不借reason隐瞒执行。后续真正effect使用独立版本设计；旧身份迁移仍需另外决定。

## 真实验收

全新合成Avery root：`C:/Users/30252/AppData/Local/Temp/dsa-s49-isolated-20260918`。通过生产composition和DesktopState后台接口，Windows Credential Manager既有slot仅供HTTPS Bearer使用；没有读取正式identity或输出key。见[脚本](live_acceptance.py)与[逐次记录](raw/live.jsonl)。

- 陶艺桌短诗接受；展台卡片因已有accepted任务暂缓。
- 取消第一项后重新提交第二项变为accepted；再次修订时不会把自己当竞争任务。
- 保存请求缺正文进入needs_input；补充本地正文后accepted。
- 关闭/重开后完整任务记录相等；未执行任何文件effect。
- 共6次Agency请求，取消不调用模型；每次只有授权的四个投影字段，本地`LOCAL_ONLY_BODY`不在外发文本。原12类调用为0。真实体验只证明这些合成场景，不证明任意措辞分类稳定。

## 审阅修复与验证

独立审阅识别并修复：伪造Cognition任务快照能污染后续重放；修订把自身作为占用；HTTP冲突误等旧结果；切换身份草稿串用；取消B清掉正在编辑A。失败、拒绝或降级修订保留原accepted任务。新增本地正文exact字符/换行保留和提交前序列化上限检查，防止NFC规范化悄改正文。

全量回归**907 passed in 752.04s**，命令`.venv/bin/python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s49-full`。该运行启动后补充的正文序列化修复及4项测试另由最终任务18项验证通过（18.70s），覆盖所有当前差异；不把907称作最终911项全量运行。UI实际脚本Node VM两项通过，见`tests/subject_task_ui_drafts.cjs`与`tests/subject_task_ui_editing.cjs`。最初错误调用系统Python导致import收集失败，随后改用仓库venv；另一次未指定临时目录触发Windows Temp权限错误，指定独立basetemp后通过，均不是产品断言失败。

## 剩余工作

没有真正生成/完成任务或执行文件；不支持旧身份任务权限自动升级。下一切片按唯一执行书实现精确预览/批准、真正committed effect及可恢复结果，保持普通聊天基线。有限不支持动作识别不是通用意图判别，不能把模型无依据拒绝当主体决定。
