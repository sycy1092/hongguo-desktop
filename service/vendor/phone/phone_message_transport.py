"""Authorized manual message pages only; no background reads or retries."""
import json,re,time
from types import FunctionType
from urllib.parse import urlsplit,parse_qs
from phone_account_flow import AccountError
from phone_message_list import parse_message_page

ENABLED=True
HOST='api5-normal-lq.fqnovel.com'
PATH='/reading/msgapi/get_ugc_message/v:version/'
LIMIT=512*1024

def query_for(group,cursor=None):
    if type(group) is not int or not 0<=group<=999999999:raise AccountError('消息分类无效，尚未发送请求。')
    if cursor is None:cursor={'next':'','readBefore':''}
    elif not isinstance(cursor,dict) or set(cursor)!={'next','readBefore'} or not cursor['next']:
        raise AccountError('消息分页位置无效，尚未发送请求。')
    for v in cursor.values():
        if not isinstance(v,str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,30})?',v):raise AccountError('消息分页位置无效，尚未发送请求。')
    return {'count':'20','cursor':cursor['next'],'before_session_read_max_msg_id':cursor['readBefore'],'msg_group_type':str(group)}

def validate_url(url,query,body=b''):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!=HOST or p.path!=PATH or p.fragment or body:raise AccountError('消息请求地址异常，尚未发送。')
    values=parse_qs(p.query,keep_blank_values=True)
    if any(values.get(k)!=[v] for k,v in query.items()):raise AccountError('消息请求参数异常，尚未发送。')

def prepare(context,query):
    import phone_account_transport as protocol
    from phone_account_favorites import request_context,reading_minimal_headers
    original=protocol.signed_request
    signer=FunctionType(original.__code__,{**original.__globals__,'LIBRARY':set(protocol.LIBRARY)|{PATH}},original.__name__,original.__defaults__,original.__closure__)
    url,body,headers=signer(request_context(context),PATH,extra=query)
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!=protocol.HOST or p.path!=PATH or p.fragment or body:raise AccountError('消息签名地址异常，尚未发送。')
    target='https://'+HOST+PATH+'?'+p.query;validate_url(target,query,body)
    return target,reading_minimal_headers(headers)

def fetch(flow,group,cursor=None):
    if not ENABLED:raise AccountError('消息列表尚未启用，未读取消息。')
    query=query_for(group,cursor)
    import requests
    from phone_account_favorites import authenticated
    from phone_account_transport import region_headers
    authenticated(flow);transport=flow.transport
    url,headers=prepare(transport.context,query);validate_url(url,query)
    cookies={c.name:c.value for c in transport.client.cookies};headers.update(region_headers(cookies))
    if transport.token:headers['X-TT-Token']=transport.token
    with requests.Session() as client:
        client.trust_env=False;client.auth=None;client.headers.clear();client.cookies.clear()
        for name,value in cookies.items():client.cookies.set(name,value,domain=HOST,path='/')
        if client.get_adapter(url).max_retries.total!=0:raise AccountError('消息读取不允许自动重试。')
        prepared=client.prepare_request(requests.Request('GET',url,headers=headers))
        if prepared.url!=url or prepared.body is not None:raise AccountError('消息请求编码异常，尚未发送。')
        try:
            started=time.monotonic()
            with client.send(prepared,timeout=(8,20),allow_redirects=False,stream=True,verify=True) as response:
                if response.status_code!=200:raise AccountError('消息服务暂不可用，登录保持原样。')
                chunks=[];size=0
                for chunk in response.iter_content(32768):
                    size+=len(chunk)
                    if size>LIMIT or time.monotonic()-started>30:raise AccountError('消息响应超出限制。')
                    chunks.append(chunk)
                # The temporary HTTP session is discarded; no returned cookies or tokens
                # replace the account session and no message text is persisted or logged.
                page=parse_message_page(json.loads(b''.join(chunks)))
                if len(page['items'])>20:raise AccountError('消息页超出本次读取数量。')
                return page
        except (requests.RequestException,ValueError,TypeError):
            raise AccountError('消息暂未读取成功，登录和原结果保持原样。') from None
