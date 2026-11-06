"""收件箱：手机上传的课堂资料（上课视频、照片、语音和文字随记）。
原文件只读不动；状态记在 数据/收件箱状态.json；整理（复制）出去的文件放在 数据/整理/。"""
import 存取公共
import datetime,json,mimetypes,re,shutil,subprocess
from 存取公共 import data_dir
import 周调整存取
from pathlib import Path
from 存取公共 import LOCK,ensure,read,write
VIDEO={'.mov','.mp4','.m4v'};PHOTO={'.jpg','.jpeg','.png','.heic','.heif'};AUDIO={'.m4a','.aac','.wav'};TEXT={'.txt'}
STATUS=('新','待剪辑','已发家长','已处理','预删除','已移除')  # 已移除：只是不在收件箱里显示（原文件不删，可在“已移除”里恢复）
APPLE_EPOCH=978307200
def paths(root):data=data_dir(root);return data/'手机上传',data/'收件箱状态.json',data/'整理',data/'备份'
def clean(name):return re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',str(name)).strip() or '未命名'
def kind_of(path,record):
 ext=path.suffix.lower();k=record.get('kind')
 if k=='voice-note' or ext in AUDIO:return 'voice'
 if k=='text-note' or ext in TEXT:return 'text'
 if ext in VIDEO:return 'video'
 if ext in PHOTO:return 'photo'
 return 'other'
def when(record,path):
 # 先用文件名里手机记下的当地时间（学生名_2026-10-11_08-46-51_…）：Mac 的时区和手机不同时，按上课当时的时间算日期
 m=re.search(r'_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_',path.name)
 if m:
  try:return datetime.datetime.fromisoformat('%s %s:%s:%s'%m.groups())
  except ValueError:pass
 value=record.get('date')
 try:
  if isinstance(value,(int,float)):return datetime.datetime.fromtimestamp(APPLE_EPOCH+value)
  if isinstance(value,str):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).astimezone().replace(tzinfo=None)
 except Exception:pass
 return datetime.datetime.fromtimestamp(path.stat().st_mtime)
def students_of(record,path):
 found=[s.get('name') for s in (record.get('students') or ([record['student']] if record.get('student') else [])) if isinstance(s,dict) and s.get('name')]
 return found or [path.name.split('_')[0]]
def scan(root):
 upload=paths(root)[0];items=[]
 for category in ('照片与视频','笔记'):
  base=upload/category
  if not base.is_dir():continue
  for folder in base.iterdir():
   if not folder.is_dir():continue
   for f in folder.iterdir():
    if f.name.startswith('.') or f.suffix in ('.json','.partial'):continue
    side=f.with_suffix(f.suffix+'.json')
    try:record=json.loads(side.read_text()) if side.exists() else {}
    except Exception:record={}
    k=kind_of(f,record);text=record.get('text')
    if k=='text' and not text:
     try:text=f.read_text(errors='ignore')[:4000]
     except Exception:pass
    moment=when(record,f)
    items.append({'id':'/'.join((category,folder.name,f.name)),'kind':k,'students':students_of(record,f),'date':moment.isoformat(timespec='seconds'),'size':f.stat().st_size,'file':f.name,'text':text or '','device':record.get('deviceModel')})
 import 相机导入  # 从相机导入的素材（在 Mac 本地 ~/Movies/课程与签到_相机素材），编号 camera/<编号>
 for r in 相机导入.records(root):
  if Path(r['path']).is_file():items.append({'id':'camera/'+r['id'],'kind':r['kind'],'students':r['students'],'date':r['date'],'size':r['size'],'file':Path(r['path']).name,'text':'','device':'相机'})
 items.sort(key=lambda x:x['date'],reverse=True);return items
def lessons(root,items):
 """资料那天这位学生实际上的课（固定课表 + 临时安排）：{"日期|学生": "18:00–18:45"}，给“按课汇总”的第一行用。"""
 weeks={};out={}
 for x in items:
  day=x['date'][:10]
  for n in x['students']:
   key=day+'|'+n
   if key in out:continue
   d=datetime.date.fromisoformat(day);mon=str(周调整存取.monday(d))
   if mon not in weeks:
    try:weeks[mon]=周调整存取.load(root,mon)['effective']
    except Exception:weeks[mon]=[]
   times=[r['start']+'–'+r['end'] for r in weeks[mon] if r['day']==周调整存取.DAYS[d.weekday()] and n in r['studentNames']]
   out[key]='、'.join(times)
 return out
