"""从相机导入：插上相机存储卡（或相机用 USB 连 Mac），按拍摄时间对课表，把上课时拍的视频照片归到学生，确认后复制进来。
- 卡上的原文件只读不动；复制到 Mac 本地 ~/Movies/课程与签到_相机素材/日期/（视频很大，不放 iCloud 同步的项目文件夹），
  导入记录在 数据/相机导入.json，收件箱（服务管理）里和手机传来的资料一起显示。
- 索尼：视频 PRIVATE/M4ROOT/CLIP/C0001.MP4，旁边 C0001M01.XML 里有拍摄开始时间，THMBNL/ 里有缩略图；照片 DCIM/1xxMSDCF/DSC*.JPG（EXIF 时间）。
  其他相机的 DCIM 也认：照片读 EXIF，视频用文件时间。
- 拍摄时间按相机自己的钟（当地时间）算。相机时间不准时可以整批偏移；卡上没有这一周拍的、或大多对不上课，就先提示，不乱分。"""
import datetime,hashlib,json,os,re,shutil,struct,threading,uuid
from 存取公共 import data_dir
from pathlib import Path
import 周调整存取
from 存取公共 import LOCK,ensure,read,write
STORE=Path(os.environ.get('LESSON_CAMERA_STORE',str(Path.home()/'Movies'/'课程与签到_相机素材')))  # 测试时用别的文件夹
VIDEO={'.mp4','.mov','.mts','.m4v'};PHOTO={'.jpg','.jpeg','.arw','.heif','.hif','.heic'}
MARGIN=datetime.timedelta(minutes=10)  # 课前课后各留 10 分钟
def record_path(root):return data_dir(root)/'相机导入.json'
def volumes():
 """插着的、像相机卡的磁盘：有 DCIM 或 PRIVATE/M4ROOT 或 PRIVATE/AVCHD。"""
 out=[]
 for v in sorted(Path('/Volumes').iterdir()):
  try:
   if v.is_symlink() or not v.is_dir():continue
   if (v/'DCIM').is_dir() or (v/'PRIVATE'/'M4ROOT').is_dir() or (v/'PRIVATE'/'AVCHD').is_dir():out.append(v)
  except OSError:continue
 return out
def volume(name):
 for v in volumes():
  if v.name==name:return v
 raise ValueError('没找到这张卡，可能已经拔出')
# ---- 拍摄时间
def exif_time(path):
 """照片 EXIF 里的拍摄时间（DateTimeOriginal，相机当地时间）。JPG 和索尼 ARW（TIFF 结构）都认，读不到返回 None。"""
 try:raw=path.open('rb').read(512*1024)
 except OSError:return None
 base=None
 if raw[:2]==b'\xff\xd8':
  i=2
  while i+4<len(raw) and raw[i]==0xFF:
   marker,size=raw[i+1],struct.unpack('>H',raw[i+2:i+4])[0]
   if marker==0xE1 and raw[i+4:i+10]==b'Exif\x00\x00':base=i+10;break
   i+=2+size
 elif raw[:4] in (b'II*\x00',b'MM\x00*'):base=0
 if base is None:return None
 tiff=raw[base:];
 if len(tiff)<8:return None
 e='<' if tiff[:2]==b'II' else '>'
 def ifd(off):
  out={}
  if off+2>len(tiff):return out
  n=struct.unpack(e+'H',tiff[off:off+2])[0]
  for k in range(n):
   p=off+2+12*k
   if p+12>len(tiff):break
   tag,typ,cnt=struct.unpack(e+'HHI',tiff[p:p+8]);val=tiff[p+8:p+12]
   if typ==2:
    o=struct.unpack(e+'I',val)[0] if cnt>4 else None
    out[tag]=(tiff[o:o+cnt] if o is not None else val[:cnt]).split(b'\x00')[0].decode('ascii','ignore')
   elif typ==4:out[tag]=struct.unpack(e+'I',val)[0]
  return out
 try:
  first=ifd(struct.unpack(e+'I',tiff[4:8])[0]);sub=ifd(first[0x8769]) if 0x8769 in first else {}
  text=sub.get(0x9003) or sub.get(0x9004) or first.get(0x0132)
  return datetime.datetime.strptime(text.strip(),'%Y:%m:%d %H:%M:%S') if text else None
 except Exception:return None
