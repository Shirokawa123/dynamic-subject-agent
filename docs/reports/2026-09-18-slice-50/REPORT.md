# Slice-50：逐次确认的本地文本保存

新建身份可以把已接受主体任务的本地正文保存为应用专用目录中的新UTF-8文本：查看完整预览、逐次确认、查询完成/失败、重复确认保护与中断恢复已接通。正文不因保存外发。没有覆盖、删除、任意路径、联网执行或新增模型用途。

## 机制与复用

复用ApplicationFacade、Host worker、Admission/Publication及任务面板。新binding采用`subject-text-effect-cycle-1.0`，新Timeline为schema 2；旧v1读写和权限保持，control schema不变，不迁移已有身份。

核对[AWS transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)，借鉴先提交intent、后执行、重复可恢复；SQLite与文件不是同一事务，不假称原子。借鉴[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)的恢复重验，批准绑定原preview basis。未引入框架、依赖、第二canonical store或外部服务。

Context7 resolve查询因fetch failed不可用，改查[Python os.link/fsync](https://docs.python.org/3/library/os.html#os.link)及[微软CreateHardLink](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw)。采用同卷暂存+hardlink发布，目标已存在时仅samefile及exact bytes可认领；不凭同内容冒认成功。暂存保留，不做未经授权清理。支持进程中断窗口的可恢复性，不扩称任意文件系统/硬件断电保证。

effect receipt追加到同一canonical SQLite并引用intent Outcome/digest；独立receipt chain/count/head检出尾删、错序和缺失。重放在intent后应用完成/失败；未决effect后禁止继续Publication。有permit的执行路径在admit与resume/freeze前和Publication后恢复；查看、预览、导出和治理冷启动不触发文件。导出包含真实schema、receipt与head。历史完成不等于之后的文件存在性监控。

## 实际结果

全新生产合成Avery：`C:/Users/30252/AppData/Local/Temp/dsa-s50-isolated-20260918`。使用既有Windows Credential Manager slot，key不打印或落盘。见[验收脚本](live_acceptance.py)、[逐次结果](live.jsonl)。

- 两次明确任务/修订，Agency仅2次请求；本地正文未进入投影。
- 首次preview不创建目录；修订后旧basis确认无效且无文件。
- 新basis确认后任务completed，UTF-8字节与完整预览相等。
- 相同key重复确认，文件inode/mtime不变；只创建一个目标文件。
- 关闭/重开，任务状态及原保存路径完全一致；保存/preview/重启没有模型调用。

独立审阅未发现权限越界或隐式迁移；修复旧身份recover入口误报available，现明确unavailable。初始测试发现读取器仍拒绝非空effect，已修复；未放宽RevisionSet。全量回归发现v1伪造user_version的错误分类变化，恢复原unsupported-schema-version语义；32项Admission+effect回归通过。

## 验证与边界

初始effect 8项、集成42项通过；最终effect 11项通过，另2项导出验证通过；UI三个Node脚本验证草稿/编辑隔离和显式确认、撤销预览、跨身份失效。全量运行为**921 passed / 1 failed in 763.64s**；唯一失败是上述schema错误分类，已修复并由**32 passed in 23.26s**覆盖Admission和最终13项effect行为。最终固定版本全量绿色结果将在紧接的Slice-51补录，不把此前失败隐藏成全绿。测试包括Publication前无文件、intent后/文件后恢复、相同内容但不同所有权目标、部分暂存、receipt尾删、旧权限、下一任务先恢复再裁决容量。

后续收口：Slice-51对a60cc74全量924项通过；明确清单修复后最终5ab5fe6全量927项通过，见[最终报告](../2026-09-18-slice-51/REPORT.md)。

后台IAB打开隔离root的真实桌面HTTP页面，只读查看“主体任务”面板和截图：dogfood-s50、已保存状态与完整换行路径均可见，无横向溢出；将任务标签改成分行以改善表单阅读。没有提交新消息、读取正式身份或占用Windows输入焦点，临时页与服务随后关闭。

尚未自动生成主体任务稿件：用户可在既有聊天中创作后明确选择/粘贴正文保存。旧身份不自动升级；新建身份可使用本切片功能。下一项是冻结版本混合场景验收和交付收口；正式身份连续使用新功能需要独立迁移决定。
