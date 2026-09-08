"""Explicit red reproducer for the unimplemented operation, not a passing acceptance test."""
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.living_memory import (
    LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from test_recent_dialogue import open_app, submit


class ReportedForgetProvider:
    """External-boundary fixture preserving the independent report's NoOp symptom."""
    def propose(self, request):
        created = request.current_user_message == '我叫陆禾。'
        return LivingMemoryProviderResult(
            LivingMemoryProposal(LivingMemoryAction.CREATE if created else LivingMemoryAction.NONE,
                '我叫陆禾。' if created else ''), '本轮记忆处理。',
            '记下了。' if created else '好的，之前那个名字我不会再用了。', 'zh')

    def reply(self, request):
        return LivingMemoryReplyResult('好的，之前那个名字我不会再用了。', 'zh')


def test_natural_name_forget_cannot_leave_the_name_active(tmp_path):
    opened = open_app(tmp_path, ReportedForgetProvider())
    try:
        submit(opened, '我叫陆禾。')
        submit(opened, '这里叫我访客就好。把我之前报的名字忘掉，不用再保存了。')
        result = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline))
        assert not any(item.status == 'active' and '陆禾' in item.content
            for item in result.projection.memories)
    finally:
        opened.app.close()