def sony_xml_time(path):
 """索尼视频旁边的 C0001M01.XML：<CreationDate value="2026-10-11T08:12:30+08:00"/>，取相机当地时间部分。"""
 xml=path.with_name(path.stem+'M01.XML')
 if not xml.is_file():xml=path.with_name(path.stem+'M01.xml')
 try:m=re.search(r'CreationDate\s+value="(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)',xml.read_text(errors='ignore'))
 except OSError:return None
 return datetime.datetime.fromisoformat(m[1]) if m else None
def shot_time(path):
 ext=path.suffix.lower()
 t=sony_xml_time(path) if ext in VIDEO else exif_time(path)
 return (t,'相机记录') if t else (datetime.datetime.fromtimestamp(path.stat().st_mtime),'文件时间')
def thumb_of(path,vol):
 """索尼视频的缩略图：M4ROOT/THMBNL/C0001T01.JPG。"""
 if path.suffix.lower() in VIDEO:
  t=vol/'PRIVATE'/'M4ROOT'/'THMBNL'/(path.stem+'T01.JPG')
  return str(t.relative_to(vol)) if t.is_file() else None
 return str(path.relative_to(vol)) if path.suffix.lower() in ('.jpg','.jpeg') else None
def media_files(vol):
 roots=[vol/'PRIVATE'/'M4ROOT'/'CLIP',vol/'DCIM',vol/'PRIVATE'/'AVCHD']
 for r in roots:
  if not r.is_dir():continue
  for f in sorted(r.rglob('*')):
   if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in VIDEO|PHOTO:yield f
# ---- 对课表
def lessons_on(day,cache):
 mon=str(周调整存取.monday(day))
 if mon not in cache:
  try:cache[mon]=周调整存取.load(cache['root'],mon)['effective']
  except Exception:cache[mon]=[]
 return [r for r in cache[mon] if r['day']==周调整存取.DAYS[day.weekday()]]
def match(t,cache):
 """这个时间在上哪节课：[{course, time, students}]（可能 0 节、1 节或几节同时）。"""
 inside,near=[],[]
 for r in lessons_on(t.date(),cache):
  a=datetime.datetime.combine(t.date(),datetime.time.fromisoformat(r['start']));b=datetime.datetime.combine(t.date(),datetime.time.fromisoformat(r['end']))
  hit={'course':r['id'],'time':r['start']+'–'+r['end'],'students':r['studentNames']}
  if a<=t<b:inside.append(hit)
  elif a-MARGIN<=t<=b+MARGIN:near.append(hit)
 return inside or near  # 正在上的课优先；课前课后 10 分钟只在没有正在上的课时才算（连着上的课不会两边都算）
def teacher_now(root):
 """老师那边的“现在”：这台 Mac 的时区可能和上课当地不同，用手机传来的资料（文件名里是手机当地时间）推算时差。"""
 import 收件箱
 now=datetime.datetime.now(datetime.timezone.utc)
 for x in 收件箱.scan(root):
  m=re.search(r'_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_',x['file'])
  side=收件箱.paths(root)[0]/(x['id']+'.json')
  try:rec=json.loads(side.read_text());value=rec.get('date')
  except Exception:continue
  if m and isinstance(value,(int,float)):
   local=datetime.datetime.fromisoformat('%s %s:%s:%s'%m.groups());utc=datetime.datetime.fromtimestamp(收件箱.APPLE_EPOCH+value,datetime.timezone.utc).replace(tzinfo=None)
   offset=round((local-utc).total_seconds()/900)*900
   return (now.replace(tzinfo=None)+datetime.timedelta(seconds=offset))
 return datetime.datetime.now()
def imported_keys(root):
 p=record_path(root)
 return {r.get('key') for r in json.loads(p.read_text()).get('items',[])} if p.exists() else set()
