"""课程连接服务：Mac 网页（课程管理、课时管理、服务管理、作品管理）+ 手机配对通道。手机只能读课表、上传资料，不能改任何数据。
结构（10-20 整理）：
- 启动时定好 ROOT / DATA / PAGE_DIR / 端口 / 是不是测试版（LITE）；
- GETS、POSTS 两张表：路径 → 处理函数；do_GET / do_POST 只负责查表、鉴权、把结果发出去；
- 所有读写都交给各个模块（课表存取、账本存取、签课表 ……），这个文件不碰资料文件的细节。"""
import sys as _sys,os as _os;_sys.path.insert(0,_os.path.dirname(_os.path.abspath(__file__)))  # Windows 自带的精简 Python 不会自动把本文件夹加进去
import datetime,html,json,re,os,subprocess,traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs,unquote
import 存取公共,操作日志,打点,课包,补记录,课表存取,账本存取,周调整存取,收件箱,签课表,纸质课表,学生状态,请假标记,相机导入,素材编辑,学生档案
from 设备配对 import page,connected_devices,lan_ip,paired_devices,desk_pending,desk_decide,revoke
from 手机网关 import start
STARTED=datetime.datetime.now().astimezone()
PORT=int(os.environ.get('LESSON_PORT','18765'));PHONE_PORT=int(os.environ.get('LESSON_PHONE_PORT','18766'))  # 测试时用别的端口，不动正在用的服务
PROGRAM=Path(__file__).resolve().parent
# 根目录：自己这套是 根目录/数据/程序/；v0.7 起的测试版是 软件文件（不用动）/程序/（资料在旁边的 我的资料/，页面在 网页/）
ROOT=Path(os.environ.get('LESSON_ROOT',str(PROGRAM.parent.parent if PROGRAM.parent.name=='数据' else PROGRAM.parent)))
DATA=存取公共.data_dir(ROOT)
PAGE_DIR=ROOT/'网页' if (ROOT/'网页').is_dir() else DATA/'页面'
# 测试版（给别的老师用）：资料里有 发行版.json 就是。只开课程管理、课时管理，不开手机通道、不转语音，端口用它写的（不和自己用的那套撞）
LITE_FILE=DATA/'发行版.json'
LITE=json.loads(LITE_FILE.read_text(encoding='utf-8')) if LITE_FILE.is_file() else None
if LITE and 'LESSON_PORT' not in os.environ:PORT=int(LITE.get('port',18775))
if LITE:存取公共.PRUNE=True
LOCAL='127.0.0.1:%d'%PORT
HTML='text/html; charset=utf-8'
# 中文 / English：存在 资料/界面设置.json，还决定按北京时间还是电脑时区算日期（存取公共.set_lang）
LANG_FILE=DATA/'界面设置.json'
def saved_lang():
 try:return json.loads(LANG_FILE.read_text(encoding='utf-8')).get('lang')
 except Exception:return None
存取公共.set_lang(saved_lang() or 'zh')
def set_lang(b):
 lang=(b or {}).get('lang')
 if lang not in ('zh','en'):raise ValueError('语言不对')
 存取公共.write_json(LANG_FILE,{'lang':lang});存取公共.set_lang(lang);return {'ok':True,'lang':lang}
TOKEN_FILE=DATA/'手机连接'/'本机口令.txt'
if not TOKEN_FILE.is_file():
 import secrets;TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True);TOKEN_FILE.write_text(secrets.token_urlsafe(32));TOKEN_FILE.chmod(0o600)