def lesson_teachers(root,items):
 """资料那天这位学生那节课是哪位老师（颜色）：{"日期|学生": ["red","blue"]}，服务管理按老师分类用（10-20）。双师课两位都算。"""
 weeks={};out={}
 for x in items:
  day=x['date'][:10]
  for n in x['students']:
   key=day+'|'+n
   if key in out:continue
   d=datetime.date.fromisoformat(day);mon=str(周调整存取.monday(d))
   if mon not in weeks:
    try:weeks[mon]=周调整存取.load(root,mon)['effective']
    except Exception:weeks[mon]=[]
   cs=set()
   for r in weeks[mon]:
    if r['day']==周调整存取.DAYS[d.weekday()] and n in r['studentNames']:
     dual=r.get('dual')
     if dual:cs|={c for c in (dual.get('left'),dual.get('right')) if c and c!='both'} or {'red','blue'}
     cs|=set(r.get('teachers') or [r.get('teacher') or 'blue'])
   out[key]=sorted(cs)
 return out
def classmates(root,items):
 """班课：资料拍摄时间落在哪节多人课里（前后放宽 20 分钟），给出这节课的全部学生，改学生时可以一键“全班”。{资料id: [名字…]}"""
 import 请假标记,签课表
 weeks={};away={};out={}
 for x in items:
  try:t=datetime.datetime.fromisoformat(x['date'][:19])
  except Exception:continue
  d=t.date();mon=str(周调整存取.monday(d))
  if mon not in weeks:
   try:weeks[mon]=周调整存取.load(root,mon)['effective']
   except Exception:weeks[mon]=[]
   # 这周请假的人（账本记了请假，或者标了请假还没记上课），“全班”里不算他们
   try:marks=请假标记.of_week(root,mon)
   except Exception:marks={}
   try:booked=签课表.week_booked(root,mon)
   except Exception:booked={}
   away[mon]={(c,n) for c in set(marks)|set(booked) for n in set(marks.get(c,{}))|set(booked.get(c,{})) if booked.get(c,{}).get(n)=='leave' or (n in marks.get(c,{}) and booked.get(c,{}).get(n)!='lesson')}
  mins=t.hour*60+t.minute
  # 拍摄时间不在课上（比如课后补写的文字）：这天他只上一节多人课，就认这节
  day=[r for r in weeks[mon] if r['day']==周调整存取.DAYS[d.weekday()] and len(r.get('studentNames') or [])>1 and set(r['studentNames'])&set(x['students'])]
  for r in weeks[mon]:
   names=r.get('studentNames') or []
   if r['day']!=周调整存取.DAYS[d.weekday()] or len(names)<2 or not set(names)&set(x['students']):continue
   try:s=int(r['start'][:2])*60+int(r['start'][3:5]);e=int(r['end'][:2])*60+int(r['end'][3:5])
   except Exception:continue
   if s-20<=mins<=e+20 or len(day)==1:
    here=[n for n in names if (r.get('id'),n) not in away[mon]]
    if len(here)>1:out[x['id']]=here
    break
 return out
def listing(root):
 state=paths(root)[1];ensure(state,{'version':1,'items':{}});obj,rev=read(state)
 items=scan(root)
 mates=classmates(root,items)
 for x in items:
  rec=obj['items'].get(x['id'],{});x['status']=rec.get('status','新');x['auto']=rec.get('auto')
  x['sentTo']=rec.get('sentTo',[]);x['classmates']=mates.get(x['id'],[])  # 班课：一条资料几个人共用，“已发”按人分开记
  e=rec.get('edit');x['edit']={k:v for k,v in e.items() if k!='file'} if e and Path(e.get('file','')).is_file() else None
 import 学生档案  # 成片和“已剪进成片”都在作品管理里管，服务管理只管课堂反馈
 rec=学生档案.records(root)
 return {'items':items,'revision':rev,'statuses':list(STATUS),'lessons':lessons(root,items),'archives':{k:{'at':v['at'],'files':v['files']} for k,v in rec.get('lessons',{}).items()},
  'texts':{k:v.get('text','') for k,v in obj.get('texts',{}).items()},'missing':missing(root,items,rec,obj),'missingDone':obj.get('missingDone',{}),'lessonTeachers':lesson_teachers(root,items+[{'date':k.split('|')[0],'students':[k.split('|')[1]]} for k in obj.get('texts',{}) if '|' in k])}  # 卡片文字框里改过的“上课内容”（按 日期|学生）
