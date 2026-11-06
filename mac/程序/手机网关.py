# coding: utf-8
"""Paired HTTPS access for the iPhone app; existing loopback API remains private."""
import base64,http.client,json,ssl,secrets,hashlib,os,subprocess,threading,mimetypes,re
from 存取公共 import data_dir
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse,parse_qs,unquote,quote
from pathlib import Path

def configuration(root):
 folder=data_dir(root)/'手机连接';folder.mkdir(parents=True,exist_ok=True)
 config=folder/'配对.json';cert=folder/'证书.pem';key=folder/'私钥.pem'
 if not cert.exists() or not key.exists():
  import 跨平台;c,k=跨平台.self_signed('Coda Phone');cert.write_text(c,encoding='ascii');跨平台.write_private(key,k)
 if config.exists():data=json.loads(config.read_text())
 else:data={'token':secrets.token_urlsafe(32)}
 data['host']=__import__('跨平台').host_name()
 data['port']=int(os.environ.get('LESSON_PHONE_PORT','18766'))
 der=ssl.PEM_cert_to_DER_cert(cert.read_text());data['fingerprint']=hashlib.sha256(der).hexdigest()
 config.write_text(json.dumps(data,ensure_ascii=False,indent=2));config.chmod(0o600)
 return data,cert,key