TOKEN=TOKEN_FILE.read_text().strip()
def phone_page():
 # 手机显示从今天起 7 天实际要上的课（固定课表 + 临时安排）：每行 [星期, 时间, 名字, '', 老师, 扣几节, 双师, 隐藏, 变动(move/add/cancel/None), 日期, 课程编号, 周一日期, 标了请假的学生, 账本里已记的 {学生: lesson/leave}]
 roster=json.loads((DATA/'学生名单.json').read_text())
 today=存取公共.today();weeks={};leave={};schedule=[];dates=[]
 for i in range(7):
  d=today+datetime.timedelta(days=i);mon=周调整存取.monday(d);dayname=周调整存取.DAYS[d.weekday()];dates.append({'date':str(d),'day':dayname})
  if mon not in weeks:w=周调整存取.load(ROOT,str(mon));weeks[mon]=[(r,r.get('changed')) for r in w['effective']]+[(r,'cancel') for r in w['cancelled']];leave[mon]=(请假标记.of_week(ROOT,str(mon)),签课表.week_booked(ROOT,str(mon)))
  for r,changed in weeks[mon]:
   if r['day']==dayname:schedule.append([dayname,r['start']+'–'+r['end'],r['name'],'',r.get('teacher','blue'),r.get('units',1),r.get('dual'),False,changed,str(d),r['id'],str(mon),[] if changed=='cancel' else sorted(leave[mon][0].get(r['id'],{})),{} if changed=='cancel' else leave[mon][1].get(r['id'],{})])
 source=(PROGRAM/'手机页模板.html').read_text()
 css=source.split('<style>',1)[1].split('</style>',1)[0]
 functions=source[source.index('let phoneTeacher='):source.index('function paintStudentFlow')]
 payload=json.dumps({'schedule':schedule,'students':roster,'dates':dates},ensure_ascii=False).replace('<','\\u003c')
 js='const initial='+payload+''';const schedule=initial.schedule,students=initial.students,db={studentIds:{}};
 const $=id=>document.getElementById(id);
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function nativeMobile(action,payload={}){window.webkit?.messageHandlers?.lessonNative?.postMessage({action,...payload})}
 function names(r){return r[2].split('、')}
 function studentState(){return 'active'}
 function timeBounds(r){let m=r[1].match(/^(\\d{2}):(\\d{2})[–-](\\d{2}):(\\d{2})$/);return m?[+m[1]*60+ +m[2],+m[3]*60+ +m[4]]:null}
 function clock(t){return String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0')}
 '''+functions+'''
 const saveRenderedCache=cachePhoneSchedule;
 cachePhoneSchedule=function(){saveRenderedCache();nativeMobile('cacheSchedule',{html:'<!doctype html>'+document.documentElement.outerHTML})};
 renderPhoneSchedule();
 if(location.protocol==='https:'){setInterval(()=>{fetch('/state',{method:'POST',credentials:'include',cache:'no-store'}).catch(()=>{})},15000)}'''
 return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+css+'</style><main><header></header><nav></nav><div><button id="editdevice"></button></div><section id="view"></section><footer id="foot"></footer></main><script>'+js+'</script>').encode()
