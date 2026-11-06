"""Short-lived single-use pairing invitations; paired devices can read and upload only."""
import base64,hashlib,json,secrets,subprocess,threading,time,re,ipaddress,struct,zlib
from 存取公共 import data_dir
from pathlib import Path
LOCK=threading.RLock()
INVITES={}
ACTIVE_DEVICES={}
def _folder(root):return data_dir(root)/'手机连接'
def _read(root):
 p=_folder(root)/'设备.json'
 return json.loads(p.read_text()) if p.exists() else {'serverId':secrets.token_hex(16),'devices':[]}
def _write(root,value):
 p=_folder(root)/'设备.json';p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False));tmp.chmod(0o600);tmp.replace(p)
def device_role(root,token):
 with LOCK:
  for d in _read(root)['devices']:
   if secrets.compare_digest(d['token'],token):
    ACTIVE_DEVICES[(str(Path(root).resolve()),d['id'])]={'name':d.get('name','iPhone'),'seen':time.monotonic()}
    return d['role']
 return None
def connected_devices(root):
 with LOCK:
  root_key=str(Path(root).resolve())
  return [d['name'] for (folder,_),d in ACTIVE_DEVICES.items() if folder==root_key and time.monotonic()-d['seen']<45]
def paired_devices(root):
 with LOCK:return [{'id':d.get('id'),'name':d.get('name','iPhone'),'role':d.get('role',''),'created':d.get('created')} for d in _read(root)['devices']]
# ---- 局域网里的其他电脑（浏览器）：在那台电脑打开 https://Mac:18766/desk → 显示代码等 Mac 允许 → Mac 上点“允许·能改 / 允许·只能看”
DESK={}  # 请求编号 → {code, name, created, status: waiting/approved/denied, token}
def desk_request(root,name):
 with LOCK:
  now=time.time()
  for k in [k for k,v in DESK.items() if now-v['created']>600]:del DESK[k]
  if sum(1 for v in DESK.values() if v['status']=='waiting')>=5:raise ValueError('等待允许的电脑太多了，请稍后再试')
  rid=secrets.token_urlsafe(18);code='%06d'%secrets.randbelow(1000000)
  DESK[rid]={'code':code,'name':str(name or '电脑')[:60],'created':now,'status':'waiting','root':str(Path(root).resolve())}
  return {'rid':rid,'code':code}
def desk_status(root,rid):
 """那台电脑轮询：批准后把令牌交给它一次（交出后就从等待表里删掉）。"""
 with LOCK:
  r=DESK.get(str(rid))
  if not r or r['root']!=str(Path(root).resolve()):return {'status':'expired'}
  if r['status']=='approved':
   token=r['token'];del DESK[str(rid)];return {'status':'approved','token':token}
  return {'status':r['status']}
def desk_pending(root):
 with LOCK:
  key=str(Path(root).resolve())
  return [{'rid':k,'code':v['code'],'name':v['name'],'created':int(v['created'])} for k,v in DESK.items() if v['root']==key and v['status']=='waiting' and time.time()-v['created']<600]
def desk_decide(root,data):
 """Mac 上决定：full＝允许·能改，view＝允许·只能看，deny＝拒绝。"""
 rid,decision=str((data or {}).get('rid','')),(data or {}).get('decision')
 if decision not in ('full','view','deny'):raise ValueError('请求无效')
 with LOCK:
  r=DESK.get(rid)
  if not r or r['status']!='waiting':raise ValueError('这个请求已经过期，请那台电脑重新打开')
  if decision=='deny':r['status']='denied';return {'ok':True}
  state=_read(root);token=secrets.token_urlsafe(32)
  state['devices'].append({'id':secrets.token_hex(12),'name':r['name'],'token':token,'role':'desk-'+decision,'created':int(time.time())})
  _write(root,state);r['status']='approved';r['token']=token
  return {'ok':True}
def revoke(root,data):
 """取消一台已允许的设备（手机或电脑），它以后要重新配对。"""
 did=str((data or {}).get('id',''))
 with LOCK:
  state=_read(root);before=len(state['devices'])
  state['devices']=[d for d in state['devices'] if d.get('id')!=did]
  if len(state['devices'])==before:raise ValueError('找不到这台设备')
  _write(root,state)
  for k in [k for k in ACTIVE_DEVICES if k[1]==did]:del ACTIVE_DEVICES[k]
 return {'ok':True}