def missing(root,items,rec,obj):
 """上了课却没上传资料（10-20 用户定：按课表算，本周 + 上周）：课表上这节课时间已经过了、没停课、没标请假、账本里也没记请假，
 那天这个学生（或同班同学拍的、算他一份的）没有任何照片 / 视频 / 语音 / 文字，也没归档、卡片里没写上课内容，就列出来。暂停上课的从暂停那天起不算。"""
 import 签课表,请假标记,学生状态,账本存取
 now=存取公共.now();today=now.date();mon=周调整存取.monday(today)
 have=set()
 for x in items:
  for n in set(x.get('students') or [])|set(x.get('classmates') or []):have.add(x['date'][:10]+'|'+n)
 have|=set(rec.get('lessons',{}))|set(obj.get('texts',{}))
 leave={(t['student'],t['date']) for t in 账本存取.summary(root)['transactions'] if t['kind']=='leave' and not t['voided']}
 paused=学生状态.load(root).get('paused',{});out=[];done=obj.get('missingDone',{})   # 老师标过“已发送”等的，不再提醒
 for m in (mon-datetime.timedelta(days=7),mon):
  try:_,entries=签课表.entries_for_week(root,str(m));marks=请假标记.of_week(root,str(m))
  except Exception:continue
  for e in entries:
   n,d=e['name'],e['date']
   hm=now.strftime('%H:%M')
   if d>str(today) or (d==str(today) and e['time'][:5]>hm):continue   # 还没开始
   ongoing=d==str(today) and e['time'][-5:]>hm   # 10-31：正在上的这节也列出来（老师要边上边记上课内容），标“正在上”
   if n in paused and d>=paused[n]:continue
   if n in (marks.get(e.get('course'),{}) or {}) or (n,d) in leave:continue
   if d+'|'+n in have or d+'|'+n in done:continue
   dual=e.get('dual');cs={c for c in ((dual or {}).get('left'),(dual or {}).get('right')) if c and c!='both'} if dual else set()
   if dual and not cs:cs={'red','blue'}
   cs.add(e.get('teacher') or 'blue')
   out.append({'student':n,'date':d,'day':e['day'],'time':e['time'],'teachers':sorted(cs),'ongoing':ongoing})
 out.sort(key=lambda x:(x['date'],x['time'],x['student']),reverse=True)
 return out
def mark_missing(root,data):
 """“上了课没传资料”里的一节，老师标成已处理（比如剪好的视频直接发家长了）：{key:'日期|学生', status, reason}；clear:true 撤销。"""
 import datetime
 d=data or {};key=str(d.get('key',''))
 if key.count('|')!=1 or len(key)>60:raise ValueError('请求无效')
 status=str(d.get('status') or '').strip()[:20];reason=str(d.get('reason') or '').strip()[:200]
 if not d.get('clear') and not status:raise ValueError('请选一个状态')
 state,backups=paths(root)[1],paths(root)[3]
 with LOCK:
  ensure(state,{'version':1,'items':{}});obj,rev=read(state);m=obj.setdefault('missingDone',{})
  if d.get('clear'):m.pop(key,None)
  else:m[key]={'status':status,'reason':reason,'at':datetime.datetime.now().isoformat(timespec='seconds')}
  write(state,obj,rev,backups,'收件箱状态')
 return listing(root)
def save_text(root,data):
 """服务管理卡片文字框里改的“上课内容”存到 收件箱状态.json 的 texts（按 日期|学生），刷新、重启、换电脑都还在。空字符串＝恢复成自动生成的。"""
 key=str((data or {}).get('key',''));text=str((data or {}).get('text',''))
 if '|' not in key or len(key)>100 or len(text)>20000:raise ValueError('请求无效')
 import datetime
 state,backups=paths(root)[1],paths(root)[3]
 with LOCK:
  ensure(state,{'version':1,'items':{}});obj,rev=read(state);texts=obj.setdefault('texts',{})
  if text.strip():texts[key]={'text':text,'at':datetime.datetime.now().isoformat(timespec='seconds')}
  else:texts.pop(key,None)
  write(state,obj,rev,backups,'收件箱状态')
 return {'ok':True}