def key_of(path):
 st=path.stat();return hashlib.sha1(('%s|%d|%d'%(path.name,st.st_size,int(st.st_mtime))).encode()).hexdigest()[:16]
def scan(root,data):
 """读卡：{volume, offset(分钟)} → 每个文件的拍摄时间、对上的课、建议的学生；再给出检查结果（这周有没有拍的、对上课的比例、建议的整批偏移）。"""
 data=data or {};vol=volume(data.get('volume'));offset=datetime.timedelta(minutes=int(data.get('offset') or 0))
 if abs(offset)>datetime.timedelta(days=400):raise ValueError('偏移太大')
 now=teacher_now(root);monday=周调整存取.monday(now.date());since=monday-datetime.timedelta(days=7)
 cache={'root':root};done=imported_keys(root);files=[]
 import 打点;wins=打点.windows(root)   # 手机网页版上点过名字的时间段：落在里面的直接认给那个学生，比按课表猜准
 for f in media_files(vol):
  raw,source=shot_time(f);t=raw+offset;k=key_of(f)
  m=match(t,cache) if t.date()>=since else []
  mk=打点.covering(t.replace(tzinfo=None),wins) if t.date()>=since else None
  files.append({'path':str(f.relative_to(vol)),'name':f.name,'kind':'video' if f.suffix.lower() in VIDEO else 'photo','size':f.stat().st_size,
   'shot':t.isoformat(timespec='seconds'),'source':source,'lessons':m,'students':mk['students'] if mk else m[0]['students'] if len(m)==1 else [],'mark':mk['id'] if mk else None,
   'thumb':thumb_of(f,vol),'imported':k in done,'recent':t.date()>=since,'future':t>now+datetime.timedelta(minutes=30)})
 recent=[x for x in files if x['recent']];this_week=[x for x in recent if x['shot'][:10]>=str(monday)]
 matched=[x for x in recent if x['lessons'] or x['mark']]
 checks=[]
 if not files:checks.append('这张卡上没有找到视频或照片，是不是插错卡了？')
 elif not this_week:checks.append('卡上没有这一周（%s 起）拍的视频照片。是不是插错卡了？或者相机时间不准？最新一个是 %s 拍的。'%(monday.strftime('%m/%d'),max(x['shot'] for x in files)[:16].replace('T',' ')))
 if any(x['future'] for x in files):checks.append('有 %d 个文件的拍摄时间比现在还晚，相机时间大概不准。'%sum(x['future'] for x in files))
 suggest=None
 if recent and len(matched)<len(recent)*0.5 or (files and not this_week):suggest=suggest_offset(root,vol,offset,len(matched))
 if suggest:checks.append('试试相机时间 %s：能对上课的从 %d 个变成 %d 个。'%(suggest['label'],len(matched),suggest['matched']))
 return {'volume':vol.name,'offset':int(offset.total_seconds()//60),'now':now.isoformat(timespec='minutes'),'since':str(since),'files':files,
  'older':len(files)-len(recent),'checks':checks,'suggest':suggest,'store':str(STORE)}
def suggest_offset(root,vol,current,best_now):
 """相机时间不准时，试整小时（±48 小时）和常见的整分钟，看哪个偏移能让最多文件对上课。"""
 times=[shot_time(f)[0] for f in media_files(vol)][-200:]
 if not times:return None
 cache={'root':root};best=None
 for h in range(-48,49):
  off=datetime.timedelta(hours=h)
  if off==current:continue
  n=sum(1 for t in times if match(t+off,cache))
  if n>best_now and (not best or n>best['matched']):best={'minutes':h*60,'matched':n,'label':'不调整（改回 0）' if h==0 else ('往后 ' if h>0 else '往前 ')+str(abs(h))+' 小时'}
 return best
# ---- 复制进来（后台慢慢复制，页面看进度）
JOB={'running':False}
def start_import(root,data):
 """{volume, items:[{path, students, shot, kind}]} → 后台复制到 ~/Movies/课程与签到_相机素材/日期/，写导入记录。"""
 items=(data or {}).get('items');vol=volume((data or {}).get('volume'))
 if not isinstance(items,list) or not items or len(items)>500:raise ValueError('请先勾选要导入的')
 import 账本存取;names=set(账本存取.roster(root));plan=[]
 for x in items:
  src=(vol/str(x.get('path',''))).resolve()
  if vol.resolve() not in src.parents or not src.is_file():raise ValueError('找不到卡上的文件：'+str(x.get('path')))
  people=x.get('students')
  if not isinstance(people,list) or not people or any(n not in names for n in people):raise ValueError(src.name+'：请先选学生')
  shot=datetime.datetime.fromisoformat(str(x.get('shot')))
  plan.append((src,people,shot,'video' if src.suffix.lower() in VIDEO else 'photo'))
 with LOCK:
  if JOB.get('running'):raise ValueError('上一批还在复制，请等它完成')
  JOB.clear();JOB.update(running=True,total=sum(p[0].stat().st_size for p in plan),done=0,count=len(plan),copied=0,current='',errors=[])
 threading.Thread(target=copy_all,args=(root,plan),daemon=True).start()
 return progress(root)
def copy_all(root,plan):
 try:
  for src,people,shot,kind in plan:
   JOB['current']=src.name
   try:
    folder=STORE/shot.strftime('%Y-%m-%d');folder.mkdir(parents=True,exist_ok=True)
    dest=folder/('%s_%s_%s'%(people[0],shot.strftime('%H-%M-%S'),src.name))
    if not (dest.exists() and dest.stat().st_size==src.stat().st_size):
     tmp=dest.with_name(dest.name+'.copying')
     with src.open('rb') as a,tmp.open('wb') as b:
      while chunk:=a.read(8<<20):b.write(chunk);JOB['done']+=len(chunk)
     shutil.copystat(src,tmp);tmp.replace(dest)
    else:JOB['done']+=src.stat().st_size
    add_record(root,{'id':uuid.uuid4().hex[:16],'key':key_of(src),'path':str(dest),'students':people,'date':shot.isoformat(timespec='seconds'),'kind':kind,'size':dest.stat().st_size,'source':src.name})
    JOB['copied']+=1
   except Exception as e:JOB['errors'].append(src.name+'：'+str(e))
 finally:JOB['running']=False;JOB['current']=''
def add_record(root,rec):
 p=record_path(root)
 with LOCK:
  ensure(p,{'version':1,'items':[]});obj,rev=read(p)
  obj['items']=[r for r in obj['items'] if r.get('key')!=rec['key']]+[rec]
  write(p,obj,rev,data_dir(root)/'备份','相机导入')
def save_record_field(root,rid,**fields):
 """改一条相机导入记录（比如改学生）。"""
 p=record_path(root)
 with LOCK:
  ensure(p,{'version':1,'items':[]});obj,rev=read(p)
  hit=[r for r in obj['items'] if r.get('id')==rid]
  if not hit:raise ValueError('找不到这份相机素材')
  hit[0].update(fields);write(p,obj,rev,data_dir(root)/'备份','相机导入')
def progress(root):return {k:v for k,v in JOB.items()}
def records(root):
 p=record_path(root)
 return json.loads(p.read_text()).get('items',[]) if p.exists() else []
def record_file(root,rid):
 """收件箱里 camera/<编号> 对应的本地文件（只认 素材文件夹 里的）。"""
 for r in records(root):
  if r['id']==rid:
   path=Path(r['path']).resolve()
   if STORE.resolve() in path.parents and path.is_file():return path
 raise ValueError('找不到这份相机素材（可能被移走了）')
def card_file(data):
 """预览卡上的缩略图 / 照片：{volume, path}，只认这张卡里的文件。"""
 vol=volume(data.get('volume'));p=(vol/str(data.get('path',''))).resolve()
 if vol.resolve() not in p.parents or not p.is_file():raise ValueError('找不到卡上的文件')
 return p
