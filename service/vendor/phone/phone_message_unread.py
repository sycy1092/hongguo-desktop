"""Manual unread-count read. No message body, acknowledgement or persistent session updates."""
import json,re,time
from types import FunctionType
from urllib.parse import urlsplit,parse_qs
from phone_account_flow import AccountError
HOST='api5-normal-lq.fqnovel.com'
PATH='/reading/msgapi/getnewmsggroupcount/v'
QUERY={'skip_cache':'false','im_merchant_msg_count':'0','im_conversation_msg_count':'0','is_pull_notifications':'false','im_show_count':'true','msg_group_list_type':'2'}
LIMIT=256*1024
FIELDS={'total':'total','commentAndMention':'comment_and_at_me_count','mentions':'mention_count','replies':'im_reply_count','likes':'im_digg_count','notifications':'notification_count','authorNotices':'author_notice_count'}

def validate_url(url,body=b''):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!=HOST or p.path!=PATH or p.fragment or body:raise AccountError('未读数请求地址异常，尚未发送。')
    values=parse_qs(p.query,keep_blank_values=True)
    if any(values.get(k)!=[v] for k,v in QUERY.items()):raise AccountError('未读数请求参数异常，尚未发送。')

def prepare(context):
    import phone_account_transport as protocol
    from phone_account_favorites import request_context,reading_minimal_headers
    original=protocol.signed_request
    signer=FunctionType(original.__code__,{**original.__globals__,'LIBRARY':set(protocol.LIBRARY)|{PATH}},original.__name__,original.__defaults__,original.__closure__)
    url,body,headers=signer(request_context(context),PATH,extra=QUERY)
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!=protocol.HOST or p.path!=PATH or p.fragment or body:raise AccountError('未读数签名地址异常，尚未发送。')
    target='https://'+HOST+PATH+'?'+p.query
    validate_url(target,body)
    return target,reading_minimal_headers(headers)

def count(value):
    if type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,8}',value):return int(value)
    if type(value) is int and 0<=value<=999999999:return value
    raise AccountError('未读数量格式暂未识别，未更新原结果。')

def parse_counts(root):
    if not isinstance(root,dict) or type(root.get('code')) is not int or root['code']!=0 or not isinstance(root.get('data'),dict):raise AccountError('未读数暂未读取成功，登录保持原样。')
    data=root['data']
    if any(type(owner['error_code']) not in (int,str) or str(owner['error_code'])!='0' for owner in (root,data) if 'error_code' in owner):raise AccountError('未读数查询被拒绝，登录和原结果保持原样。')
    if 'total' not in data:raise AccountError('未读总数缺失，未更新原结果。')
    # Categories can overlap. Never add them together or treat absent fields as zero.
    counts={key:count(data[field]) for key,field in FIELDS.items() if field in data}
    return {'counts':counts,'readAt':int(time.time())}

def fetch(flow):
    import requests
    from phone_account_favorites import authenticated
    from phone_account_transport import region_headers
    authenticated(flow);transport=flow.transport
    url,headers=prepare(transport.context)
    cookies={c.name:c.value for c in transport.client.cookies};headers.update(region_headers(cookies))
    if transport.token:headers['X-TT-Token']=transport.token
    with requests.Session() as client:
        client.trust_env=False;client.auth=None;client.headers.clear();client.cookies.clear()
        for name,value in cookies.items():client.cookies.set(name,value,domain=HOST,path='/')
        if client.get_adapter(url).max_retries.total!=0:raise AccountError('未读数不允许自动重试')
        prepared=client.prepare_request(requests.Request('GET',url,headers=headers))
        if prepared.url!=url or prepared.body is not None:raise AccountError('未读数请求编码异常，尚未发送。')
        try:
            started=time.monotonic()
            with client.send(prepared,timeout=(8,20),allow_redirects=False,stream=True,verify=True) as response:
                if response.status_code!=200:raise AccountError('未读数服务暂不可用，登录保持原样。')
                chunks=[];size=0
                for chunk in response.iter_content(32768):
                    size+=len(chunk)
                    if size>LIMIT or time.monotonic()-started>30:raise AccountError('未读数响应超出限制')
                    chunks.append(chunk)
                return parse_counts(json.loads(b''.join(chunks)))
        except (requests.RequestException,ValueError,TypeError):raise AccountError('未读数暂未读取成功，登录和原结果保持原样。') from None