def copy_files(root,data):
 """把选中的照片、视频（原文件，不复制不改动）放到 Mac 剪贴板，到微信里 ⌘V 一次发出去。"""
 ids=(data or {}).get('ids')
 if not isinstance(ids,list) or len(ids)>100 or (not ids and not (data or {}).get('card')):raise ValueError('请求无效')  # 只有卡片、没有视频也行
 import 素材编辑;files=[str(wechat_size(素材编辑.send_path(root,i))) for i in ids]  # 改过的用改好的那份；太大的视频换成发微信用的小视频
 card=str(data.get('card') or '')
 if card:  # 课堂卡片（文字和照片画在一张图里），放在最前面
  cp=(card_dir(root)/Path(card).name).resolve()
  if cp.parent!=card_dir(root).resolve() or not cp.is_file():raise ValueError('找不到课堂卡片')
  files=[str(cp)]+files
 text=str(data.get('text') or '').strip()[:20000]
 import 跨平台
 if 跨平台.WIN:跨平台.copy_windows(files,text);return {'copied':len(files)}
 r=subprocess.run(['/usr/bin/osascript','-l','JavaScript',str(Path(__file__).with_name('复制文件到剪贴板.js')),*(['--text',text] if text else []),*files],capture_output=True,text=True,timeout=20)
 if r.stdout.strip()!='ok':raise ValueError('没能放到剪贴板：'+(r.stderr.strip()[-200:] or '未知原因'))
 return {'copied':len(files)}
def resolve(root,item_id):
 if str(item_id).startswith('final/'):
  import 学生档案;parts=str(item_id).split('/',3)
  p=(学生档案.EDIT/parts[1]/parts[2]/parts[3]).resolve() if len(parts)==4 else None
  if not p or 学生档案.EDIT.resolve() not in p.parents or not p.is_file():raise ValueError('找不到这个成片')
  return p
 if str(item_id).startswith('camera/'):
  import 相机导入;return 相机导入.record_file(root,str(item_id)[7:])
 upload=paths(root)[0].resolve();path=(upload/str(item_id)).resolve()
 if upload not in path.parents or not path.is_file() or path.suffix=='.json':raise ValueError('找不到这份资料')
 return path
import threading as _threading
PREP_LOCK=_threading.Lock()
WECHAT_DIR=Path.home()/'Movies'/'课程与签到_发微信小视频'  # Mac 本地，不进 iCloud；删了也没关系，下次会重新做
def wechat_size(path):
 """发微信时太大的视频（超过 40MB，比如 iPhone 拍的 1080p/4K）换成 720p 小视频（约每分钟 19MB）。
 微信一次粘贴好几个大视频时会丢掉一部分（10-17 用户实测：3 个视频只发出 1 个）。做过一次就留着复用，原文件不动。"""
 path=Path(path)
 if path.suffix.lower() not in VIDEO or path.stat().st_size<=40*1024*1024:return path
 import 素材编辑
 out=wechat_out(path)
 with PREP_LOCK:lock=PREP_LOCKS.setdefault(str(out),_threading.Lock())
 with lock:  # 同一个视频只压一次：再点一次“发家长”就等前面那次压完，不会撞车失败
  if not out.is_file():
   tmp=out.with_name(out.stem+'.part.mp4')
   try:素材编辑.tool({'compress':str(path),'out':str(tmp)},timeout=1800);tmp.replace(out);PREP_ERR.pop(str(out),None)
   except Exception as e:PREP_ERR[str(out)]=str(e)[:200];raise
 return out
def wechat_out(path):
 import hashlib
 WECHAT_DIR.mkdir(parents=True,exist_ok=True)
 return WECHAT_DIR/(hashlib.sha1(('%s|%d|%d'%(path,path.stat().st_size,int(path.stat().st_mtime))).encode()).hexdigest()[:16]+'.mp4')
PREP_LOCKS={};PREP_ERR={}
def _prep_one(p):
 try:wechat_size(p)
 except Exception:pass  # 错误记在 PREP_ERR，网页会显示
