# 最新main复现：纠错误拦与同段持久阻塞

基线main/远端80e227636be2dde1859e3c4e3dccb848db3a916e，2026-10-02。本阶段真实Provider调用0。Facade context_fixture配生产whole cognition/Host/Timeline与合成Transport驱动用户五步症状；合成回复不冒充人物验收。

已运行命令：`PYTHONPATH=src python -m pytest tests/test_whole_correction_scope.py -q --basetemp=C:/Users/30252/AppData/Local/Temp/dsa-s138-repro-01`。10.72秒红；原始顺序为terminal → original-whole-history-unverified → 同码 → 同码 → close/reopen后同码。只有正常首轮进入fake wire；普通纠错和其后三次普通请求均FailedClosed，真实空白不是此症状的解释。

静态已见whole current与history共用first_life谓词，底层裸词含说错/更正/纠正；verified whole prefix扫描旧失败再次调用该predicate并返回None。待拆证假设：只修当前谓词仍会被旧failure阻断；只修prefix仍会拦当前纠错。材料/Provider问题与同root首轮正常且之后0wire不相符。下一阶段只修这些经证实接缝，保持真正撤回和未知失败闭锁。

复现回归由核心owner暂未提交，修复后与稳定源码一起收口；本证据保留原始红结果，不改写为成功。核心实现前按[S138完成条件](../../slices/slice-138-correction-continuity-and-empty-diagnosis.md)核对普通语义/撤回/向前接续，旧v1/LIFE不扩语义。
