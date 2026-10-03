"""Whole disclosure acts are separate from old memory/life control words.

Correction and quoted/reported discussion do not revoke dialogue permission.
This local grammar recognises explicit acts and their object; it does not grant
memory, goal, file or life capabilities, or infer arbitrary Chinese intent.
"""
import re
import unicodedata

from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES

CONVERSATION = 'conversation'
WITHDRAWAL = 'withdrawal'
UNSUPPORTED = 'unsupported-operation'
UNRESOLVED = 'unresolved-disclosure'

HISTORY_FAILURE_CODES = frozenset(('original-whole-history-unverified', 'original-whole-history-withdrawn'))
KNOWN_REPLY_FAILURE_CODES = frozenset('original-whole-' + code for code in (
    (REVIEW_DIAGNOSTIC_CODES - {'review-schema', 'review-quote', 'review-label', 'transport-timeout', 'transport-delivery-ambiguous'})
    | {'character-credential-unavailable', 'structured-choice-invalid', 'expression-invalid', 'provider-failed', 'history-changed'}))
KNOWN_PUBLICATION_FAILURE_CODES = frozenset(('original-whole-authorization-changed', 'original-whole-unprepared-interruption'))

_PREFIX = r'(?:(?:请(?:你)?|麻烦(?:你)?|帮我|替我|给我|你|我们|我希望(?:你)?|现在|这次|还是|也|就|那|不过|但是)\s*)*'
_SOURCE = re.compile(r'(?:(?:我|我们|你|你们)的)?(?:(?:这|那)(?:段|些|份|条|句)?|之前|此前|刚才|先前|上次|旧的|旧)*(?:的)?'
    r'(?:(?:聊天|对话|历史|原话|消息|资料)(?:记录|内容|原文)?|记录|记忆)'
    r'(?:(?:里|中|内|的|来|用于|用作|作为).*)?(?:了|啦|吧|好吗|可以吗)?[?？]?')
_REFERENCE = re.compile(r'(?:(?:刚才|之前|此前|先前)(?:的)?)?(?:这(?:个|些|句|段话|件事|些内容)|那(?:个|些|句|段话|件事|些内容)|它)(?:话)?(?:了|啦|吧|好吗|可以吗)?[?？]?$')
_QUOTE_OBJECT = re.compile(r'〔引文([0-9]+)〕(?:了|啦|吧|好吗|可以吗)?[?？]?$')
_EN_SOURCE = re.compile(r'(?:(?:the|my|our|your|this|that|these|those|previous|earlier|prior|old|last|recent))*'
    r'(?:chat|conversation|history|phrase|words|messages?|records?|memory|information)(?:text|content)?[?]?$|whatijusttoldyou|whatisaid')
_EN_REFERENCE = re.compile(r'(?:this|that|it)[?]?$')
_EN_ACT = re.compile(r'^(?:please|canyou|couldyou|wouldyou)?(?:(?P<negative>(?:donot|don\x27t|don’t|never|stop)'
    r'(?:using|use|quoting|quote|referencing|reference|mentioning|mention|saying|say|remembering|remember|keeping|keep|storing|store|sharing|share|sending|send))'
    r'(?P<after>.*)|(?P<remove>forget|delete|erase|remove)(?P<object>.*))$')
_NEGATIVE = r'(?:不要|别|勿|不再|停止|不能|不许|禁止)(?:再|继续)?(?:使用|用|引用|参考|提起|提|说|记住|记|保存|保留|分享|发送)'
_REMOVE = r'(?:忘记|忘掉|遗忘|删掉|删除|清除|移除|撤回)'
_ACT = re.compile(r'^' + _PREFIX + r'(?:(?P<negative>' + _NEGATIVE + r')(?P<after>.*)|(?P<remove>(?:我|我们)?撤回|' + _REMOVE + r')(?P<object>.*))$')
_REVERSED = re.compile(r'^' + _PREFIX + r'(?:把|将)?(?P<object>.+?)(?P<action>' + _NEGATIVE + r'|' + _REMOVE + r'|不用(?:了|啦|吧)?)[?？]?$')
_NEGATED_TRANSFER = re.compile(r'^' + _PREFIX + r'(?:别|不要|勿|禁止|不许)(?:再)?(?:把|将)(?P<object>.+?)'
    r'(?:发给|发送给|提供给|交给|传给)(?:模型|你|别人|其他人|第三方|服务器|deepseek)(?:了|吧)?[?？]?$')
_REPORT = re.compile(r'^(?:(?:我|我们)?(?:昨天|前天|之前|上次|过去|曾经|刚才)(?:曾|已经)?(?:说|提到|写道|要求)|(?:你|他|她|他们|她们|朋友)(?:昨天|前天|之前|上次|过去|曾经|刚才)?(?:说|提到|写道|要求))')
_CURRENT = re.compile(r'^(?:现在|这次|不过|但是|但)(?:也|还是)?(?:请|你|我们|不要|别|勿|忘记|忘掉|删除|删掉)')


