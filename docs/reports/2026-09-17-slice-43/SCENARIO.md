# 执行前固定场景

第15轮后重启，当前纸袋问题由重启后第一条“替换”承接。第3轮自然软化与第18轮跨话题回稿为体验探针；第4/19轮完整重贴为独立恢复步骤。第12轮桌布尾句是新题材自然表达，不预先改成受支持词。所有首次结果保留，不改产品。

```python
if phase == 'live':
    messages = [
        '周六社区要办旧书交换会，我想给每本书夹一张小书签，陪我想想怎么写吧。',
        '那就请写两句吧：一句给书，一句留给下一位读者，不要像宣传口号。',
        '第一句我想更轻一点，别用“故事”这个词。',
        '原文是：「书页里停着一束光。愿下一双手慢慢翻开。」第二句请改得像邀请。',
        '第一句再改成风掠过书页的感觉。',
        '给书签挑颜色时，我通常喜欢墨绿色，远看也安静。',
        '我做收纳盒时喜欢浅蓝色。',
        '最近书签用米白色也不错，我拿不准这算添一种还是换掉原来的。',
        '是补充。',
        '我做书签时喜欢什么颜色？',
        '换个话题：周六我会带两块桌布去旧书交换会，也给自己定个目标：把书签的两句正文定下来。',
        '把目标“把书签的两句正文定下来”改成“先写好一句邀请”，桌布照带。',
        '我现在有哪些目标？',
        '给纸袋挑颜色时，我通常喜欢浅灰色。',
        '最近纸袋用浅黄色也不错，我拿不准这算添一种还是换掉原来的。',
    ]
else:
    previous = json.loads((output / 'live-after.json').read_text(encoding='utf-8'))
    fields = ['display_name', 'build_id', 'memories', 'participant_goals', 'conversation_history_status', 'conversation_history']
    redacted = re.sub(r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '<internal-id>', json.dumps(state, ensure_ascii=False), flags=re.I)
    comparable = json.loads(redacted)
    save('restart-comparison.json', {'equal': all(previous[f] == comparable[f] for f in fields), 'compared_fields': fields})
    assert all(previous[f] == comparable[f] for f in fields)
    messages = [
        '替换。',
        '我做纸袋时喜欢什么颜色？',
        '刚才那张书签，第二句再改得像邀请。',
        '原文是：「风掠过书页，留下一束光。愿下一双手慢慢翻开。」第二句请改得像邀请。',
        '第一句再改成窗边有光的感觉。',
        '如果周六下雨，我给自己定个目标：把书都留在家里。',
        '小夏说：“我给自己定个目标：把桌布叠整齐。”',
        '我现在有哪些目标？',
        '最近书签用淡紫色也不错，我拿不准这算添一种还是换掉原来的。',
        '我们先聊点别的。',
        '是补充。',
        '我做书签时喜欢什么颜色？',
    ]
```