def lan_ip():
 for command in [['/usr/sbin/ipconfig','getifaddr','en0'],['/sbin/ifconfig','en0']]:
  try:
   output=subprocess.check_output(command,text=True,stderr=subprocess.DEVNULL)
   for candidate in re.findall(r'(?:^|\binet\s+)(\d+\.\d+\.\d+\.\d+)',output):
    address=ipaddress.ip_address(candidate)
    if not address.is_loopback and not address.is_unspecified:return candidate
  except (subprocess.CalledProcessError,ValueError,OSError):pass
 import 跨平台;return 跨平台.lan_ip()
def invitation(root):
 with LOCK:
  root=Path(root)
  if not (data_dir(root)/'账本.json').is_file():
   for name in ['基础排课.json','学生名单.json']:
    value=json.loads((data_dir(root)/name).read_text()) if (data_dir(root)/name).is_file() else None
    if not isinstance(value,list) or not value:raise ValueError('未找到可读取的课程资料，不能生成配对码。')
  from 手机网关 import configuration
  config,_,_=configuration(root)
  state=_read(root);_write(root,state)
  code=secrets.token_urlsafe(24)
  now=time.time()
  for key in list(INVITES):
   if INVITES[key]['expires']<now:del INVITES[key]
  INVITES[code]={'root':str(root.resolve()),'expires':now+300,'serverId':state['serverId']}
  ip=lan_ip()
  return {'version':1,'kind':'lesson-pair','host':config['host'],'fallbackHost':ip,'port':config['port'],'fingerprint':config['fingerprint'],'code':code,'serverId':state['serverId'],'expires':int(now+300)}
def claim(root,data):
 with LOCK:
  code=str(data.get('code',''));invite=INVITES.get(code)
  if not invite or invite['expires']<time.time() or invite['root']!=str(Path(root).resolve()):raise ValueError('二维码已过期或已使用，请在 Mac 重新生成。')
  state=_read(root);token=secrets.token_urlsafe(32)
  state['devices'].append({'id':secrets.token_hex(12),'name':str(data.get('name','iPhone'))[:80],'token':token,'role':'read-upload','created':int(time.time())})
  _write(root,state);del INVITES[code]
  return {'token':token,'serverId':state['serverId'],'role':'read-upload'}
# ---- 手机网页版（10-23）：相机扫二维码直接打开；添加到主屏幕后的网页和 Safari 不共用登录，所以另给一个 6 位数，在网页里输入也能连上
WRONG=[]   # 输错 6 位数的时间：5 分钟里错 20 次就暂时都不认，防乱试
def web_pin(root,code):
 with LOCK:
  pins={v.get('pin') for v in INVITES.values()};pin='%06d'%secrets.randbelow(1000000)
  while pin in pins:pin='%06d'%secrets.randbelow(1000000)
  INVITES[code]['pin']=pin;return pin
def claim_pin(root,pin,name):
 with LOCK:
  now=time.time();WRONG[:]=[t for t in WRONG if now-t<300]
  if len(WRONG)>=20:raise ValueError('输错太多次了，等 5 分钟再试')
  code=next((k for k,v in INVITES.items() if v.get('pin')==str(pin) and v['expires']>=now and v['root']==str(Path(root).resolve())),None)
  if not code:WRONG.append(now);raise ValueError('这个数字不对或已过期，请在 Mac 上重新生成')
  return claim(root,{'code':code,'name':name})
def qr_png(text):
 from qrcodegen import QrCode
 code=QrCode.encode_text(text,QrCode.Ecc.MEDIUM)
 scale,border=7,4
 size=(code.get_size()+border*2)*scale
 raw=bytearray()
 for y in range(size):
  raw.append(0)
  for x in range(size):
   raw.append(0 if code.get_module(x//scale-border,y//scale-border) else 255)
 def chunk(kind,data):
  return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
def page(root,program):
 payload=invitation(root)
 png=qr_png(json.dumps(payload))
 return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>连接设备</title><body style="font-family:system-ui;text-align:center;padding:40px;background:#f6f7fa"><h1>连接设备</h1><p>手机左滑，点“扫码连接 Mac”扫描此码</p><img alt="配对二维码" style="width:320px;max-width:90%;border:20px solid white" src="data:image/png;base64,'+base64.b64encode(png).decode()+'"><p>二维码五分钟有效，仅可使用一次。</p><p>连接后可查看课表、上传资料、核对签课表入账；其他账目不能改。</p><button onclick="history.back()">返回课表</button> <button onclick="location.reload()">重新生成</button></body>').encode()
