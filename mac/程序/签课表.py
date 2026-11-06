"""每周签课表：按周生成签课表（浏览器里打印，/api/sheets/print），导入签字扫描件，逐行核对后入账（上课扣课、请假不扣），签字截图留作凭据。
文件都在 数据/签课表/：模板/（每张表的行位置快照）、已签扫描件/（导入的原件）、待核对/（识别结果）；签字截图在 数据/签字/。待打印/ 是以前生成 PDF 用的，留着老文件。
这个文件是“签课表模板”：决定表长什么样、每格什么意思、怎么判断上课/请假。
识别有两条路，判定规则一样（judge）：Mac/Windows 网页里由浏览器量笔迹（签课表识别.js → stash/layout/scanned）；
手机拍完直接传来的（手机网关 → upload）仍交给同目录的 纸质表单识别工具（源代码 纸质表单识别.swift，只在 Mac 上有）。"""
import base64,datetime,hashlib,json,re,subprocess,uuid
import 存取公共
from 存取公共 import data_dir
from pathlib import Path
import 周调整存取,账本存取,请假标记,课包
from 存取公共 import LOCK,ensure,read,write
TOOL=Path(__file__).with_name('纸质表单识别工具')
SIGN_INK,LEAVE_INK=.003,.025  # 签字格墨迹超过 0.3% 算签了（打个勾也算）；请假框超过 2.5% 算勾了（手机照片里的勾很细）
HEX64=re.compile(r'^[0-9a-f]{64}$')
def folders(root):
 base=data_dir(root)/'签课表';out={k:base/k for k in ('模板','待打印','已签扫描件','待核对')};out['签字']=data_dir(root)/'签字'
 for p in out.values():p.mkdir(parents=True,exist_ok=True)
 return out
def worker(root,action,data):
 if __import__('os').name=='nt':raise ValueError('这个识别工具只有 Mac 版，Windows 请在课时管理里导入签课表，由网页识别')
 if not TOOL.is_file():raise ValueError('缺少 纸质表单识别工具，请在 数据/程序 里运行“编译纸质表单识别工具.command”')
 subprocess.run(['/usr/bin/xattr','-d','com.apple.quarantine',str(TOOL)],capture_output=True)  # 微信、网盘下载的会带“来自网络”标记，系统会拦住这个小程序（10-19 测试）
 try:r=subprocess.run([str(TOOL)],input=json.dumps({'action':action,'data':data},ensure_ascii=False),text=True,capture_output=True,timeout=120)
 except subprocess.TimeoutExpired:raise ValueError('识别工具没有反应。如果屏幕上弹出“无法验证开发者”，请到 系统设置 → 隐私与安全性 里点“仍要打开”，再导入一次')
 except OSError as err:raise ValueError('签课识别工具无法运行：'+str(err))
 try:out=json.loads(r.stdout)
 except Exception:raise ValueError('识别工具没有完成：'+((r.stderr.strip().splitlines() or ['未知错误'])[-1])[:200])
 if isinstance(out,dict) and out.get('error'):raise ValueError(out['error'])
 return out
def entries_for_week(root,week):
 """这一周实际要上的课（固定课表 + 临时安排），班课按学生拆成一行一人。"""
 data=周调整存取.load(root,week);monday=datetime.date.fromisoformat(data['week']);out=[]
 for r in data['effective']:
  date=monday+datetime.timedelta(days=周调整存取.DAYS.index(r['day']))
  for n in r['studentNames']:
   out.append({'id':hashlib.sha1((r['id']+'|'+n+'|'+str(date)).encode()).hexdigest()[:12],'course':r['id'],'date':str(date),'day':r['day'],'time':r['start']+'–'+r['end'],'name':n,'units':r.get('units',1),'teacher':r.get('teacher'),'dual':r.get('dual')})
 return data['week'],out