def start(root,local_token,port=18766,upstream_port=18765,upload_root=None):
 root=Path(root).resolve();home=root.parent if root.name=='配套文件' else root
 config,cert,key=configuration(root)
 class Gateway(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def authorized(self):
   cookie=SimpleCookie()
   try:cookie.load(self.headers.get('Cookie',''))
   except Exception:return False
   value=self.headers.get('Authorization','').removeprefix('Bearer ')
   if not value and 'lesson_device' in cookie:value=cookie['lesson_device'].value
   from 设备配对 import device_role
   self.device_role='legacy' if value and secrets.compare_digest(value,config['token']) else device_role(root,value) if value else None
   return self.device_role is not None
  def reply(self,code,data):
   raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  def do_GET(self):self.handle_request()
  def do_POST(self):self.handle_request()
  def handle_request(self):
   try:
    if self.command=='POST' and self.path=='/mobile/pair':
     from 设备配对 import claim
     size=int(self.headers.get('Content-Length','0'))
     if size<=0 or size>4096:raise ValueError('配对请求无效')
     self.reply(200,claim(root,json.loads(self.rfile.read(size))));return
    # 手机网页版（10-23）只在 18767（受信任证书那个端口）上
    if getattr(self.server,'web',False):self.web();return
    # 局域网里的其他电脑（浏览器）：/desk 申请 → Mac 上允许 → 带着 lesson_desk 小饼干访问，整套 Mac 网页都转给它
    dpath=urlparse(self.path).path
    if dpath=='/desk' or dpath.startswith('/desk/'):self.desk(urlparse(self.path));return
    role=self.desk_role()
    if role:self.desk_proxy(role);return
    # 浏览器直接打开网址（没有配对令牌、也不是手机 App）：带去申请页，不显示一串错误
    if self.command=='GET' and dpath=='/' and not self.headers.get('Authorization') and 'lesson_device' not in self.headers.get('Cookie','') and 'text/html' in self.headers.get('Accept',''):
     self.send_response(302);self.send_header('Location','/desk');self.send_header('Content-Length','0');self.end_headers();return
    if not self.authorized():self.reply(401,{'error':'手机尚未配对'});return
    origin=self.headers.get('Origin')
    if origin and origin!='https://'+self.headers.get('Host',''):self.reply(403,{'error':'来源不符'});return
    parsed=urlparse(self.path)
    if self.device_role=='read-upload':
     read_paths={'/','/state','/editing/status','/list','/student-docs/list','/videos/list','/student-notes/list','/studentdoc','/sheetfile','/scanfile','/mobile/media'}
     if parsed.path not in read_paths and parsed.path not in {'/mobile/upload','/mobile/sheet','/mobile/sheet/commit','/mobile/paper','/mobile/leave','/mobile/attend','/mobile/mark','/student-docs/upload'}:self.reply(403,{'error':'此设备只允许查看和上传资料'});return
    if self.command=='POST' and parsed.path=='/mobile/upload':self.upload();return
    if self.command=='POST' and parsed.path=='/mobile/sheet':self.sheet();return
    if self.command=='POST' and parsed.path=='/mobile/sheet/commit':self.sheet_commit();return
    if self.command=='POST' and parsed.path=='/mobile/paper':self.paper();return
    if self.command=='POST' and parsed.path=='/mobile/leave':self.leave();return
    if self.command=='POST' and parsed.path=='/mobile/attend':self.leave('/api/attend');return
    if self.command=='POST' and parsed.path=='/mobile/mark':   # 10-24 App 里的打点：开始、结束各交一次（同一个编号）
     length=int(self.headers.get('Content-Length','0'))
     if not 0<length<=8192:raise ValueError('提交内容无效')
     x=json.loads(self.rfile.read(length));self.upstream('/api/marks/save',{k:x.get(k) for k in ('id','students','course','week','start','end')}|{'by':'手机'});self.reply(200,{'ok':True});return
    if self.command=='GET' and parsed.path=='/mobile/media':self.media(parsed);return
    allowed={'/bulk-lessons/commit','/','/state','/save','/merge-local','/manual-backup','/weekly-backup','/backups','/restore-backup','/export','/scan','/list','/archive','/sheetfile','/scanfile','/editing/acquire','/editing/status','/studentdoc'}
    if parsed.path not in allowed and not parsed.path.startswith(('/videos/','/sheets/','/student-docs/')):self.reply(404,{'error':'未知请求'});return
    length=int(self.headers.get('Content-Length','0'))
    if length<0 or length>36*1024*1024:raise ValueError('请求过大')
    payload=self.rfile.read(length) if length else None
    conn=http.client.HTTPConnection('127.0.0.1',upstream_port,timeout=180)
    try:
     conn.request(self.command,self.path,payload,{'Host':'127.0.0.1:%d'%upstream_port,'Origin':'http://127.0.0.1:%d'%upstream_port,'X-Local-Token':local_token,'X-Lesson-Device':'iPhone','Content-Type':self.headers.get('Content-Type','application/json')})
     response=conn.getresponse();raw=response.read();self.send_response(response.status);self.send_header('Content-Type',response.getheader('Content-Type','application/octet-stream'));self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    finally:conn.close()
   except (BrokenPipeError,ConnectionResetError):pass
   except Exception as e:self.reply(400,{'error':str(e)})
  def upload(self):
   length=int(self.headers.get('Content-Length','0'))
   big=2
   if length<=0 or length>big*1024**3:raise ValueError('每个文件需小于%dGB'%big)
   name=Path(unquote(self.headers.get('X-Filename',''))).name
   if Path(name).suffix.lower() not in ({'.mov','.mp4','.m4v','.heic','.heif','.jpg','.jpeg','.png'} | ({'.m4a','.txt'} if self.headers.get('X-Capture-ID') else set())):raise ValueError('请选择视频或照片')
   name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',name)[:160]
   staging=Path(upload_root)/'临时文件' if upload_root is not None else data_dir(root)/'手机上传中';staging.mkdir(parents=True,exist_ok=True)
   temp=staging/(secrets.token_hex(12)+'.partial');target=home/name
   if target.exists():target=home/(Path(name).stem+'_'+secrets.token_hex(4)+Path(name).suffix)
   capture_id=self.headers.get('X-Capture-ID','')
   record=None
   if capture_id:
    if not re.fullmatch(r'[A-Fa-f0-9-]{36}',capture_id):raise ValueError('拍摄编号无效')
    raw=self.headers.get('X-Capture-Metadata','')
    if len(raw)>16384:raise ValueError('拍摄信息过大')
    record=json.loads(base64.b64decode(raw,validate=True))
    if record.get('id')!=capture_id:raise ValueError('拍摄编号不符')
    # Deterministic destination makes retries safe when the response was lost.
    if record.get('kind') in {'voice-note','text-note'}:
     notes=root/'资料'/'课堂随记';target=notes/name
     if upload_root is None:notes.mkdir(parents=True,exist_ok=True)
    else:target=home/name
   if upload_root is not None:
    category='笔记' if record and record.get('kind') in {'voice-note','text-note'} else '照片与视频'
    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',Path(unquote(self.headers.get('X-Filename',''))).name)[:160]
    folder=Path(upload_root)/category/(capture_id or secrets.token_hex(16));folder.mkdir(parents=True,exist_ok=True)
    target=folder/name
   self.connection.settimeout(180)
   checksum=hashlib.sha256()
   try:
    with temp.open('xb') as f:
     left=length
     while left:
      block=self.rfile.read(min(left,1024*1024))
      if not block:raise ValueError('上传中断，未归档')
      f.write(block);checksum.update(block);left-=len(block)
     f.flush();os.fsync(f.fileno())
    actual=checksum.hexdigest()
    expected=self.headers.get('X-SHA256','')
    if expected and expected!=actual:raise ValueError('文件校验失败，手机原件保留')
    if record:
     if target.exists():
      h=hashlib.sha256()
      with target.open('rb') as existing:
       for chunk in iter(lambda:existing.read(1024*1024),b''):h.update(chunk)
      if h.hexdigest()!=actual:raise ValueError('目标文件冲突，未覆盖')
     else:
      try:os.link(temp,target)
      except FileExistsError:
       if hashlib.sha256(target.read_bytes()).hexdigest()!=actual:raise ValueError('目标文件冲突，未覆盖')
     record['sha256']=actual;record['captureId']=capture_id
     sidecar=target.with_suffix(target.suffix+'.json');pending=staging/(secrets.token_hex(12)+'.json')
     with pending.open('w') as f:
      json.dump(record,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
     os.replace(pending,sidecar)
    else:os.replace(temp,target)
   finally:
    if temp.exists():temp.unlink()
   self.reply(200,{'filename':target.name,'bytes':length,'sha256':actual,'captureId':capture_id})
  def upstream(self,path,data):
   conn=http.client.HTTPConnection('127.0.0.1',upstream_port,timeout=300)
   try:
    conn.request('POST',path,json.dumps(data).encode(),{'Host':'127.0.0.1:%d'%upstream_port,'Origin':'http://127.0.0.1:%d'%upstream_port,'X-Local-Token':local_token,'X-Lesson-Device':'iPhone','Content-Type':'application/json'})
    response=conn.getresponse();out=json.loads(response.read() or b'{}')
   finally:conn.close()
   if response.status!=200:raise ValueError(out.get('error','Mac 没有处理成功'))
   return out
  def sheet(self):
   """手机拍的签课表：交给 Mac 识别（存进 已签扫描件、识别、放进待核对），回给手机一张精简的核对单。"""
   length=int(self.headers.get('Content-Length','0'))
   if not 1000<length<=30*1024*1024:raise ValueError('照片太小或超过 30MB')
   name=Path(unquote(self.headers.get('X-Filename',''))).name or '手机拍照.jpg'
   self.connection.settimeout(180);body=self.rfile.read(length)
   if len(body)!=length:raise ValueError('上传中断，请重拍')
   out=self.upstream('/api/sheets/upload',{'filename':name,'data':base64.b64encode(body).decode()})
   sheets=[{'reviewId':x['reviewId'],'week':x['week'],'sheetId':x['sheetId'],
            'rows':[{'id':r['entry']['id'],'date':r['entry']['date'],'day':r['entry']['day'],'time':r['entry']['time'],'name':r['entry']['name'],'units':r['entry'].get('units',1),
                     'status':r['status'],'reason':r['reason'],'image':r['image'],'leaveImage':r.get('leaveImage',''),'booked':r['booked']} for r in x['rows']]} for x in out['sheets']]
   self.reply(200,{'sheets':sheets,'skipped':len(out['skipped'])})
  def paper(self):
   """老课表存档：手机拍的照片直接放进 数据/纸质课表/待归档，在 Mac 课时管理里看图选学生归档。"""
   length=int(self.headers.get('Content-Length','0'))
   if not 1000<length<=30*1024*1024:raise ValueError('照片太小或超过 30MB')
   name=Path(unquote(self.headers.get('X-Filename',''))).name or '老课表.jpg'
   if Path(name).suffix.lower() not in ('.jpg','.jpeg','.png','.heic'):raise ValueError('请上传照片')
   self.connection.settimeout(180);body=self.rfile.read(length)
   if len(body)!=length:raise ValueError('上传中断，请重拍')
   from 纸质课表 import keep
   self.reply(200,{'file':keep(root,body,name)})
  def sheet_commit(self):
   """手机上核对完的签课表入账：只转交 reviewId 和每行的决定，规则和 Mac 上一样（重复提交不会重复扣）。"""
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=65536:raise ValueError('提交内容无效')
   data=json.loads(self.rfile.read(length))
   if not re.fullmatch(r'[0-9a-f]{64}',str(data.get('reviewId',''))) or not isinstance(data.get('decisions'),dict):raise ValueError('提交内容无效')
   out=self.upstream('/api/sheets/commit',{'reviewId':data['reviewId'],'decisions':data['decisions']})
   self.reply(200,{k:out[k] for k in ('saved','skipped','pending')})
  def leave(self,target='/api/leave/set'):
   """手机课表上按住学生名字：标请假 / 取消（/mobile/leave，只是标记），或记“上课了”（/mobile/attend，直接扣课时，编号和签课表那行一样不会重复扣）。
   只转交 周、课程、学生、开关，标成“手机”做的。"""
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=4096:raise ValueError('提交内容无效')
   data=json.loads(self.rfile.read(length))
   if not all(isinstance(data.get(k),str) for k in ('week','course','student')):raise ValueError('提交内容无效')
   self.upstream(target,{'week':data['week'],'course':data['course'],'student':data['student'],'on':bool(data.get('on')),'by':'手机'})
   self.reply(200,{'ok':True})
  # ---- 手机网页版（10-23）：/m 页面、/m/data 课表、/m/act 记上课/请假/打点（一次可交好几条，没网时排的队）
  WEB_FILES={'/m':('手机网页.html','text/html; charset=utf-8'),'/m/':('手机网页.html','text/html; charset=utf-8'),'/m/sw.js':('手机网页sw.js','application/javascript; charset=utf-8')}
  def web_auth(self):
   cookie=SimpleCookie()
   try:cookie.load(self.headers.get('Cookie',''))
   except Exception:pass
   value=self.headers.get('Authorization','').removeprefix('Bearer ').strip() or (cookie['lesson_web'].value if 'lesson_web' in cookie else '')
   if not value:return False
   from 设备配对 import device_role
   return device_role(root,value)=='read-upload'
  def raw_reply(self,code,raw,kind,extra=()):
   self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
   for k,v in extra:self.send_header(k,v)
   self.end_headers();self.wfile.write(raw)
  def web_paired(self,token,location=None):
   cookie='lesson_web=%s; Path=/; Max-Age=94608000; Secure; HttpOnly; SameSite=Strict'%token
   if location:
    self.send_response(302);self.send_header('Set-Cookie',cookie);self.send_header('Location',location);self.send_header('Content-Length','0');self.end_headers();return
   self.raw_reply(200,json.dumps({'ok':True,'token':token}).encode(),'application/json',[('Set-Cookie',cookie)])
  def web(self):
   parsed=urlparse(self.path);p=parsed.path
   if self.command=='GET' and p in self.WEB_FILES:
    name,kind=self.WEB_FILES[p];f=root/'网页'/name
    extra=[('Service-Worker-Allowed','/m')] if p=='/m/sw.js' else []
    self.raw_reply(200,f.read_bytes(),kind,extra);return
   if self.command=='GET' and p=='/m/manifest.json':
    # 10-23：主屏幕上的网页有时会被 iPhone 清掉本地存的令牌，每次都要输 6 位数。连上以后页面换成带 ?k=令牌 的清单，
    # 添加到主屏幕时起始网址就带着令牌，每次打开都自己带上，不靠手机记。令牌不对就不带。
    from 设备配对 import device_role
    k=parse_qs(parsed.query).get('k',[''])[0]
    start='/m?k='+quote(k) if k and len(k)<100 and device_role(root,k)=='read-upload' else '/m'
    self.raw_reply(200,json.dumps({'name':'课达','short_name':'课达','start_url':start,'scope':'/m','display':'standalone','background_color':'#f6f7fa','theme_color':'#f6f7fa',
     'icons':[{'src':'/m/icon.png','sizes':'180x180','type':'image/png'}]},ensure_ascii=False).encode(),'application/manifest+json');return
   if self.command=='GET' and p=='/m/icon.png':
    f=root/'网页'/'手机网页图标.png'
    if f.is_file():self.raw_reply(200,f.read_bytes(),'image/png');return
    self.reply(404,{'error':'没有图标'});return
   if self.command=='GET' and p=='/m/cert':   # 证书机构：iPhone 装一次，网页才是“受信任”的
    self.raw_reply(200,(data_dir(root)/'手机连接'/'证书机构.pem').read_bytes(),'application/x-x509-ca-cert',[('Content-Disposition','attachment; filename="Coda-Mac.cer"')]);return
   if self.command=='GET' and p=='/m/join':   # 相机扫 Mac 上的二维码进来
    from 设备配对 import claim
    try:out=claim(root,{'code':parse_qs(parsed.query).get('code',[''])[0],'name':'手机网页版'})
    except ValueError:self.send_response(302);self.send_header('Location','/m#expired');self.send_header('Content-Length','0');self.end_headers();return
    self.web_paired(out['token'],'/m#t='+out['token']);return
   origin=self.headers.get('Origin')
   if self.command=='POST' and origin and origin!='https://'+self.headers.get('Host',''):self.reply(403,{'error':'来源不符'});return
   if self.command=='POST' and p=='/m/pair':   # 添加到主屏幕后：输入 Mac 上的 6 位数
    from 设备配对 import claim_pin
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=1024:raise ValueError('请求无效')
    out=claim_pin(root,str(json.loads(self.rfile.read(length)).get('pin','')).strip(),'手机网页版')
    self.web_paired(out['token']);return
   if not self.web_auth():self.reply(401,{'error':'这台手机还没连上 Mac'});return
   if self.command=='GET' and p=='/m/data':
    conn=http.client.HTTPConnection('127.0.0.1',upstream_port,timeout=30)
    try:
     conn.request('GET','/api/mobile/week',None,{'Host':'127.0.0.1:%d'%upstream_port});r=conn.getresponse();raw=r.read()
    finally:conn.close()
    self.raw_reply(r.status,raw,'application/json');return
   if self.command=='POST' and p=='/m/act':
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=200000:raise ValueError('请求无效')
    items=json.loads(self.rfile.read(length)).get('items')
    if not isinstance(items,list) or len(items)>200:raise ValueError('请求无效')
    self.reply(200,{'results':[self.web_act(x) for x in items]});return
   self.reply(404,{'error':'未知请求'})
  def web_act(self,x):
   """一条手机上的操作 → Mac。成功、已经记过（重交）都算交上了；别的错误原样告诉手机，让老师看着办。"""
   x=x if isinstance(x,dict) else {};xid=str(x.get('id',''))[:64];kind=x.get('kind')
   try:
    if kind in ('leave','attend'):
     if not all(isinstance(x.get(k),str) for k in ('week','course','student')):raise ValueError('内容不全')
     self.upstream('/api/leave/set' if kind=='leave' else '/api/attend',{'week':x['week'],'course':x['course'],'student':x['student'],'on':bool(x.get('on',True)),'by':'手机'})
    elif kind=='mark':
     self.upstream('/api/marks/save',{k:x.get(k) for k in ('id','students','course','week','start','end','remove')}|{'by':'手机'})
    else:raise ValueError('不认识的操作')
    return {'id':xid,'ok':True}
   except ValueError as e:
    msg=str(e)
    if kind=='attend' and '已经记过上课' in msg:return {'id':xid,'ok':True,'note':'Mac 上已经记过了'}
    return {'id':xid,'ok':False,'error':msg}
  # ---- 其他电脑
  DESK_PAGE="""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>连接这台 Mac</title>
<body style="margin:0;font:16px -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#f6f7fa;color:#223047;display:flex;align-items:center;justify-content:center;min-height:100vh">
<div style="background:#fff;border:1px solid #e5e9ef;border-radius:18px;padding:34px 40px;max-width:440px;text-align:center">
<h2 style="margin:0 0 10px">连接课程管理（Mac）</h2><p id="t" style="color:#68788d;line-height:1.8">正在申请…</p>
<div id="c" style="font-size:44px;font-weight:700;letter-spacing:8px;margin:14px 0"></div>
<p style="color:#8190a4;font-size:14px;line-height:1.8">请在那台 Mac 的“服务管理”里点<b>允许</b>（核对上面的代码）。<br>允许后这台电脑以后打开就直接进入。</p></div>
<script>
async function go(){
 try{const r=await (await fetch('/desk/request',{method:'POST'})).json();if(r.error)throw new Error(r.error);
  document.getElementById('c').textContent=r.code;document.getElementById('t').textContent='等待 Mac 允许…';
  for(;;){await new Promise(x=>setTimeout(x,2000));const s=await (await fetch('/desk/status?rid='+encodeURIComponent(r.rid),{cache:'no-store'})).json();
   if(s.status==='approved'){location.href='/';return}
   if(s.status==='denied'){document.getElementById('t').textContent='Mac 那边拒绝了。';return}
   if(s.status==='expired'){document.getElementById('t').textContent='等太久已过期，请刷新这个页面重新申请。';return}}
 }catch(e){document.getElementById('t').textContent='申请失败：'+e.message}
}
go();
</script>"""
  # 只能看的电脑可以用的 POST（只读）；这些按钮只在 Mac 本机才有意义（打开 Finder、放剪贴板）
  DESK_READ_POSTS={'/api/sheets/review','/api/camera/scan'}
  DESK_MAC_ONLY={'/api/inbox/open','/api/archive/open','/api/works/open','/api/inbox/copyfiles','/api/works/copy','/device-pair','/api/desk','/api/desk/decide','/api/desk/revoke'}  # 允许/取消设备也只能在 Mac 本机做
  def desk_role(self):
   cookie=SimpleCookie()
   try:cookie.load(self.headers.get('Cookie',''))
   except Exception:return None
   if 'lesson_desk' not in cookie:return None
   from 设备配对 import device_role
   role=device_role(root,cookie['lesson_desk'].value)
   return role if role and role.startswith('desk-') else None
  def desk(self,parsed):
   from 设备配对 import desk_request,desk_status
   if parsed.path=='/desk' and self.command=='GET':
    if self.desk_role():self.send_response(302);self.send_header('Location','/');self.send_header('Content-Length','0');self.end_headers();return
    raw=self.DESK_PAGE.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
   if parsed.path=='/desk/request' and self.command=='POST':
    ua=self.headers.get('User-Agent','')
    os_name='Mac' if 'Macintosh' in ua else 'Windows' if 'Windows' in ua else 'iPad' if 'iPad' in ua else 'Android' if 'Android' in ua else '电脑'
    browser='Edge' if 'Edg/' in ua else 'Chrome' if 'Chrome/' in ua else 'Safari' if 'Safari/' in ua else 'Firefox' if 'Firefox/' in ua else '浏览器'
    self.reply(200,desk_request(root,'%s · %s · %s'%(os_name,browser,self.client_address[0])));return
   if parsed.path=='/desk/status' and self.command=='GET':
    out=desk_status(root,parse_qs(parsed.query).get('rid',[''])[0])
    if out.get('status')=='approved':
     raw=json.dumps({'status':'approved'}).encode();self.send_response(200);self.send_header('Content-Type','application/json')
     self.send_header('Set-Cookie','lesson_desk=%s; Path=/; Max-Age=31536000; Secure; HttpOnly; SameSite=Lax'%out['token'])
     self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
    self.reply(200,out);return
   self.reply(404,{'error':'未知请求'})
  def desk_proxy(self,role):
   """把整套 Mac 网页转给已允许的电脑（边收边发，视频可以拖进度）。只能看的电脑不能改东西。"""
   path=urlparse(self.path).path
   if path in self.DESK_MAC_ONLY:self.reply(403,{'error':'这个按钮只在 Mac 本机上有用（会在 Mac 上打开 Finder 或放剪贴板）'});return
   if self.command=='POST' and role=='desk-view' and path not in self.DESK_READ_POSTS:self.reply(403,{'error':'这台电脑只能看，不能改。要改请在 Mac 上把它设成“能改”'});return
   if self.command not in ('GET','POST','HEAD'):self.reply(405,{'error':'不支持'});return
   length=int(self.headers.get('Content-Length','0') or 0)
   if length<0 or length>60*1024*1024:raise ValueError('请求过大')
   body=self.rfile.read(length) if length else None
   headers={'Host':'127.0.0.1:%d'%upstream_port,'X-Local-Token':local_token,'Origin':'http://127.0.0.1:%d'%upstream_port}
   for h in ('Content-Type','Range','Accept'):
    if self.headers.get(h):headers[h]=self.headers.get(h)
   conn=http.client.HTTPConnection('127.0.0.1',upstream_port,timeout=300)
   try:
    conn.request(self.command,self.path,body,headers);resp=conn.getresponse()
    self.send_response(resp.status)
    for h in ('Content-Type','Content-Length','Content-Range','Accept-Ranges','Location','Cache-Control'):
     v=resp.getheader(h)
     if v:self.send_header(h,v)
    self.end_headers()
    if self.command!='HEAD':
     while chunk:=resp.read(1024*1024):self.wfile.write(chunk)
   finally:conn.close()
  def media(self,parsed):
   identifier=parse_qs(parsed.query).get('id',[''])[0]
   index=root/'课堂视频'/'视频索引.json'
   state=json.loads(index.read_text());item=next((x for x in state.get('items',[]) if x['id']==identifier),None)
   if not item:raise ValueError('影像不存在')
   base=home/'上课视频归档' if item.get('archived') else root/'课堂视频'
   path=(base/item['file']).resolve()
   if base.resolve() not in path.parents or not path.is_file():raise ValueError('影像文件不存在')
   size=path.stat().st_size;start,end=0,size-1;status=200
   request_range=self.headers.get('Range','')
   if request_range:
    match=re.fullmatch(r'bytes=(\d+)-(\d*)',request_range)
    if not match:self.send_error(416);return
    start=int(match[1]);end=min(int(match[2]) if match[2] else end,end);status=206
    if start>end:self.send_error(416);return
   self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('X-Filename',quote(path.name));self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-store')
   if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
   self.end_headers()
   with path.open('rb') as f:
    f.seek(start);left=end-start+1
    while left:
     chunk=f.read(min(left,1024*1024))
     if not chunk:break
     self.wfile.write(chunk);left-=len(chunk)
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(cert,key)
 import 网页证书
 web_cert,web_key,_=网页证书.ensure(root)
 web_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);web_context.minimum_version=ssl.TLSVersion.TLSv1_2;web_context.load_cert_chain(web_cert,web_key)
 def lan_bind():
  """手机在同一个 Wi-Fi 里连这台电脑，所以听局域网；手机要先配对才能用。设 LESSON_BIND=127.0.0.1 可以只留本机。"""
  return os.environ.get('LESSON_BIND') or '0.0.0.0'
 class DualServer(ThreadingHTTPServer):
  # 别的电脑在浏览器里只打 IP:18766（没写 https://）时，浏览器会用 http 连过来，以前就“打不开”。
  # 现在同一个端口先看第一个字节：是加密连接就照常走 https；不是就告诉浏览器改去 https://这台Mac:18766/desk（10-18 用户）
  def get_request(self):
   conn,addr=self.socket.accept();conn.settimeout(10)
   try:first=conn.recv(1,__import__('socket').MSG_PEEK)
   except Exception:conn.close();raise OSError('连接没发数据')
   if first!=b'\x16':
    try:
     conn.recv(8192);host=conn.getsockname()[0]
     conn.sendall(('HTTP/1.1 301 Moved Permanently\r\nLocation: https://%s:%d%s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'%(host,self.server_address[1],'/m' if self.web else '/desk')).encode())
    finally:conn.close()
    raise OSError('已改去 https')
   tls=self.tls.wrap_socket(conn,server_side=True);tls.settimeout(None)
   return tls,addr
 server=DualServer((lan_bind(),port),Gateway);server.tls=context;server.web=False
 threading.Thread(target=server.serve_forever,daemon=True).start()
 web=DualServer((lan_bind(),port+1),Gateway);web.tls=web_context;web.web=True   # 手机网页版：18767
 threading.Thread(target=web.serve_forever,daemon=True).start()
 return server
