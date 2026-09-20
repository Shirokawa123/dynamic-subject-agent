# 小说来源定位与起点边界：原型前研究

2026-09-20。范围：公开标准、EbookLib、epub.js三组官方资料。没有读取小说原文、私人文件或凭据，没有调用角色模型、安装依赖或修改产品。Context7两次库解析均fetch failed，按技能回退官方文档与源码。

## 结论

复用EPUB的阅读顺序与定位机制，把“人物在起点知道什么”作为独立语义核对。解析器不能证明人物提取完成。当前不锁定依赖，也不把章节顺序当故事时间线。

## 官方事实与复用取舍

- [EPUB 3.3 spine](https://www.w3.org/TR/epub-33/#sec-spine-elem)以itemref/idref定义默认阅读顺序，linear=no标识辅助内容，缺省为yes。读取应取spine顺序，不能用ZIP顺序或文件名排序；辅助内容标记应保留。
- [EPUB CFI 1.1](https://idpf.org/epub/linking/cfi/epub-cfi.html)提供出版物内位置/连续范围定位，涉及结构路径和文本偏移，可用于展开来源后回到原文；定位需要绑定具体文件版本，不能保证改版或DOM改写后仍指向相同语义。
- EbookLib的[reader源码](https://raw.githubusercontent.com/aerkalov/ebooklib/master/ebooklib/reader.py)将spine读取为(idref, linear)列表，能减少容器/manifest/spine自建。[源码许可声明](https://raw.githubusercontent.com/aerkalov/ebooklib/master/ebooklib/epub.py)为AGPL-3.0-or-later；[v0.20发布记录](https://github.com/aerkalov/ebooklib/releases)包含修复和测试工作流改进。仅列为Python解析候选，引入前仍须核实锁定版本及项目许可证兼容性；不提供人物知情判断。
- epub.js的[官方API](https://raw.githubusercontent.com/futurepress/epub.js/master/documentation/md/API.md)包含cfiFromRange/getRange转换，可用于浏览器原文选区定位。[package](https://raw.githubusercontent.com/futurepress/epub.js/master/package.json)声明版本0.3.93和BSD-2-Clause，[许可证](https://github.com/futurepress/epub.js/blob/master/license)可查；[GitHub Releases](https://github.com/futurepress/epub.js/releases)最新标记为v0.3.88，证据不一致，不能据此宣称维护活跃或选定生产版本。

## 原型建议（研究推断，非用户已确认决定）

1. 来源定位至少保留文件指纹/版本、spine序号、文档href和原始段落范围。若需要阅读器选区再加入CFI，保留文本归一化前后的对应关系。
2. 起点是具体段落边界及之前/之后；给用户看卷章名和附近原文进行简明确认。
3. 每条人物候选区分来源位置、描述所涉时间、角色是否知情及确认状态。起点前出现的文字不证明角色知情；起点后出现的回忆也可能涉及此前背景。首份原型不自动吸收起点后的内容填背景。
4. 先验证选择起点、展开候选来源、纠错和确认的流程。需要原书排版/选区时再评估epub.js，EbookLib保持候选；此次没有依赖引入决定。

## 未决与接续

具体小说文件、版本和开篇段落未提供。叙述者信息、伏笔、回忆与人物知情的判定须结合材料验证，不能靠文件解析格式解决。引入任何库前，还需核对锁定版本、依赖许可证、近期维护响应、Windows集成成本，以及预览脚本和外部资源访问边界。研究不授权小说外发。

对应[小说提取如何保留来源与起点边界](../../.scratch/character-chat-wayfinder/issues/01-novel-source-boundary.md)。该研究由source_research子代理完成，主代理整理落盘；下一步素材准备仍是未解决票。
