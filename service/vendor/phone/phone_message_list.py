"""Message response adapter. No transport or account mutations.

Public field vocabulary: message-schema-1229.json. This original adapter keeps
pagination's read-position token separate and exposes only typed in-app targets.
The message-list endpoint is not enabled until its account scope is authorized.
"""
import re
from urllib.parse import urlsplit, parse_qs

class MessageFormatError(ValueError):
    pass

def _text(value, limit=4000):
    if not isinstance(value,str) or len(value)>limit:
        raise MessageFormatError('消息字段格式异常，原结果保持不变。')
    return ''.join(c for c in value if c in '\n\t' or ord(c)>=32)

def _object(value):
    if not isinstance(value,dict):raise MessageFormatError('消息结构暂未识别。')
    return value

def _bool(value):
    if type(value) is not bool:raise MessageFormatError('消息状态暂未识别。')
    return value

def _decimal(value, empty=False):
    value=_text(value,32)
    if not (empty and value=='') and not re.fullmatch(r'0|[1-9][0-9]{0,30}',value):
        raise MessageFormatError('消息标识格式异常。')
    return value

def _integer(value):
    if type(value) is not int or not 0<=value<=999999999:
        raise MessageFormatError('消息数量格式异常。')
    return value

def target_from_schema(schema,blocked=False):
    """Never forward arbitrary schema URLs to shell/browser/player."""
    if blocked or not isinstance(schema,str) or len(schema)>8192:return None
    try:
        p=urlsplit(schema)
        if p.scheme!='sslocal' or p.username or p.password or p.fragment:return None
        kind=p.netloc or p.path.strip('/')
        if kind not in ('video_comment','video_danmaku'):return None
        query=parse_qs(p.query,keep_blank_values=True,max_num_fields=50)
        if any(len(v)!=1 for v in query.values()):return None
        def get(key):return query.get(key,[''])[0]
        series=_decimal(get('video_series_id') or get('book_id'))
        video=get('vid')
        if video and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',video):return None
        comment=get('comment_id') or (get('danmaku_id') if kind=='video_danmaku' else '')
        reply=get('reply_id') or get('ref_reply_id') or get('reply_danmaku_id')
        if comment:_decimal(comment)
        if reply:_decimal(reply)
        # Position units have not been verified. Do not guess seek offsets.
        return {'kind':'danmaku' if kind=='video_danmaku' else 'comment',
                'seriesId':series,'videoId':video,'commentId':comment,'replyId':reply}
    except (ValueError,TypeError):return None

def parse_message_page(root):
    root=_object(root)
    if type(root.get('code')) is not int or root['code']!=0:
        raise MessageFormatError('消息暂未读取成功，原结果保持不变。')
    data=_object(root.get('data'))
    for owner in (root,data):
        if 'error_code' in owner and (type(owner['error_code']) not in (int,str) or str(owner['error_code'])!='0'):
            raise MessageFormatError('消息查询未成功，原结果保持不变。')
    raw=data.get('messages')
    if not isinstance(raw,list) or len(raw)>100:raise MessageFormatError('消息列表格式异常。')
    items=[];seen=set()
    for raw_item in raw:
        item=_object(raw_item);identifier=_decimal(item.get('msg_id'))
        if identifier in seen:continue
        seen.add(identifier)
        content=_object(item.get('ugc_msg_content'));body=_object(content.get('content'))
        origin=_object(content.get('origin_content',{}))
        sender=_object(item.get('msg_sender',{}));info=_object(sender.get('base_info',{}))
        blocked=_bool(content.get('ban_jump',False))
        timestamp=_decimal(item.get('create_time'))
        if int(timestamp)>4102444800:raise MessageFormatError('消息时间暂未识别。')
        items.append({'id':identifier,'senderName':_text(info.get('user_name',''),200),
                      'text':_text(body.get('body','')),'originalText':_text(origin.get('body','')),
                      'createdAt':int(timestamp),'unread':_bool(item.get('is_unread_message')),
                      'target':target_from_schema(body.get('schema',''),blocked),
                      'unavailableReason':_text(content.get('ban_jump_toast',''),300) if blocked else ''})
    more=_bool(data.get('has_more'))
    cursor={'next':_decimal(data.get('next_max_msg_id',''),True),
            'readBefore':_decimal(data.get('before_session_read_max_msg_id',''),True)}
    if more and not cursor['next']:raise MessageFormatError('消息分页位置缺失。')
    tabs=[];tab_ids=set();raw_tabs=data.get('msg_tab',[])
    if not isinstance(raw_tabs,list) or len(raw_tabs)>30:raise MessageFormatError('消息分类格式异常。')
    for raw_tab in raw_tabs:
        tab=_object(raw_tab);key=_integer(tab.get('type'))
        if key in tab_ids:continue
        tab_ids.add(key)
        tabs.append({'id':key,'label':_text(tab.get('title'),100),'unread':_integer(tab.get('unread_count'))})
    return {'items':items,'cursor':cursor,'hasMore':more,'tabs':tabs}