def mobile_week():
 """手机网页版（10-23）：昨天起 8 天实际要上的课（固定课表 + 临时安排），每节课带上请假标记、账本里已记的、这几天的打点。"""
 today=存取公共.today();weeks={};rows=[];days=[]
 for i in range(-1,7):
  d=today+datetime.timedelta(days=i);mon=str(周调整存取.monday(d));dayname=周调整存取.DAYS[d.weekday()];days.append({'date':str(d),'day':dayname})
  if mon not in weeks:
   w=周调整存取.load(ROOT,mon)
   weeks[mon]=([(r,r.get('changed')) for r in w['effective']]+[(r,'cancel') for r in w['cancelled']],请假标记.of_week(ROOT,mon),签课表.week_booked(ROOT,mon))
  lessons,leave,booked=weeks[mon]
  for r,changed in lessons:
   if r['day']!=dayname:continue
   cancel=changed=='cancel'
   rows.append({'date':str(d),'day':dayname,'start':r['start'],'end':r['end'],'students':r['studentNames'],'teacher':r.get('teacher','blue'),'dual':r.get('dual'),
    'units':r.get('units',1),'changed':changed,'course':r['id'],'week':mon,'leave':[] if cancel else sorted(leave.get(r['id'],{})),'booked':{} if cancel else booked.get(r['id'],{})})
 rows.sort(key=lambda r:(r['date'],r['start']))
 lt=(LITE or {}).get('teachers') or {}
 return {'today':str(today),'days':days,'rows':rows,'teachers':{'red':lt.get('red') or '红老师','blue':lt.get('blue') or '蓝老师'},
  'marks':打点.listing(ROOT,str(today-datetime.timedelta(days=1))),'fetchedAt':存取公共.now_aware().isoformat(timespec='seconds'),
  'tz':int(存取公共.now_aware().utcoffset().total_seconds()//60)}   # 中文按北京时间算“今天”：手机按这个时区判断今天、明天
def web_pair():
 """服务管理“连接手机网页版”：一个一次性的二维码（相机扫了直接在 Safari 打开并记住这台手机）+ 证书下载地址。"""
 import 网页证书,base64
 from 设备配对 import invitation,qr_png
 from 设备配对 import web_pin
 code=invitation(ROOT)['code'];base=网页证书.urls(ROOT,PHONE_PORT+1)
 url=base[0]+'/m/join?code='+code
 return {'pin':web_pin(ROOT,code),'url':url,'qr':'data:image/png;base64,'+base64.b64encode(qr_png(url)).decode(),'cert':[u+'/m/cert' for u in base],'expires':300}
# ---- 页面：路径 → (文件, 导航里哪个亮)
PAGES={'/':('课程管理.html','course'),'/lesson':('课时管理.html','lesson'),'/service':('服务管理.html','service'),'/works':('作品管理.html','works'),'/log':('操作日志.html','log')}
if LITE:PAGES={'/':PAGES['/'],'/lesson':PAGES['/lesson'],'/service':PAGES['/service'],'/setup':('设置向导.html','setup'),'/log':PAGES['/log']}
REDIRECTS={'/ledger':'/lesson','/adjust':'/'}  # 以前的网址，书签里可能还有
ASSETS=('签课表识别.js','pdf.min.js','pdf.worker.min.js','i18n.js','操作日志.js')  # 页面用的脚本，只给这几个
# 测试版只开放课程管理、课时管理用得到的接口；手机通道、服务管理、作品、相机这些一律 404
LITE_GET=('/api/inbox','/api/service','/api/camera','/api/desk','/api/marks','/api/mobile','/api/log','/api/packages','/api/gaps','/api/adjust','/api/ledger','/api/sheets','/api/sign','/api/paper')
LITE_POST={'/api/inbox/status','/api/inbox/stage','/api/inbox/open','/api/inbox/copyfiles','/api/inbox/prepare','/api/inbox/edit','/api/inbox/reassign','/api/inbox/card','/api/inbox/text','/api/inbox/missing','/api/archive/sent','/api/archive/trashcut','/api/archive/open','/api/desk/decide','/api/desk/revoke','/api/camera/scan','/api/camera/import','/api/marks/save','/state','/editing/status','/api/sheets/archive','/api/sheets/rename','/api/log/reason','/api/sheets/topaper','/api/packages/save','/api/packages/sync','/api/student/rename','/api/lang','/api/gaps/resolve','/api/gaps/restart','/api/student/merge','/api/paper/restore','/api/student/remove','/api/student/enroll','/schedule/save','/api/adjust/save','/api/leave/set','/api/attend','/api/ledger/add','/api/ledger/batch','/api/ledger/void','/api/student/pause','/api/sheets/generate','/api/sheets/upload','/api/sheets/stash','/api/sheets/scanned','/api/sheets/review','/api/sheets/commit','/api/paper/file','/api/setup'}
def lite_blocked(path,post=False):
 if not LITE:return False
 if post:return path not in LITE_POST
 return path.startswith('/api/') and not any(path==p or path.startswith(p+'/') or path.startswith(p+'?') for p in LITE_GET)
def teacher_names(b):
 blue=str(b.get('blue','')).strip()[:12];red=str(b.get('red','')).strip()[:12]
 if not blue:raise ValueError('请至少写一位老师的名字')
 return {'blue':blue,'red':red}
def setup_save(b):
 """测试版第一次打开的设置向导：老师名字、学生名单（可带剩余课时）、要不要留示例。写好后以后打开就直接进课程管理。
 设置完以后只能改工作室名和老师名字（mode=names）；不能再整个重来，不然会把学生和账本清空。"""
 if not LITE:raise ValueError('只有试用版有设置向导')
 studio=str(b.get('studio','')).strip()[:30]
 if LITE.get('setupDone'):
  if b.get('mode')!='names':raise ValueError('已经设置过了，学生和课表请在课程管理、课时管理里改')
  LITE.update(teachers=teacher_names(b),studio=studio);存取公共.write_json(LITE_FILE,LITE)
  return {'ok':True}
 teachers=teacher_names(b);students=[];seen=set()
 for raw in b.get('students') or []:
  name=str(raw.get('name','')).strip()
  if not name:continue
  if re.search(r'[、,，|/\\]',name) or len(name)>12:raise ValueError('学生名字“%s”里不能有顿号、逗号、斜杠，最长 12 个字'%name)
  if re.search(r'\s',name) or name.isdigit():raise ValueError('“%s”不像学生名字（名字里不能有空格，也不能只是数字）'%name)
  if name in seen:continue
  seen.add(name);units=raw.get('units');students.append((name,int(units) if str(units).lstrip('-').isdigit() else None))
 keep=bool(b.get('keepSamples'))
 if not students and not keep:raise ValueError('请写至少一个学生，或者勾选“先留着示例学生”')
 load=lambda name,default:json.loads((DATA/name).read_text(encoding='utf-8')) if keep else default
 rows=load('基础排课.json',[]);roster=load('学生名单.json',[]);ledger=load('账本.json',{'version':1,'transactions':[]})
 if not teachers['red']:
  for r in rows:
   if r.get('teacher')=='red':r['teacher']='blue'
 roster+=[n for n,_ in students if n not in roster]
 today=str(存取公共.today());now=存取公共.now_aware().isoformat(timespec='seconds')
 for i,(n,u) in enumerate(students):
  if u is not None:ledger['transactions'].append({'id':'setup-%s-%d'%(today,i),'kind':'opening','student':n,'date':today,'note':'开始使用时剩余课时','delta':u,'createdAt':now})
 存取公共.write_json(DATA/'基础排课.json',rows);存取公共.write_json(DATA/'学生名单.json',roster);存取公共.write_json(DATA/'账本.json',ledger)
 LITE.update(teachers=teachers,studio=studio,setupDone=today);存取公共.write_json(LITE_FILE,LITE)
 return {'ok':True,'students':len(roster)}
NAV_CSS=('<style>'
 'body{margin:0;background:#f6f7fa;color:#223047;font:16px -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}'
 'main{max-width:1320px!important;margin:0 auto!important;padding:18px 24px 40px!important}'
 '.modnav{margin:0 0 16px}.modnav a{text-decoration:none}'
 '.modnav .mods{display:flex;gap:8px;flex-wrap:wrap;align-items:center}'
 '.modnav .mods a.tab{padding:9px 18px;border-radius:12px;background:#fff;border:1px solid #e5e9ef;font-size:15px;color:#275de0}'
 '.modnav .mods a.tab.on{background:#223047;color:#fff;border-color:#223047}'
 '.modnav .conn{margin-left:auto;font-size:13px;color:#68788d;padding:8px 12px;border:1px solid #e5e9ef;border-radius:10px;background:#fff}'
 '.modnav .conn.on{color:#2f8f5b}'
 '.modnav .logl{margin-left:auto;font-size:13px;color:#68788d;padding:8px 12px;border:1px solid #e5e9ef;border-radius:10px;background:#fff}.modnav .logl.on{background:#223047;color:#fff}.modnav .logl+.conn{margin-left:0}'
 '</style>')
NAV_JS=("<script>(function(){var c=document.getElementById('navconn');if(!c)return;"
 "function t(){fetch('/connection-status',{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){"
 "c.className='conn'+(d.devices.length?' on':'');c.textContent=d.devices.length?'● 手机已连接':'○ 手机未连接'}).catch(function(){c.textContent='服务不可用'})}"
 "t();setInterval(t,5000)})()</script>")
def nav(module):
 loglink='<a class="logl%s" href="/log" title="Mac 和手机上每一次改动">操作日志</a>'%(' on' if module=='log' else '')
 mods=''.join('<a class="tab%s" href="%s">%s</a>'%(' on' if key==module else '',href,name) for key,href,name in (('course','/','课程管理'),('lesson','/lesson','课时管理'),('service','/service','服务管理')) if not LITE or key in ('course','lesson','service'))
 if LITE:
  studio=LITE.get('studio')
  phone='<a class="conn" href="#" onclick="fetch(\'/open-uploads\');return false" title="手机 App 传来的随记，在访达里打开">手机上传</a><a class="conn" id="navconn" style="margin-left:0" href="/device-pair?key='+TOKEN+'" title="点这里出二维码，iPhone 上的 App 扫一下就连上">…</a>' if LITE.get('phone') else ''  # 开源版：连手机、看上传
  return NAV_CSS+'<script>window.LESSON_TEACHERS='+json.dumps((LITE.get('teachers') or {}),ensure_ascii=False).replace('<','\\u003c')+'</script><style>#connectionstatus,#connectdevice,#pairdialog{display:none!important}</style><div class="modnav"><div class="mods">'+mods+loglink+phone+'<a class="conn" style="margin-left:0" href="/setup" title="Coda 课达 开源版 v'+str(LITE.get('version',''))+'">'+('<span data-noi18n>'+html.escape(studio)+'</span> · ' if studio else '')+'设置</a></div></div>'+(NAV_JS if LITE.get('phone') else '')
 return NAV_CSS+'<div class="modnav"><div class="mods">'+mods+loglink+'<a class="conn" id="navconn" href="/service" title="手机连接情况">…</a></div></div>'+NAV_JS
def render_page(path):
 name,module=PAGES[path]
 out=(PAGE_DIR/name).read_bytes().replace(b'@@NAV@@',nav(module).encode()).replace(b'@@LOCAL_KEY@@',TOKEN.encode())
 if name in ('课程管理.html','课时管理.html','设置向导.html'):out=out.replace(b'</title>',b'</title><script>window.CODA_LANG='+json.dumps(saved_lang()).encode()+b';window.CODA_KEY='+json.dumps(TOKEN).encode()+b'</script><script src="/assets/i18n.js"></script>',1)  # 中文 / English 切换
 if __import__('os').name=='nt':  # Windows 上换掉只属于 Mac 的说法
  for a,b in (('⌘V','Ctrl+V'),('⌘Z','Ctrl+Z'),('在 Finder 显示','在文件夹中显示'),('在访达里打开','在文件夹里打开'),('废纸篓','回收站'),('这台 Mac','这台电脑'),('这台Mac','这台电脑'),('Mac 上','电脑上'),('Mac 剪贴板','电脑剪贴板'),('Mac 网页','电脑网页')):out=out.replace(a.encode(),b.encode())
 tag=b'<script>window.CODA_LOG_KEY='+json.dumps(TOKEN).encode()+b'</script><script src="/assets/%E6%93%8D%E4%BD%9C%E6%97%A5%E5%BF%97.js"></script>'
 out=out.replace(b'</body>',tag+b'</body>',1) if b'</body>' in out else out+tag  # 少见的改动后右下角问一句原因
 if LITE:
  out=out.replace('，手机刷新后可见'.encode(),b'')  # 测试版没有手机
  out=out.replace('“启动课程管理”'.encode(),'“Mac 点这里”（Windows 是“Windows 点这里”）'.encode())  # 测试版的启动文件叫这个
  if LITE.get('setupDone') and path=='/setup':  # 已经设置过：向导页变成“修改工作室名和老师”
   cfg={'studio':LITE.get('studio',''),**(LITE.get('teachers') or {})}
   out=out.replace(b'<main>',b'<script>window.CODA_DONE='+json.dumps(cfg,ensure_ascii=False).replace('<','\\u003c').encode()+b'</script><main>',1)
  icon=PROGRAM/'图标.svg'   # Coda 课达 Logo：浏览器标签上的小图标 + 右上角小标 + 设置向导标题上方的大图标
  if icon.is_file():
   import base64;uri=b'data:image/svg+xml;base64,'+base64.b64encode(icon.read_bytes())
   out=out.replace(b'<main>',b'<link rel="icon" href="'+uri+b'"><main>',1)
   k=out.find(b'<a class="conn" href="/setup" title="')
   if k>=0:e=out.find(b'>',k)+1;out=out[:e]+b'<img src="'+uri+b'" alt="" style="width:18px;height:18px;vertical-align:-4px;margin-right:7px">'+out[e:]
   out=out.replace('<h1>欢迎使用'.encode(),b'<img src="'+uri+b'" alt="" style="width:76px;height:76px;display:block;margin:0 0 18px">'+'<h1>欢迎使用'.encode(),1)
 return out
PROXY_APPS=('Shadowrocket','Surge','Clash','mihomo','sing-box','V2rayU','Stash','Quantumult','Tailscale','WireGuard','OpenVPN')
def network_check():
 """检测会干扰手机连接的代理 / VPN：默认路由被虚拟网卡（utun）接管，或正在运行代理软件。"""
 try:route=subprocess.run(['/sbin/route','-n','get','default'],capture_output=True,text=True,timeout=3).stdout
 except Exception:route=''
 found=re.search(r'interface:\s*(\S+)',route);iface=found[1] if found else None
 try:running=subprocess.run(['/bin/ps','-axo','comm'],capture_output=True,text=True,timeout=3).stdout
 except Exception:running=''
 apps=[name for name in PROXY_APPS if name.lower() in running.lower()]
 return {'defaultInterface':iface,'tunnel':bool(iface and iface.startswith('utun')),'apps':apps}
def service_info():
 backups=sorted((DATA/'备份').glob('*.json'),key=lambda f:f.stat().st_mtime) if (DATA/'备份').is_dir() else []
 def count(name,key):
  try:value=json.loads((DATA/name).read_text());return len(value[key] if key else value)
  except Exception:return None
 host=__import__('跨平台').host_name()
 try:log=(DATA/'连接服务.log').read_bytes()[-6000:].decode('utf-8','ignore').splitlines()[-15:]
 except Exception:log=[]
 return {'running':True,'pid':os.getpid(),'startedAt':STARTED.isoformat(timespec='seconds'),'ports':{'mac':PORT,'phone':PHONE_PORT},'host':host,'lanIP':lan_ip(),
  'keepAwake':os.name!='nt' and subprocess.run(['/usr/bin/pgrep','-f','caffeinate -s -w %d'%os.getpid()],capture_output=True).returncode==0,
  'connected':connected_devices(ROOT),'paired':paired_devices(ROOT),
  'data':{'courses':count('基础排课.json',None),'students':count('学生名单.json',None),'ledgerTransactions':count('账本.json','transactions'),'adjustWeeks':count('临时调整.json','weeks'),'backups':len(backups),'lastBackup':datetime.datetime.fromtimestamp(backups[-1].stat().st_mtime).astimezone().isoformat(timespec='seconds') if backups else None,'folder':str(DATA)},
  'network':network_check(),'log':log}
def paused():return sorted(学生状态.load(ROOT).get('paused',{}))  # 暂停上课的学生：课程管理的“未排课学生”里不列
def with_leave(week):return dict(week,leave=请假标记.of_week(ROOT,week['week']),booked=签课表.week_booked(ROOT,week['week']),paused=paused())  # 临时安排页同时拿到这一周的请假标记、账本里已记的上课/请假
# ---- GET：路径 → 函数(g)，g('x') 取网址里的参数。返回 dict/list 就发 JSON，Path 就发文件，bytes 就当网页发；抛 ValueError 就回 404（BAD400 里的回 400）
GETS={
 '/whoami':lambda g:{'root':str(ROOT.resolve()),'version':(LITE or {}).get('version','')},  # 启动程序用：端口上跑的是不是这个文件夹的 Coda 课达
 '/connection-status':lambda g:{'devices':connected_devices(ROOT)},
 '/schedule':lambda g:dict(课表存取.load(ROOT),paused=paused()),
 '/api/ledger':lambda g:账本存取.summary(ROOT),'/api/ledger/changes':lambda g:{'changes':账本存取.changes(ROOT,g('name'))},
 '/api/adjust':lambda g:with_leave(周调整存取.load(ROOT,g('week'))),
 '/api/adjust/cancelled':lambda g:{'items':周调整存取.cancelled_between(ROOT,g('from'),g('to'))},
 '/api/sheets':lambda g:签课表.pending(ROOT),
 '/api/sheets/print':lambda g:签课表.print_html(ROOT,g('id')).encode(),
 '/api/sheets/layout':lambda g:签课表.layout_cells(ROOT,g('id')),
 '/api/sheets/scanfile':lambda g:签课表.scan_path(ROOT,g('name')),
 '/api/sign':lambda g:签课表.sign_path(ROOT,g('f')),
 '/api/gaps':lambda g:补记录.overview(ROOT),
 '/api/packages':lambda g:课包.listing(ROOT,g('student')),
 '/api/gaps/student':lambda g:补记录.detail(ROOT,g('name')),
 '/api/paper':lambda g:纸质课表.pending(ROOT),
 '/api/paper/student':lambda g:纸质课表.of_student(ROOT,g('name')),
 '/api/paper/image':lambda g:纸质课表.resolve(ROOT,g('w'),g('f')),
 '/api/desk':lambda g:{'pending':desk_pending(ROOT),'url':'https://%s:%d/desk'%(lan_ip() or '这台Mac的IP',PHONE_PORT),'paired':paired_devices(ROOT)},
 '/api/works':lambda g:学生档案.works(ROOT),
 '/api/works/file':lambda g:学生档案.work_file(g('p')),
 '/api/camera':lambda g:{'volumes':[v.name for v in 相机导入.volumes()],'job':相机导入.progress(ROOT)},
 '/api/camera/file':lambda g:相机导入.card_file({'volume':g('volume'),'path':g('path')}),
 '/api/inbox':lambda g:收件箱.listing(ROOT),
 '/api/inbox/file':lambda g:素材编辑.send_path(ROOT,g('id')) if g('edited') else 收件箱.resolve(ROOT,g('id')),
 '/api/service':lambda g:service_info(),
 '/api/log':lambda g:操作日志.listing(ROOT,g('month') or None),
 '/api/mobile/week':lambda g:mobile_week(),
 '/api/marks':lambda g:{'marks':打点.listing(ROOT,g('since') or None)},
}
BAD400={'/api/adjust','/api/adjust/cancelled'}
# ---- POST：路径 → 函数(请求内容)，返回的 dict 发回去；ValueError → 400，Conflict（别处改过）→ 409
POSTS={
 '/schedule/save':lambda b:课表存取.save(ROOT,b.get('rows'),b.get('revision')),
 '/api/adjust/save':lambda b:with_leave(周调整存取.save(ROOT,b)),
 '/api/leave/set':lambda b:dict(请假标记.set_mark(ROOT,b),booked=签课表.week_booked(ROOT,b['week'])),
 '/api/attend':lambda b:签课表.attend(ROOT,b),
 '/api/ledger/add':lambda b:账本存取.add(ROOT,b),'/api/ledger/batch':lambda b:账本存取.add_batch(ROOT,b),'/api/ledger/void':lambda b:账本存取.void(ROOT,b),'/api/ledger/edit':lambda b:账本存取.edit(ROOT,b),
 '/api/student/enroll':lambda b:学生状态.enroll(ROOT,b),'/api/student/merge':lambda b:学生状态.merge(ROOT,b),'/api/student/rename':lambda b:学生状态.rename(ROOT,b),'/api/student/pause':lambda b:学生状态.set_paused(ROOT,b),'/api/student/remove':lambda b:学生状态.remove_student(ROOT,b),
 '/api/packages/save':lambda b:课包.save(ROOT,b),'/api/packages/sync':lambda b:(课包.sync(ROOT),{'ok':True})[1],
 '/api/gaps/resolve':lambda b:补记录.resolve(ROOT,b),'/api/gaps/restart':lambda b:补记录.restart(ROOT,b),
 '/api/sheets/generate':lambda b:签课表.generate(ROOT,b),'/api/sheets/upload':lambda b:签课表.upload(ROOT,b),'/api/sheets/stash':lambda b:签课表.stash(ROOT,b),'/api/sheets/scanned':lambda b:签课表.scanned(ROOT,b),'/api/sheets/review':lambda b:签课表.get_review(ROOT,b),'/api/sheets/rename':lambda b:签课表.rename_row(ROOT,b),'/api/sheets/commit':lambda b:签课表.commit(ROOT,b),'/api/sheets/topaper':lambda b:签课表.to_paper(ROOT,b),'/api/sheets/archive':lambda b:签课表.archive_sheet(ROOT,b),
 '/api/paper/file':lambda b:纸质课表.file(ROOT,b),'/api/paper/restore':lambda b:纸质课表.restore(ROOT,b),
 '/api/lang':set_lang,'/api/setup':setup_save,'/api/log/reason':lambda b:操作日志.set_reason(ROOT,b),'/api/marks/save':lambda b:打点.save(ROOT,b),
 '/api/inbox/status':lambda b:收件箱.set_status(ROOT,b),'/api/inbox/stage':lambda b:收件箱.stage(ROOT,b),'/api/inbox/open':lambda b:收件箱.open_folder(ROOT,b),'/api/inbox/copyfiles':lambda b:收件箱.copy_files(ROOT,b),'/api/inbox/prepare':lambda b:收件箱.prepare(ROOT,b),'/api/inbox/edit':lambda b:素材编辑.apply(ROOT,b),'/api/inbox/reassign':lambda b:收件箱.reassign(ROOT,b),'/api/inbox/card':lambda b:收件箱.save_card(ROOT,b),'/api/inbox/text':lambda b:收件箱.save_text(ROOT,b),'/api/inbox/missing':lambda b:收件箱.mark_missing(ROOT,b),
 '/api/archive/sent':lambda b:学生档案.sent(ROOT,b),'/api/archive/trashcut':lambda b:学生档案.trash_cut(ROOT,b),'/api/archive/open':lambda b:学生档案.open_place(ROOT,b),
 '/api/works/copy':lambda b:学生档案.works_copy(ROOT,b),'/api/works/sent':lambda b:学生档案.works_sent(ROOT,b),'/api/works/trash':lambda b:学生档案.works_trash(ROOT,b),'/api/works/open':lambda b:学生档案.works_open(ROOT,b),'/api/works/drop':lambda b:学生档案.works_drop(ROOT,b),
 '/api/desk/decide':lambda b:desk_decide(ROOT,b),'/api/desk/revoke':lambda b:revoke(ROOT,b),
 '/api/camera/scan':lambda b:相机导入.scan(ROOT,b),'/api/camera/import':lambda b:相机导入.start_import(ROOT,b),
}
POST_LIMIT={'/api/sheets/upload':45000000,'/api/sheets/stash':45000000,'/api/inbox/card':25000000,'/api/sheets/scanned':25000000}  # 其余 2MB
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,raw,kind='application/json'):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def json(self,obj,status=200):self.reply(status,json.dumps(obj,ensure_ascii=False).encode())
 def fail(self,status,message):self.json({'error':message},status)
 def redirect(self,to):self.send_response(302);self.send_header('Location',to);self.send_header('Content-Length','0');self.end_headers()
 def local(self):return self.headers.get('Host')==LOCAL
 def authorized(self):return self.local() and self.headers.get('X-Local-Token')==TOKEN
 def send_file(self,path):
  size=path.stat().st_size;start,end,status=0,size-1,200
  m=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers.get('Range',''))
  if m and (m[1] or m[2]):
   if m[1]:start=int(m[1]);end=min(int(m[2]),size-1) if m[2] else size-1
   else:start=max(0,size-int(m[2]))
   if start>end or start>=size:self.send_response(416);self.end_headers();return
   status=206
  self.send_response(status);self.send_header('Content-Type',收件箱.mime(path));self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-store')
  if status==206:self.send_header('Content-Range','bytes %d-%d/%d'%(start,end,size))
  self.end_headers()
  with path.open('rb') as f:
   f.seek(start);left=end-start+1
   while left:
    chunk=f.read(min(left,1<<20))
    if not chunk:break
    try:self.wfile.write(chunk)
    except (BrokenPipeError,ConnectionResetError):return
    left-=len(chunk)
 def do_GET(self):
  try:
   u=urlparse(self.path);p=u.path;q=parse_qs(u.query);g=lambda k:q.get(k,[''])[0]
   if lite_blocked(p):return self.fail(404,'试用版没有这个功能')
   if p=='/device-pair':
    if not self.local() or g('key')!=TOKEN:return self.reply(403,b'{}')
    return self.reply(200,page(ROOT,PROGRAM),HTML)
   if p=='/device-pair-web':
    if not self.local() or g('key')!=TOKEN:return self.reply(403,b'{}')
    return self.json(web_pair())
   if not self.local():return self.reply(404,b'{}')
   if p=='/open-uploads':(DATA/'手机上传').mkdir(exist_ok=True);__import__('跨平台').open_path(DATA/'手机上传');return self.reply(204,b'')
   if p=='/' and self.authorized() and self.headers.get('X-Lesson-Device')=='iPhone':return self.reply(200,phone_page(),HTML)
   if p in REDIRECTS:return self.redirect(REDIRECTS[p])
   if LITE and not LITE.get('setupDone') and p in ('/','/lesson'):return self.redirect('/setup')  # 测试版第一次打开：先走设置向导
   if p in PAGES:return self.reply(200,render_page(p),HTML)
   if p.startswith('/assets/'):
    n=unquote(p[8:])
    if n not in ASSETS or not (PAGE_DIR/n).is_file():return self.fail(404,'没有这个文件')
    return self.reply(200,(PAGE_DIR/n).read_bytes(),'application/javascript; charset=utf-8')
   if p not in GETS:return self.reply(404,b'{}')
   try:out=GETS[p](g)
   except ValueError as e:return self.fail(400 if p in BAD400 else 404,str(e))
   if isinstance(out,Path):return self.send_file(out)
   if isinstance(out,bytes):return self.reply(200,out,HTML)
   self.json(out)
  except Exception:
   traceback.print_exc();self.fail(503,'课程资料暂不可读取，请在 Mac 检查数据文件夹。')
 def log_before(self,p,body):
  try:return 操作日志.before(ROOT,p,body)
  except Exception:traceback.print_exc();return None   # 日志出问题不能挡住正事
 def log_after(self,p,body,pre,result):
  from urllib.parse import unquote as uq
  try:return 操作日志.record(ROOT,p,body,pre,result,device=self.headers.get('X-Lesson-Device'),referer=self.headers.get('Referer'),reason=uq(self.headers.get('X-Coda-Reason') or ''))
  except Exception:traceback.print_exc();return None,False
 def do_POST(self):
  if not self.authorized():return self.reply(403,b'{}')
  p=urlparse(self.path).path
  if lite_blocked(p,post=True):return self.fail(404,'试用版没有这个功能')
  if p=='/state':  # 手机 App 心跳
   try:self.json({'db':None,'mode':'read-only','courseCount':len(json.loads((DATA/'基础排课.json').read_text())),'ledgerAvailable':True,'lanIP':lan_ip()})
   except Exception:self.reply(503,b'{"error":"Schedule unavailable"}')
  elif p=='/editing/status':self.reply(200,b'{"owner":"Mac","device":"iPhone","readOnly":true}')
  elif p in POSTS:
   try:
    if self.headers.get('Origin') not in (None,'http://'+LOCAL):raise ValueError('来源不符')
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=POST_LIMIT.get(p,2000000):raise ValueError('请求无效或文件太大')
    body=json.loads(self.rfile.read(size))
   except Exception as e:return self.fail(400,str(e) if isinstance(e,ValueError) else '请求无效')
   pre=self.log_before(p,body)
   try:out=POSTS[p](body)
   except 存取公共.Conflict as e:self.log_after(p,body,pre,'冲突：'+str(e));return self.fail(409,str(e))
   except ValueError as e:self.log_after(p,body,pre,'失败：'+str(e));return self.fail(400,str(e))
   except Exception:traceback.print_exc();self.log_after(p,body,pre,'失败：程序出错');return self.fail(500,'保存失败，数据文件未改动')
   eid,ask=self.log_after(p,body,pre,'ok')
   raw=json.dumps(out,ensure_ascii=False).encode()
   self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
   if eid:self.send_header('X-Coda-Log',eid)
   if ask:self.send_header('X-Coda-Ask','1')
   self.end_headers();self.wfile.write(raw)
  else:self.fail(403,'手机只能查看课表和上传资料')
if __name__=='__main__':
 server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
 if not LITE or LITE.get('phone'):  # 开源版：开手机通道（App 连 18766）
  start(ROOT,TOKEN,port=PHONE_PORT,upstream_port=PORT,upload_root=DATA/'手机上传')
 if not LITE:收件箱.start_transcriber(ROOT)  # 手机没转出文字的语音，Mac 每 30 秒看一次、自动补转
 print('课程连接服务已启动：课表、账本、周调整都以 数据/ 里的文件为准；手机只读。',flush=True)
 server.serve_forever()
