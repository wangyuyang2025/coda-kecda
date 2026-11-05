"""纸质课表存档：以前一人一张的老课表（没有定位黑角，不能自动识别），拍照后先放“待归档”，在 Mac 上一张张看图选学生归档；需要时从课时单里复制发家长。
文件：数据/纸质课表/待归档/（等归档）、数据/纸质课表/<学生名>/（已归档，记录.json 记着每张的最后上课日期和余课）、数据/纸质课表/不要的/（拍坏或不需要的，不删除）。
归档时把“最后一次上课后剩几节”作为这个学生在系统里的起点（起始余额），之后的缴费、上课都在系统里记；可同时标“暂停上课”。"""
import datetime,hashlib,json,os,re,shutil
import 存取公共
from 存取公共 import data_dir
from pathlib import Path
import 账本存取,学生状态
IMAGES=('.jpg','.jpeg','.png','.heic','.pdf')
SAFE=re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,160}$')
def base(root):
 b=data_dir(root)/'纸质课表';(b/'待归档').mkdir(parents=True,exist_ok=True);return b
def files(folder):
 return sorted((p for p in folder.glob('*') if p.is_file() and p.suffix.lower() in IMAGES),key=lambda p:p.name)
def keep(root,raw,name):
 """手机传来但不是签课表的照片，放进待归档。"""
 name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',Path(str(name)).name)[:120] or '照片.jpg'
 target=base(root)/'待归档'/(存取公共.now().strftime('%Y%m%d_%H%M%S_')+name)
 n=1
 while target.exists():target=target.with_name(target.stem+'_%d'%n+target.suffix);n+=1
 target.write_bytes(raw);return target.name
def pending(root):
 bin_=sorted(files(base(root)/'不要的'),key=lambda p:p.stat().st_ctime,reverse=True) if (base(root)/'不要的').is_dir() else []
 return {'files':[p.name for p in files(base(root)/'待归档')],'students':账本存取.roster(root),'dropped':[p.name for p in bin_]}
def notes(folder):
 p=folder/'记录.json'
 try:return json.loads(p.read_text())
 except Exception:return {}
def of_student(root,name):
 """这个学生已归档的老课表，按最后上课日期排。"""
 if name not in 账本存取.roster(root):raise ValueError('没有这个学生')
 folder=base(root)/name;info=notes(folder)
 items=[dict({'file':p.name},**info.get(p.name,{})) for p in files(folder)] if folder.is_dir() else []
 return {'files':[x['file'] for x in sorted(items,key=lambda x:x.get('date',''))],'items':sorted(items,key=lambda x:x.get('date',''))}
def resolve(root,where,name):
 """where 是 待归档 或学生名；只允许读这两类文件夹里的图片。"""
 b=base(root).resolve()
 if where not in ('待归档','不要的') and where not in 账本存取.roster(root):raise ValueError('找不到这张图')
 p=(b/where/Path(str(name)).name).resolve()
 if p.parent!=b/where or not SAFE.match(p.name) or p.suffix.lower() not in IMAGES or not p.is_file():raise ValueError('找不到这张图')
 return p
def start(root,student,day,left,fname):
 """老课表的余课作为起点。已有更晚的老课表起点、或手动登记过的起始余额就不动；已有更早的老课表起点，换成这张更晚的。"""
 live=[t for t in 账本存取.summary(root)['transactions'] if t['student']==student and t['kind']=='opening' and not t['voided']]
 if live:
  t=live[0]
  if not t['id'].startswith('paper-'):return '已有手动登记的起始余额，这张只存档'
  if t['date']>=str(day):return '已有更晚的老课表起点，这张只存档'
  账本存取.void(root,{'id':t['id'],'note':'换成更晚的老课表（'+str(day)+'）'})
 账本存取.add(root,{'id':'paper-'+hashlib.sha1((student+'|'+fname+'|'+str(day)).encode()).hexdigest()[:12],'kind':'opening','student':student,'date':str(day),'delta':left,'note':'老课表 '+str(day)+' 最后一次上课后'})
 return '已作为起点：剩 %d 节'%left
def file(root,data):
 """归档到学生名下（要填最后一次上课日期和那时的余课），或放进“不要的”。"""
 src=resolve(root,'待归档',(data or {}).get('file',''));student=data.get('student');info=None
 if student=='不要的':dest=base(root)/'不要的'
 elif isinstance(student,str) and student.strip():
  student=student.strip()
  if student not in 账本存取.roster(root):
   if not data.get('create'):raise ValueError('名单里没有这个学生')
   学生状态.ensure_students(root,[student])  # 名单里没有：直接新建
  dest=base(root)/student
  try:day=datetime.date.fromisoformat(str(data.get('date','')))
  except ValueError:raise ValueError('请填最后一次上课的日期')
  left=data.get('remaining')
  if isinstance(left,bool) or not isinstance(left,int) or not -500<=left<=500:raise ValueError('请填那时剩几节课（整数，欠课填负数）')
  info={'date':str(day),'remaining':left}
  # 先登记起点：失败就不动图片，免得归档了一半
  info['start']=start(root,student,day,left,src.name)
 else:raise ValueError('请选一个学生')
 dest.mkdir(parents=True,exist_ok=True);target=dest/src.name
 if target.exists():target=dest/(src.stem+'_'+存取公共.now().strftime('%H%M%S%f')+src.suffix)
 shutil.move(str(src),str(target))
 if info:
  book=notes(dest);book[target.name]=info;存取公共.write_json(dest/'记录.json',book)
  if data.get('paused'):学生状态.set_paused(root,{'name':student,'paused':True,'since':info['date']})
 return dict(pending(root),result=info['start'] if info else '已放进“不要的”',moved=target.name)
def restore(root,data):
 """“不要的”里的照片放回待归档（点错了“不要”时用）。"""
 src=resolve(root,'不要的',(data or {}).get('file',''));dest=base(root)/'待归档'/src.name
 if dest.exists():dest=dest.with_name(src.stem+'_'+存取公共.now().strftime('%H%M%S%f')+src.suffix)
 shutil.move(str(src),str(dest))
 return dict(pending(root),result='已放回待归档',moved=dest.name)