def layout(week,entries,token):
 """签课表版式：按日期分两栏（尽量一样长），每行 时间｜学生｜签字｜请假框。坐标是 1240×1754 的页面坐标。"""
 items,rows=[],[]
 T=lambda x,y,t,size:items.append({'t':'text','x':x,'y':y,'s':t,'size':size})
 R=lambda x,y,w,h:items.append({'t':'rect','x':x,'y':y,'w':w,'h':h})
 order,groups=[],{}
 for e in entries:
  if e['date'] not in groups:order.append(e['date'])
  groups.setdefault(e['date'],[]).append(e)
 columns,weights=[[],[]],[0.0,0.0]
 for d in sorted(order,key=lambda d:(-len(groups[d]),order.index(d))):
  c=0 if weights[0]<=weights[1] else 1;columns[c].append(d);weights[c]+=len(groups[d])+1.4
 rh=min(64,min((1510-65*len(col))/max(1,sum(len(groups[d]) for d in col)) for col in columns))
 if rh<38:raise ValueError('本周人数过多，签字空间不足，请分批生成')
 T(465,80,'每周上课签到表',28);T(410,108,week+' 起 · 请假请勾选方框',17);T(55,106,'编号 '+token,13);T(1035,106,'v0.1',13)
 for ci,col in enumerate(columns):
  x=55+ci*578;y=145.0
  for d in sorted(col):
   day=sorted(groups[d],key=lambda e:(e['time'],e['id']))
   T(x+4,y+24,d[5:]+' '+day[0]['day'],22);y+=33
   bounds=[x,x+135,x+245,x+497,x+540]
   for j,label in enumerate(['时间','学生','签字','请假']):T(bounds[j]+4,y+20,label,17)
   R(x,y,540,28);y+=28
   for e in day:
    R(x,y,540,rh)
    for bx in bounds[1:-1]:items.append({'t':'line','x1':bx,'y1':y,'x2':bx,'y2':y+rh})
    T(x+4,y+rh/2+6,e['time'],17);T(x+139,y+rh/2+6,e['name'],min(21,100/max(1,len(e['name']))))
    box=[x+507,y+rh/2-10,20,20];R(*box)
    rows.append({'entry':e,'sign':[x+249,y+4,244,rh-8],'leave':box});y+=rh
   y+=4
 T(55,1694,'签字表示已上课；请假勾选方框。空白待确认。请保留四角黑色定位标记。',16)
 return items,rows
def cells(rows):
 """每行要量的格子：签字格（往里缩 2，要截图）、请假框（往里缩 4，避开框线）；另截一张整个请假框的图给人核对（leaveview）。frame 是纸上印的框线位置，识别时先对准它（纸不平也不怕偏）。"""
 out=[]
 for r in rows:
  s,l,i=r['sign'],r['leave'],r['entry']['id']
  out+=[{'id':i+'/sign','rect':[s[0]+2,s[1]+2,s[2]-4,s[3]-4],'image':True,'frame':[s[0]-4,s[1]-4,s[2]+8,s[3]+8]},{'id':i+'/leave','rect':[l[0]+4,l[1]+4,l[2]-8,l[3]-8],'frame':l,'follow':i+'/sign'},{'id':i+'/leaveview','rect':[l[0]-3,l[1]-3,l[2]+6,l[3]+6],'image':True,'follow':i+'/leave'}]
 return out