def _unquoted(message):
    text = unicodedata.normalize('NFKC', message).casefold()
    pairs = {'“': '”', '‘': '’', '「': '」', '『': '』', '"': '"'}
    output, index, unresolved, quotes = [], 0, False, []
    while index < len(text):
        character = text[index]
        if character in pairs:
            end = text.find(pairs[character], index + 1)
            if end < 0:
                unresolved = True
                output.append(text[index:])
                break
            output.append('〔引文' + str(len(quotes)) + '〕')
            quotes.append(text[index + 1:end])
            index = end + 1
        else:
            output.append(character)
            index += 1
    return re.sub(r'\s+', '', ''.join(output)), unresolved, quotes


def _source_object(text, quotes, *, literal_disclosure=False):
    if _SOURCE.fullmatch(text) or _REFERENCE.fullmatch(text) or _EN_SOURCE.fullmatch(text) or _EN_REFERENCE.fullmatch(text):
        return True
    quoted = _QUOTE_OBJECT.fullmatch(text)
    if quoted is None or int(quoted[1]) >= len(quotes):
        return False
    # Quotation is a syntactic argument, not automatically a history object.
    # A bare literal argument may be withdrawn. A quoted word used in a larger
    # purpose phrase (such as a color to paint with) is not that bare object.
    content = re.sub(r'\s+', '', quotes[int(quoted[1])])
    return literal_disclosure or bool(_SOURCE.fullmatch(content) or _REFERENCE.fullmatch(content)
        or _EN_SOURCE.fullmatch(content) or _EN_REFERENCE.fullmatch(content))


def _unsupported(clause):
    # Actual unsupported operations, not nouns or discussion about them.
    explicit = r'(?:请(?:你)?|麻烦(?:你)?|帮我|替我|给我)'
    effect = r'(?:保存|存档|导出|写入|复制)'
    if re.fullmatch(explicit + effect + r'[^。！？!?]{1,100}', clause):
        return True
    if re.fullmatch(r'(?:' + explicit + r')?(?:把|将)[^。！？!?]{1,100}' + effect +
        r'(?:(?:到|为|成)[^。！？!?]{1,100}|下来|起来)?(?:吧|一下)?[?？]?', clause):
        return True
    if re.fullmatch(r'(?:' + explicit + r')?(?:保存|存档|导出|写入|复制)(?:这|那|当前|刚才|本)[^。！？!?]{1,100}[?？]?', clause):
        return True
    operation = r'(?:设立|设置|创建|新增|更新|修改|变更|取消|撤销|撤回|放弃|完成)'
    ending = r'(?:(?:为|成|到|:)[^。！？!?]{1,200})?(?:吧|一下|好吗|可以吗)?[?？]?'
    if re.fullmatch(r'(?:' + explicit + r')?' + operation + r'[^。！？!?]{0,40}(?:目标|承诺|记忆)' + ending, clause):
        return True
    return bool(re.fullmatch(explicit + r'(?:记住|记下|记录)[^。！？!?]{1,200}[?？]?', clause))


def whole_dialogue_scope(message):
    text, unbalanced, quotes = _unquoted(message)
    if unbalanced:
        clauses = re.split(r'[。.!?！？，,；;：:]', text)
        if (any(_ACT.fullmatch(clause) or _EN_ACT.fullmatch(clause) or _NEGATED_TRANSFER.fullmatch(clause) for clause in clauses)
            or re.search(r'聊天|对话|历史|原话|消息|记录|记忆|资料', text)
            and re.search(_NEGATIVE + '|' + _REMOVE, text)):
            return UNRESOLVED
    unsupported = False
    for sentence in re.split(r'[。.!?！？]', text):
        reported = False
        for clause in re.split(r'[，,；;：:]', sentence):
            if not clause:
                continue
            if _REPORT.fullmatch(clause):
                reported = True
                continue
            if reported and not _CURRENT.match(clause):
                continue
            reported = False
            match = _ACT.fullmatch(clause) or _EN_ACT.fullmatch(clause)
            target = (match['after'] if match and match['negative'] else match['object'] if match else '')
            reverse = _REVERSED.fullmatch(clause)
            transfer = _NEGATED_TRANSFER.fullmatch(clause)
            literal_disclosure = bool(match)
            reverse_disclosure = bool(reverse)
            if (match and (not target or _source_object(target, quotes, literal_disclosure=literal_disclosure))
                or reverse and _source_object(reverse['object'], quotes, literal_disclosure=reverse_disclosure)
                or transfer and _source_object(transfer['object'], quotes, literal_disclosure=True)):
                return WITHDRAWAL
            unsupported = unsupported or _unsupported(clause)
    return UNSUPPORTED if unsupported else CONVERSATION


def is_whole_dialogue_control(message):
    return whole_dialogue_scope(message) in (WITHDRAWAL, UNRESOLVED)


def known_whole_failure(failure):
    return (failure.stage == 'history' and failure.code in HISTORY_FAILURE_CODES
        or failure.stage == 'whole-reply' and failure.code in KNOWN_REPLY_FAILURE_CODES
        or failure.stage == 'publication' and failure.code in KNOWN_PUBLICATION_FAILURE_CODES)