def prepare(root,data):
 """发家长前先在后台把大视频压小，网页每秒问一次进度：{ids} → {items:[{id,state:ready|working|error,pct,error}],ready:bool}"""
 import 素材编辑,threading
 ids=(data or {}).get('ids') or []
 if not isinstance(ids,list) or len(ids)>100:raise ValueError('请求无效')
 out=[]
 for i in ids:
  p=Path(素材编辑.send_path(root,i))
  if p.suffix.lower() not in VIDEO or p.stat().st_size<=40*1024*1024:out.append({'id':i,'state':'ready'});continue
  o=wechat_out(p)
  if o.is_file():out.append({'id':i,'state':'ready'});continue
  if str(o) in PREP_ERR and not (data or {}).get('retry'):out.append({'id':i,'state':'error','error':PREP_ERR[str(o)]});continue
  with PREP_LOCK:lock=PREP_LOCKS.setdefault(str(o),_threading.Lock())
  if not lock.locked():
   PREP_ERR.pop(str(o),None)
   threading.Thread(target=_prep_one,args=(p,),daemon=True).start()
  tmp=o.with_name(o.stem+'.part.mp4')
  try:dur=0 if __import__('os').name=='nt' else float(subprocess.run(['/usr/bin/mdls','-raw','-name','kMDItemDurationSeconds',str(p)],capture_output=True,text=True,timeout=5).stdout or 0)
  except Exception:dur=0
  expect=dur*2.65e6/8 if dur>0 else p.stat().st_size/4
  out.append({'id':i,'state':'working','pct':min(99,int((tmp.stat().st_size if tmp.exists() else 0)*100/expect)) if expect else 0})
 return {'items':out,'ready':all(x['state']=='ready' for x in out)}
# 语音转文字引擎：SenseVoice（阿里开源，本机离线，比苹果自带的准；大模型不随程序发布）
SENSEVOICE=Path(__import__('os').environ.get('LESSON_SENSEVOICE') or Path(__file__).resolve().parents[4]/'3_可用'/'工具'/'语音识别_SenseVoice_v1'/'转文字.py')
def fix_list(root):
 """数据/语音纠错.txt：每行“错词=对词”（比如 核弦=和弦），识别完按表替换。专业词老错就往里加一行。"""
 f=data_dir(root)/'语音纠错.txt'
 if not f.exists():f.write_text('# 语音转文字纠错表：每行“错词=对词”，# 开头是说明。识别完按表替换。\n核弦=和弦\n',encoding='utf-8')
 return f
def transcribe_missing(root):
 """手机没转出文字的语音，在 Mac 上补转：先用 SenseVoice（一次转一批，很快）；SenseVoice 不在或出错时，用苹果自带的（程序/语音转文字.app）。
 转出来的文字写进语音旁边的 json（text），服务管理里自动出现在这节课的上课内容里；没听出说话的记下来，不再反复转。"""
 import tempfile
 app=Path(__file__).with_name('语音转文字.app');n=0
 if not STT_LOCK.acquire(blocking=False):return 0  # 一次只跑一轮
 try:
  todo=[]
  for x in scan(root):
   if x['kind']!='voice' or x['text'].strip() or str(x['id']).startswith(('camera/','final/')):continue
   try:src=resolve(root,x['id'])
   except ValueError:continue
   side=src.with_suffix(src.suffix+'.json')
   try:rec=json.loads(side.read_text()) if side.exists() else {}
   except Exception:rec={}
   if not rec.get('sttTried'):todo.append((x,src,side,rec))
  if not todo:return 0
  texts=None
  if SENSEVOICE.is_file():
   try:
    r=subprocess.run(['/usr/bin/python3','-I',str(SENSEVOICE),'--纠错',str(fix_list(root)),*[str(t[1]) for t in todo]],capture_output=True,text=True,timeout=600)
    texts=json.loads(r.stdout) if r.returncode==0 else None
   except Exception:texts=None
  for x,src,side,rec in todo:
   if texts is not None:
    text=(texts.get(str(src)) or '').strip()
    if text:rec['text']=text;rec['textBy']='SenseVoice';n+=1
    else:rec['sttError']='没听出说话'
    rec['sttTried']=True
    存取公共.write_json(side,rec,indent=None)
   elif app.is_dir():n+=_transcribe_one(root,app,x,tempfile)
 finally:STT_LOCK.release()
 return n