def generate(root,data):
 week,entries=entries_for_week(root,(data or {}).get('week'));d=folders(root)
 if not entries:raise ValueError('这一周没有课')
 if len(entries)>64:raise ValueError('签课表最多 64 行；请减少本次打印的课程')
 if len({e['id'] for e in entries})!=len(entries):raise ValueError('课程编号重复，请核对排课')
 token=hashlib.sha256(json.dumps({'version':'0.1','week':week,'entries':entries},ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:10]
 items,rows=layout(week,entries,token);fname='签课表_%s_%s.pdf'%(week,token)
 # 10-19 起不再生成 PDF：存下要画的东西（items），打印时浏览器按 A4 原样画出来（Mac、Windows 都能打印）
 manifest={'version':'0.1','template':'签课表','week':week,'entries':entries,'id':token,'filename':fname,'width':1240,'height':1754,'rows':rows,'cells':cells(rows),'items':items,'title':'每周上课签到表 '+week}
 (d['模板']/(token+'.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=1))
 return {'id':token,'filename':fname,'rows':len(entries)}
def ensure_cells(root):
 """旧的版式快照补上（或更新）cells，通用工具才能量格子。"""
 for p in folders(root)['模板'].glob('*.json'):
  m=json.loads(p.read_text())
  if 'cells' not in m or m['cells']!=cells(m['rows']):m['cells']=cells(m['rows']);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(m,ensure_ascii=False,indent=1));t.replace(p)
def unreliable(rows,shift):
 """纸不平时每行要挪一点才对得准，挪的幅度沿着一列慢慢变（纸鼓起来是渐变的）。
 10-27 改：以前一列里出现一次跳变，这一列后面全不信，纸稍微鼓一点整张就被拒（47/49 行）。
 现在每行只和同一列上下各 3 行的中位数比，差得多的那几行不信；挪到搜索范围边上的行也不信。别的行照常认。"""
 bad=set();cols=[]
 for r in rows:
  if cols and abs(cols[-1][-1]['sign'][0]-r['sign'][0])<50:cols[-1].append(r)
  else:cols.append([r])
 med=lambda v:sorted(v)[len(v)//2]
 for col in cols:
  edge=set()
  for r in col:
   s=r['sign'];dx,dy=shift.get(r['entry']['id'],(0,0));h=s[3]+8
   if abs(dy)>=min(24,max(3,int(0.4*h))) or abs(dx)>=min(24,max(3,int(0.4*(s[2]+8)))):edge.add(r['entry']['id'])
  bad|=edge
  for k,r in enumerate(col):
   i=r['entry']['id'];h=r['sign'][3]+8;dx,dy=shift.get(i,(0,0))
   near=[shift.get(x['entry']['id'],(0,0)) for j,x in enumerate(col) if j!=k and abs(j-k)<=3 and x['entry']['id'] not in edge]
   if len(near)>=2 and (abs(dx-med([n[0] for n in near]))>0.25*h or abs(dy-med([n[1] for n in near]))>0.25*h):bad.add(i)
 return bad
def analyze(root,target,page):
 """识别一页：通用工具量出每格笔迹，这里按签课表规则判成 上课 / 请假 / 待确认。结果按“文件内容+页码”缓存。"""
 d=folders(root);raw=target.read_bytes();rid=hashlib.sha256(raw+('#page%d'%page).encode()).hexdigest();cache=d['待核对']/(rid+'.json')
 if cache.is_file():return json.loads(cache.read_text())
 ensure_cells(root)
 out=worker(root,'scan',{'file':str(target),'page':page,'layouts':str(d['模板'])})
 return judge(root,target,page,out,cache,rid)
def judge(root,target,page,out,cache,rid):
 """把量好的每格笔迹（小程序或浏览器量的，格式一样）按签课表规则判成 上课 / 请假 / 待确认，存进待核对。"""
 d=folders(root)
 m=json.loads((d['模板']/(out['token']+'.json')).read_text());got={c['id']:c for c in out['cells']};rows=[]
 bad=unreliable(m['rows'],{c['id'][:-5]:tuple(c.get('shift',(0,0))) for c in out['cells'] if c['id'].endswith('/sign')})
 if len(bad)>0.3*len(m['rows']):raise ValueError('照片里的表格没能对准（纸不平或拍得太斜），请把纸放平、正对着重拍，或用扫描仪')
 for r in m['rows']:
  i=r['entry']['id'];sign,leave=got.get(i+'/sign',{}),got.get(i+'/leave',{})
  has,checked=sign.get('ink',0)>SIGN_INK,leave.get('ink',0)>LEAVE_INK
  status='待确认' if has==checked else ('请假' if checked else '上课')
  reason='签字和请假均有笔迹，请核对' if has and checked else ('未检测到明确笔迹' if not has and not checked else ('请核对签字' if has else '请核对请假勾选'))
  if i in bad:status,reason='待确认','这一行没完全对准（纸不平或拍斜了），请看图核对'
  rows.append({'entry':r['entry'],'status':status,'reason':reason,'image':sign.get('image',''),'leaveImage':got.get(i+'/leaveview',{}).get('image',''),'signatureInk':sign.get('ink',0),'leaveInk':leave.get('ink',0)})
 review={'reviewId':rid,'sheetId':out['token'],'week':m['week'],'sourceFile':target.name,'page':page,'rows':rows}
 cache.write_text(json.dumps(review,ensure_ascii=False));return review
def upload(root,data):
 """保存扫描件并逐页识别（批量扫描的多页 PDF 一次导入），空白页和背面自动跳过。"""
 name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',str((data or {}).get('filename','')))[:120] or '扫描件'
 if Path(name).suffix.lower() not in ('.pdf','.jpg','.jpeg','.png','.heic'):raise ValueError('请上传 PDF、JPG、PNG 或 HEIC 格式的扫描件')
 try:raw=base64.b64decode(str(data.get('data','')),validate=True)
 except Exception:raise ValueError('文件没有传完整，请重试')
 if not 1000<len(raw)<=30*1024*1024:raise ValueError('文件太小或超过 30MB')
 d=folders(root);stamp=存取公共.now().strftime('%Y%m%d_%H%M%S');target=d['已签扫描件']/(stamp+'_'+name);target.write_bytes(raw)
 pages=worker(root,'pages',{'file':str(target)})['pages'] if target.suffix.lower()=='.pdf' else 1
 sheets,skipped=[],[]
 for i in range(pages):
  try:sheets.append(review_view(analyze(root,target,i),root))
  except ValueError as err:skipped.append({'page':i+1,'reason':str(err)})
 if not sheets:raise ValueError(skipped[0]['reason'] if pages==1 else '这 %d 页里没有找到签课表（%s）'%(pages,skipped[0]['reason']))
 return {'sheets':sheets,'skipped':skipped,'pages':pages}
# ---- 浏览器识别（10-19 起，Mac 和 Windows 都用这一套）：程序只存原件、给版式、按浏览器量好的结果判定
IMG_SUFFIX=('.jpg','.jpeg','.png','.heic','.pdf')  # PDF 扫描件由浏览器里的 pdf.js 一页页画出来再识别
def stash(root,data):
 """先把照片原件存好（核对时能回看），返回文件名；同一个文件识别过就直接给结果，不用再量。"""
 name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',str((data or {}).get('filename','')))[:120] or '扫描件'
 if Path(name).suffix.lower() not in IMG_SUFFIX:raise ValueError('请上传 PDF、JPG、PNG 或 HEIC 格式的扫描件')
 try:raw=base64.b64decode(str(data.get('data','')),validate=True)
 except Exception:raise ValueError('文件没有传完整，请重试')
 if not 1000<len(raw)<=30*1024*1024:raise ValueError('文件太小或超过 30MB')
 d=folders(root);stamp=存取公共.now().strftime('%Y%m%d_%H%M%S');target=d['已签扫描件']/(stamp+'_'+name);target.write_bytes(raw)
 rid=hashlib.sha256(raw+b'#page0').hexdigest();cache=d['待核对']/(rid+'.json')
 return {'file':target.name,'cached':review_view(json.loads(cache.read_text()),root) if cache.is_file() else None}
def scan_path(root,name):
 """给浏览器读的照片：HEIC（iPhone 原图）在 Mac 上先用系统自带的 sips 转成 JPG；Windows 上的浏览器读不了 HEIC，请对方把照片存成 JPG。"""
 base=folders(root)['已签扫描件'].resolve();p=(base/Path(str(name)).name).resolve()
 if p.parent!=base or not p.is_file() or p.suffix.lower() not in IMG_SUFFIX:raise ValueError('找不到这张照片')
 if p.suffix.lower()!='.heic':return p
 jpg=p.with_name(p.name+'.jpg')
 if not jpg.is_file():
  if not Path('/usr/bin/sips').exists():raise ValueError('这台电脑打不开 HEIC 照片：请在手机上把照片存成 JPG（或截图）再导入')
  subprocess.run(['/usr/bin/sips','-s','format','jpeg',str(p),'--out',str(jpg)],capture_output=True,timeout=60)
  if not jpg.is_file():raise ValueError('HEIC 照片转换失败，请改用 JPG')
 return jpg
def layout_cells(root,token):
 if not re.fullmatch(r'[0-9a-f]{10}',str(token)):raise ValueError('表单编号不对')
 ensure_cells(root);p=folders(root)['模板']/(token+'.json')
 if not p.is_file():raise ValueError('找不到这张表（编号 %s）的版式快照，请确认是本系统打印的表单'%token)
 return {'cells':json.loads(p.read_text())['cells']}
def scanned(root,data):
 """浏览器量好的结果：{file, page, result:{token, cells:[{id, ink, shift, image}]}} → 判定、存待核对，返回核对用的数据。"""
 d=folders(root);name=Path(str((data or {}).get('file',''))).name;target=d['已签扫描件']/name
 if not name or not target.is_file():raise ValueError('找不到这张照片，请重新导入')
 page=int(data.get('page') or 0);out=data.get('result') or {}
 if not re.fullmatch(r'[0-9a-f]{10}',str(out.get('token',''))) or not isinstance(out.get('cells'),list):raise ValueError('识别结果不完整，请重新导入')
 raw=target.read_bytes();rid=hashlib.sha256(raw+('#page%d'%page).encode()).hexdigest();cache=d['待核对']/(rid+'.json')
 if cache.is_file():return {'sheets':[review_view(json.loads(cache.read_text()),root)],'skipped':[],'pages':1}
 if not (d['模板']/(out['token']+'.json')).is_file():raise ValueError('找不到这张表（编号 %s）的版式快照，请确认是本系统打印的表单'%out['token'])
 return {'sheets':[review_view(judge(root,target,page,out,cache,rid),root)],'skipped':[],'pages':1}
def review_file(root,rid):
 if not HEX64.match(str(rid)):raise ValueError('核对记录无效')
 p=folders(root)['待核对']/(rid+'.json')
 if not p.is_file():raise ValueError('找不到这次识别结果')
 return p
def to_paper(root,data):
 """拍错了：这张其实是老课表（不是周签课表）→ 原照片复制进 纸质课表/待归档，这次识别结果从待核对里拿掉（10-20）。
 已经有行入账了就不让改，请先在流水里撤销。"""
 p=review_file(root,(data or {}).get('reviewId'));rv=review_view(json.loads(p.read_text()),root)
 if rv.get('booked'):raise ValueError('这张已经入账了 %d 行，不能改成老课表；要改先在课时管理的流水里撤销'%rv['booked'])
 src=folders(root)['已签扫描件']/Path(str(rv.get('sourceFile',''))).name
 if not src.is_file():raise ValueError('找不到原来的照片')
 import 纸质课表
 if src.suffix.lower()=='.pdf':raise ValueError('PDF 扫描件不能放进纸质课表（那里只收照片）')
 name=纸质课表.keep(root,src.read_bytes(),src.name.split('_',2)[-1] if src.name[:8].isdigit() else src.name)
 bak=data_dir(root)/'备份';bak.mkdir(exist_ok=True);p.replace(bak/('改成老课表_'+p.name))   # 识别结果留一份在备份里
 return {'file':name,'pending':pending(root)}
def archive_sheet(root,data):
 """11-01 用户要：老签课表里没入账的行不想再核对了 → 整张归档，从待核对里拿掉（已入账的行不动，识别结果和照片留在备份里，可手动放回）。"""
 p=review_file(root,(data or {}).get('reviewId'))
 with LOCK:
  bak=data_dir(root)/'备份';bak.mkdir(exist_ok=True);p.replace(bak/('已归档_'+p.name))
 return {'pending':pending(root)}
def keep_check(root,review,decisions,wrong):
 """10-27 用户要：每次核对入账，把“机器认的 / 老师定的 / 老师勾了认错”连同签字格、请假框图片存下来，以后拿来改识图程序。
 存在 签课表/识别核对/记录.jsonl（一行一格，同一格再交一次就再记一行，按最后一行算）+ 图片/。老师没动的“待确认”不记。"""
 base=data_dir(root)/'签课表'/'识别核对';pics=base/'图片';pics.mkdir(parents=True,exist_ok=True);now=存取公共.now_aware().isoformat(timespec='seconds');out=[]
 def pic(uri):
  if not str(uri).startswith('data:image/png;base64,'):return ''
  raw=base64.b64decode(uri.split(',',1)[1]);fn=hashlib.sha256(raw).hexdigest()[:32]+'.png'
  if not (pics/fn).exists():(pics/fn).write_bytes(raw)
  return fn
 for r in review['rows']:
  e=r['entry'];final=decisions.get(e['id'])
  if r['booked'] or r['status']=='停课' or final in (None,'待确认') and not wrong.get(e['id']):continue
  out.append({'at':now,'sheet':review['sheetId'],'week':review['week'],'source':review.get('sourceFile'),'page':review.get('page'),'row':e['id'],'name':e['name'],'date':e['date'],
   'machine':r['status'],'reason':r.get('reason',''),'final':final,'wrong':bool(wrong.get(e['id'])),'image':pic(r.get('image','')),'leaveImage':pic(r.get('leaveImage',''))})
 if out:
  with LOCK,(base/'记录.jsonl').open('a',encoding='utf-8') as f:f.write(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in out))
def ledger_index(root):
 obj,_=read(账本存取.paths(root)[0]) if 账本存取.paths(root)[0].exists() else ({'transactions':[]},None)
 voided={t['target'] for t in obj['transactions'] if t['kind']=='void'}
 # 撤销后重新入账的记录编号会多一个“-againN”，这里按原编号认（不然那一行会一直留在待核对里）
 return {re.sub(r'-again\d+$','',t['id']):t for t in obj['transactions'] if t['id'] not in voided}
def review_view(review,root=None):
 """给页面看的识别结果：每行加上“是否已入账”。"""
 done=ledger_index(root) if root else {}
 # 打印后才在临时安排里停掉的课：这一行标“停课”，不算请假、不扣课、也不留在待核对里
 off=周调整存取.cancelled_keys(root,str(周调整存取.monday(datetime.date.fromisoformat(review['week'])))) if root and review.get('week') else set()
 wk=str(周调整存取.monday(datetime.date.fromisoformat(review['week']))) if root and review.get('week') else None
 slots=周调整存取.cancelled_slots(root,wk) if wk else set()
 def stopped(e):return (e.get('course'),e['date']) in off or (not e.get('course') and ((e['date'],e['time'].replace('-','–'),e['name']) in slots or (e['date'],'*','*') in slots))
 rows=[dict(r,booked=('sign-'+r['entry']['id']) in done,**({'status':'停课','reason':'这节课在临时安排里停了'} if stopped(r['entry']) and ('sign-'+r['entry']['id']) not in done else {})) for r in review['rows']]
 if root:rows=[with_mark(r,root) for r in rows]
 if root:names=set(账本存取.roster(root));rows=[dict(r,unknown=True) if r['entry']['name'] not in names and not r['booked'] else r for r in rows]  # 名单里没有：页面上让老师选换成谁
 return {k:v for k,v in review.items() if k!='rows'}|{'rows':rows,'booked':sum(r['booked'] for r in rows)}
def with_mark(r,root):
 """课表上的请假标记（Mac 或手机标的）：纸上勾了请假＝请假，照旧；纸上没勾请假、课表上标了＝待确认，请人核对。"""
 if r['booked'] or r['status']=='停课':return r
 e=r['entry'];m=请假标记.find(root,e['date'],e.get('course'),e['name'])
 if not m:return r
 r=dict(r,leaveMark=请假标记.label(m))
 if r['status']=='请假':return r
 if r['status']=='上课':return dict(r,status='待确认',reason='纸上签了字、没勾请假，但 %s 在课表上标了请假，请核对'%r['leaveMark'])
 return dict(r,reason=r['reason']+'；另外 %s 在课表上标了请假'%r['leaveMark'])  # 本来就待确认（空白、涂改、没对准）：照旧问，多一句提示
def rename_row(root,data):
 """10-27 用户要：签课表上的名字不在名单里（打印后在课表上改了名字），核对时旁边选“换成谁”。
 把所有待核对签课表里这个旧名字都换成选的学生（一次选好，别的几张也跟着好），改前备份；之后照常确认入账。"""
 import shutil
 d=data or {};a=str(d.get('from') or '').strip();b=str(d.get('to') or '').strip();names=账本存取.roster(root)
 if not a or a in names:raise ValueError('%s 在名单里，不用换'%a)
 if b not in names:raise ValueError('请选名单里的学生')
 base=folders(root)['待核对'];backups=data_dir(root)/'备份';backups.mkdir(exist_ok=True);n=0
 with LOCK:
  for f in base.glob('*.json'):
   try:rv=json.loads(f.read_text())
   except Exception:continue
   hit=[r for r in rv.get('rows',[]) if r.get('entry',{}).get('name')==a]
   if not hit:continue
   for r in hit:r['entry']['name']=b
   shutil.copy2(f,backups/('待核对_'+f.name));存取公共.write_json(f,rv,indent=None);n+=len(hit)
 return dict(get_review(root,d),renamed=n)
def get_review(root,data):return review_view(json.loads(review_file(root,(data or {}).get('reviewId')).read_text()),root)
def pending(root):
 """还有没入账行的扫描件，最新的在前。"""
 out=[]
 for p in sorted(folders(root)['待核对'].glob('*.json'),key=lambda f:f.stat().st_mtime,reverse=True):
  try:r=review_view(json.loads(p.read_text()),root)
  except Exception:continue
  left=sum(1 for x in r['rows'] if not x['booked'] and x['status']!='停课')
  if left:out.append({'reviewId':r['reviewId'],'week':r['week'],'sourceFile':r['sourceFile'],'rows':len(r['rows']),'left':left})
 return {'pending':out,'printed':printed(root)}
MARKERS=[(34,34,24),(1206,34,18),(1206,1720,21),(34,1720,15)]
def crc32(data):
 import zlib;return zlib.crc32(bytes(data))&0xffffffff
def print_html(root,token):
 """签课表打印页：A4 一页，四角定位黑块 + 顶部编号条码 + 表格，和原来小程序画的 PDF 一模一样的位置（1240×1754 页面坐标）。"""
 if not re.fullmatch(r'[0-9a-f]{10}',str(token)):raise ValueError('表单编号不对')
 p=folders(root)['模板']/(token+'.json')
 if not p.is_file():raise ValueError('找不到这张签课表')
 m=json.loads(p.read_text())
 items=m.get('items') or layout(m['week'],m['entries'],token)[0]
 import html as H
 out=[]
 for x,y,s in MARKERS:out.append('<rect x="%g" y="%g" width="%g" height="%g"/>'%(x-s/2,y-s/2,s,s))
 raw=[0xa6,0x5c]+list(bytes.fromhex(token));raw.append(crc32(raw)&0xff)
 bits=[(b>>i)&1 for b in raw for i in range(7,-1,-1)]
 for i,b in enumerate(bits):
  if b:out.append('<rect x="%g" y="26" width="6" height="20"/>'%(428+i*6))
 for it in items:
  t=it.get('t')
  if t=='text':out.append('<text x="%g" y="%g" font-size="%g">%s</text>'%(it['x'],it['y'],it.get('size') or 18,H.escape(str(it.get('s','')))))
  elif t=='rect':out.append('<rect x="%g" y="%g" width="%g" height="%g"%s/>'%(it['x'],it['y'],it['w'],it['h'],'' if it.get('fill') else ' fill="none" stroke="#000" stroke-width="1"'))
  elif t=='line':out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#000" stroke-width="1"/>'%(it['x1'],it['y1'],it['x2'],it['y2']))
 title=H.escape(m.get('title') or ('每周上课签到表 '+m.get('week','')))
 return (('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>%s</title><script>window.CODA_NO_LANG_TOGGLE=1;window.CODA_LANG="@@LANG@@"</script><script src="/assets/i18n.js"></script><style>'
  '@page{size:A4 portrait;margin:0}html,body{margin:0;padding:0;background:#fff}'
  'svg{display:block;width:210mm;height:297mm}svg text{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Noto Sans SC",sans-serif;fill:#000}'
  '.tip{font:15px -apple-system,"Microsoft YaHei",sans-serif;padding:12px 16px;background:#fff7e0;border-bottom:1px solid #f0d58a;display:flex;gap:12px;align-items:center}'
  '.tip button{font:inherit;padding:6px 16px;border-radius:8px;border:0;background:#223047;color:#fff;cursor:pointer}'
  '@media print{.tip{display:none}}</style></head><body>'
  '<div class="tip"><span>打印设置：纸张 <b>A4</b>，缩放 <b>实际大小 / 100%%</b>，边距 <b>无</b>。四个角的黑块要完整打出来。</span><button onclick="print()">打印</button></div>'
  '<svg viewBox="0 0 1240 1754" xmlns="http://www.w3.org/2000/svg">%s</svg>'
  '<script>addEventListener("load",()=>setTimeout(()=>print(),400))</script></body></html>')%(title,''.join(out))).replace('@@LANG@@',存取公共.LANG)
def printed(root):
 """已生成的签课表（待打印 文件夹），最新的在前；有 title 的（比如补打的临时课表）用 title 显示。"""
 d=folders(root);out=[]
 for t in sorted(d['模板'].glob('*.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:40]:
  try:m=json.loads(t.read_text())
  except Exception:continue
  out.append({'id':t.stem,'filename':m.get('filename',''),'week':m.get('week',''),'title':m.get('title','') if not str(m.get('title','')).startswith('每周上课签到表') else '','rows':len(m.get('rows',[])),'made':datetime.datetime.fromtimestamp(t.stat().st_mtime).strftime('%m/%d %H:%M')})
 return out
def commit(root,data):
 """把核对过的行写进账本：上课按课程设置扣 1 或 2 课时，请假不扣，待确认的先不动；同一行再次提交会跳过。"""
 review=review_view(json.loads(review_file(root,(data or {}).get('reviewId')).read_text()),root);decisions=data.get('decisions')
 if not isinstance(decisions,dict):raise ValueError('核对结果无效')
 d=folders(root);names=账本存取.roster(root);built=[];notes=[];later=0;today=str(存取公共.today())
 for row in review['rows']:
  e=row['entry'];status=decisions.get(e['id'],'待确认')
  if row['status']=='停课':continue  # 临时安排里停了的课不入账
  if status not in ('上课','请假','待确认'):raise ValueError('出勤状态不对')
  if status=='待确认':continue
  # 10-19 测试：打印后删了的学生会让整张表都入不了账；还没到的课签了“上课”也会提前扣。改成跳过这几行、其余照常入账
  if e['name'] not in names:notes.append(e['name']+' 已不在名单里，这一行没入账');continue
  if status=='上课' and e['date']>today:later+=1;continue
  if status=='上课' and 课包.covering(root,e['name'],e['date']):notes.append('%s %s 在课包期间，按周扣，这一行不另外扣'%(e['name'],e['date'][5:]));continue
  units=e.get('units') if e.get('units') in (1,2) else 1
  try:tx=账本存取.make_tx({'id':'sign-'+e['id'],'kind':'lesson' if status=='上课' else 'leave','student':e['name'],'date':e['date'],'units':units,'time':e['time'].replace('–','-'),'note':'签课表 '+review['sheetId']},names)
  except ValueError as err:raise ValueError(e['name']+'：'+str(err))
  img=row.get('image','')
  if img.startswith('data:image/png;base64,'):
   raw=base64.b64decode(img.split(',',1)[1]);fn=hashlib.sha256(raw).hexdigest()[:32]+'.png';(d['签字']/fn).write_bytes(raw);tx['sign']=fn
  tx.update(sheet=review['sheetId'],course=e.get('course'),teacher=e.get('teacher'),dual=e.get('dual'))
  built.append(tx)
 ledger,_,backups=账本存取.paths(root);saved=skipped=0
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions'];known={t['id'] for t in txs}
  voided={t['target'] for t in txs if t['kind']=='void'}
  for tx in built:
   if tx['id'] in known:
    # 这一行以前记过、后来在流水里撤销了：再确认就重新记一条（换个编号），不再默默跳过
    live=[i for i in known if re.sub(r'-again\d+$','',i)==tx['id'] and i not in voided]
    if live:skipped+=1;continue
    n=2
    while tx['id']+'-again%d'%n in known:n+=1
    tx['id']=tx['id']+'-again%d'%n
   try:账本存取.check_live(tx,txs)
   except ValueError:skipped+=1;continue
   txs.append(账本存取.stamp(tx));known.add(tx['id']);saved+=1
  if saved:write(ledger,obj,rev,backups,'账本')
 try:keep_check(root,review,decisions,data.get('wrong') or {})
 except Exception:pass   # 记识别对错出问题不能挡住入账
 if later:notes.append('%d 节课还没到日子，先不记上课，到了再核对'%later)
 return {'saved':saved,'skipped':skipped,'notes':notes,'pending':later+sum(1 for r in review['rows'] if r['status']!='停课' and not r['booked'] and decisions.get(r['entry']['id'],'待确认')=='待确认'),'ledger':账本存取.summary(root)}
def sign_path(root,name):
 base=folders(root)['签字'].resolve();p=(base/Path(str(name)).name).resolve()
 if p.parent!=base or not re.fullmatch(r'[0-9a-f]{32}\.png',p.name) or not p.is_file():raise ValueError('找不到签字图片')
 return p
def week_booked(root,week):
 """某周每节课每位学生在账本里已经记了什么：{课程编号: {学生: 'lesson' | 'leave'}}。按 学生+日期+时段 对（签课表、手机、手动记的都认）。"""
 _,entries=entries_for_week(root,week)
 ledger=账本存取.paths(root)[0]
 txs=read(ledger)[0]['transactions'] if ledger.exists() else []
 voided={t['target'] for t in txs if t['kind']=='void'}
 live={(t['student'],t['date'],t.get('time')):t['kind'] for t in txs if t['id'] not in voided and t['kind'] in ('lesson','leave','noshow')}
 out={}
 for e in entries:
  k=live.get((e['name'],e['date'],e['time'].replace('–','-')))
  if k:out.setdefault(e['course'],{})[e['name']]=k
 return out
def attend(root,data):
 """不靠签课表直接记“上课了”（打印后才临时加的课）：{week, course, student, by}。
 流水编号和签课表那一行一样（sign-<行编号>），所以这节课以后就算在纸上签了字，核对入账时也会跳过，不会重复扣。"""
 if not isinstance(data,dict):raise ValueError('请求无效')
 by=data.get('by') if data.get('by') in ('Mac','手机') else 'Mac'
 week,entries=entries_for_week(root,data.get('week'))
 e=next((x for x in entries if x['course']==data.get('course') and x['name']==data.get('student')),None)
 if not e:raise ValueError('这一周没有这节课（可能已停课或课表改过），请刷新')
 if e['date']>str(存取公共.today()):raise ValueError('这节课在 %s，还没到，不能先记上课（请假可以提前标）'%e['date'][5:].replace('-','/'))  # 10-19 测试：点错了会提前扣课时
 if 课包.covering(root,e['name'],e['date']):raise ValueError('%s 这段时间是课包，按周扣，不用一节节记；要改这周扣几节，去课时管理“…”→“课包”'%e['name'])
 base='sign-'+e['id'];units=e.get('units') if e.get('units') in (1,2) else 1
 kind='noshow' if data.get('kind')=='noshow' else 'lesson'  # 10-31：旷课也从这里记，同样先扣课时
 tx=账本存取.make_tx({'id':base,'kind':kind,'student':e['name'],'date':e['date'],'units':units,'time':e['time'].replace('–','-'),'note':by+(' 记旷课' if kind=='noshow' else ' 记上课')},账本存取.roster(root))
 tx.update(course=e.get('course'),teacher=e.get('teacher'),dual=e.get('dual'),via=by)
 ledger,_,backups=账本存取.paths(root)
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions']
  voided={t['target'] for t in txs if t['kind']=='void'};old=next((t for t in txs if t['id']==base),None)
  if old and base not in voided:raise ValueError(e['name']+' 这节课已经记过'+({'lesson':'上课','noshow':'旷课'}.get(old['kind'],'请假'))+'，要改请先到课时管理的流水里撤销')
  if old:tx['id']=base+'-'+uuid.uuid4().hex[:6]  # 以前记过又撤销了：换个编号重记
  账本存取.check_live(tx,txs)
  txs.append(账本存取.stamp(tx));write(ledger,obj,rev,backups,'账本')
 try:请假标记.set_mark(root,{'week':week,'course':e['course'],'student':e['name'],'on':False})  # 上了课就不算请假了
 except ValueError:pass
 return {'week':week,'booked':week_booked(root,week),'leave':请假标记.of_week(root,week),'units':units}