import threading as _threading
STT_LOCK=_threading.Lock()
def _transcribe_one(root,app,x,tempfile):
  if x['kind']!='voice' or x['text'].strip() or str(x['id']).startswith(('camera/','final/')):return 0
  try:src=resolve(root,x['id'])
  except ValueError:return 0
  side=src.with_suffix(src.suffix+'.json')
  try:rec=json.loads(side.read_text()) if side.exists() else {}
  except Exception:rec={}
  if rec.get('sttTried'):return 0
  out=Path(tempfile.mkdtemp())/'r.json'
  try:subprocess.run(['/usr/bin/open','-n','-W',str(app),'--args',str(src),str(out)],timeout=200,check=False)
  except subprocess.TimeoutExpired:pass
  try:res=json.loads(out.read_text())
  except Exception:res={'error':'没有结果'}
  rec['sttTries']=rec.get('sttTries',0)+1;got=0
  if res.get('text','').strip():rec['text']=res['text'].strip();rec['textBy']='Mac 补转';rec['sttTried']=True;got=1
  else:
   rec['sttError']=res.get('error','')[:200]
   if 'No speech' in rec['sttError'] or rec['sttTries']>=3:rec['sttTried']=True  # 没听出说话、或试了 3 次：不再试；超时之类的下一轮再试
  存取公共.write_json(side,rec,indent=None)
  return got
def start_transcriber(root):
 import threading,time
 def loop():
  while True:
   try:transcribe_missing(root)
   except Exception:pass
   time.sleep(30)
 threading.Thread(target=loop,daemon=True).start()
def card_dir(root):
 d=paths(root)[2]/'课堂卡片';d.mkdir(parents=True,exist_ok=True);return d
def save_card(root,data):
 """服务管理画好的课堂卡片（JPG）存到 数据/整理/课堂卡片/学生_日期.jpg，发家长时和视频一起放进剪贴板。"""
 import base64
 key=str((data or {}).get('key',''));img=str((data or {}).get('image',''))
 if '|' not in key or not img.startswith('data:image/jpeg;base64,'):raise ValueError('卡片内容不对')
 raw=base64.b64decode(img.split(',',1)[1])
 if len(raw)>15*1024*1024:raise ValueError('卡片太大')
 day,name=key.split('|',1);f=card_dir(root)/(clean(name)+'_'+day+'.jpg');f.write_bytes(raw)
 return {'card':f.name}
def reassign(root,data):
 """改学生（拍错人时用）：{ids, student}。手机传来的改旁边的 json；相机导入的改导入记录。原文件不动。"""
 import 账本存取
 ids=(data or {}).get('ids')
 names=[str(n).strip() for n in ((data or {}).get('students') or [(data or {}).get('student','')])]  # students＝班课一起记给几个人
 if not isinstance(ids,list) or not ids or len(ids)>500 or not names or len(names)>30:raise ValueError('请求无效')
 roster=账本存取.roster(root)
 for n in names:
  if n not in roster:raise ValueError('名单里没有“%s”'%n)
 whos=[{'id':n,'name':n} for n in names];name=names[0]
 for i in ids:
  if str(i).startswith('final/'):continue
  if str(i).startswith('camera/'):
   import 相机导入;rid=str(i)[7:]
   相机导入.save_record_field(root,rid,students=names)
   continue
  src=resolve(root,i);side=src.with_suffix(src.suffix+'.json')
  try:rec=json.loads(side.read_text()) if side.exists() else {}
  except Exception:rec={}
  rec['students']=whos;rec['student']=whos[0]
  存取公共.write_json(side,rec,indent=None)
 return listing(root)
def set_status(root,data):
 ids=data.get('ids');status=data.get('status')
 if not isinstance(ids,list) or not ids or len(ids)>500 or status not in STATUS:raise ValueError('请求无效')
 for i in ids:resolve(root,i)
 _,state,_,backups=paths(root)
 with LOCK:
  ensure(state,{'version':1,'items':{}});obj,rev=read(state)
  for i in ids:obj['items'].setdefault(i,{})['status']=status
  write(state,obj,rev,backups,'收件箱状态')
 return listing(root)
def mark_sent(root,items,student):
 """“已发”按人记：一条资料只属于一个人的直接标“已发家长”；班课共用的记下发给了谁，全班都发过才标“已发家长”。"""
 if not items:return
 _,state,_,backups=paths(root)
 with LOCK:
  ensure(state,{'version':1,'items':{}});obj,rev=read(state)
  for x in items:
   rec=obj['items'].setdefault(x['id'],{});to=set(rec.get('sentTo',[]))|{student}
   if len(x['students'])>1:rec['sentTo']=sorted(to)
   if to>=set(x['students']):rec['status']='已发家长'
  write(state,obj,rev,backups,'收件箱状态')
def stage(root,data):
 """把选中的资料复制到整理文件夹（不动原文件）。target=edit：待剪辑；target=parent：发家长，附文字说明。"""
 ids=data.get('ids');target=data.get('target')
 if not isinstance(ids,list) or not ids or len(ids)>500 or target not in ('edit','parent'):raise ValueError('请求无效')
 meta={x['id']:x for x in scan(root)};chosen=[]
 for i in ids:
  resolve(root,i)
  if i in meta:chosen.append(meta[i])
 _,_,out,_=paths(root);upload=paths(root)[0];made={}
 for x in chosen:
  student=clean(x['students'][0]);day=x['date'][:10]
  import 学生档案
  folder=学生档案.edit_folder(student,day) if target=='edit' else (out/'发家长'/(student+'_'+day))
  folder.mkdir(parents=True,exist_ok=True);made.setdefault(folder,[]).append(x)
  if x['kind'] in ('video','photo','voice'):
   import 素材编辑;source=素材编辑.send_path(root,x['id']);orig=resolve(root,x['id']);dest=folder/(orig.stem+source.suffix)  # 用原来的文件名（改好的那份也一样）
   if dest.exists() and dest.stat().st_size!=source.stat().st_size:dest=folder/(source.stem+'_'+x['date'][11:19].replace(':','')+source.suffix)
   if dest.is_symlink() or dest.exists():continue
   if target=='edit' or x['id'].startswith('camera/'):dest.symlink_to(source)  # 剪辑文件夹（Mac 本地）一律放替身  # 相机视频很大，整理文件夹里只放替身（指向 Mac 本地的素材），不复制进 iCloud
   else:shutil.copy2(source,dest)
 if target=='parent':
  for folder,group in made.items():
   notes=[x for x in group if x['text'].strip()]
   if notes:(folder/'文字说明.txt').write_text(compose(group[0]['students'][0],group[0]['date'][:10],notes,lessons(root,group))+'\n')
 if target=='edit':set_status(root,{'ids':[x['id'] for x in chosen],'status':'待剪辑'})
 return {'folders':[str(f.relative_to(paths(root)[2].parent)) if target=='parent' else '' for f in made],'editFolders':[str(f) for f in made] if target=='edit' else [],'count':len(chosen),'listing':listing(root)}
WEEK=['周一','周二','周三','周四','周五','周六','周日']
def compose(name,day,notes,times):
 """和服务管理“按课汇总”一样：第一行 学生 日期 星期 上课时间 上课内容；后面一条一条 1. 2. 3.（去掉原来自己写的编号）。"""
 d=datetime.date.fromisoformat(day);time=times.get(day+'|'+name,'')
 points=[re.sub(r'^[(（]?\d{1,2}[.、．)）:：]\s*','',t.strip()) for x in sorted(notes,key=lambda y:y['date']) for t in x['text'].splitlines()]
 points=[t for t in points if t]
 return '\n'.join(['%s %d月%d日 %s%s 上课内容'%(name,d.month,d.day,WEEK[d.weekday()],' '+time if time else '')]+['%d. %s'%(i+1,t) for i,t in enumerate(points)])
def open_folder(root,data):
 """在 Finder 里打开整理文件夹或某份资料所在位置。"""
 out=paths(root)[2].resolve();target=data.get('folder');item=data.get('id')
 import 跨平台
 if item:path=resolve(root,item);跨平台.reveal(path)
 else:
  path=(paths(root)[0].parent/str(target or '整理')).resolve()
  if path!=out and out not in path.parents:raise ValueError('只能打开“整理”里的文件夹')
  out.mkdir(parents=True,exist_ok=True);path.mkdir(parents=True,exist_ok=True);跨平台.open_path(path)
 return {'opened':True}
def mime(path):return mimetypes.guess_type(path.name)[0] or ('audio/mp4' if path.suffix.lower()=='.m4a' else 'application/octet-stream')
