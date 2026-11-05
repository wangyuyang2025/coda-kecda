"""打点认领（10-23 用户定）：手机网页版上点学生名字＝记下“谁、从几点开始拍”，切回网页（或再点一下）＝记下结束。
视频用 iPhone 自带相机拍，不经过网页传；之后视频到了 Mac（相机导入、隔空投送……），按拍摄时间落在哪段打点里，就认给那个学生。
- 存在 资料/打点.json：{version, marks:{编号: {id, students, course, week, date, start, end, by, at}}}；
- 编号是手机生成的，同一条再交一次（没网时排队、补交）只会更新，不会多出一条；
- start / end 是手机当地的钟点（“2026-10-23T17:05:12”，不带时区），和相机拍摄时间一样按当地时间比；
- 没有结束时间的：算到 开始+30 分钟 和 下一条打点开始 之间较早的那个。"""
import datetime,json,re,threading
import 存取公共
LOCK=threading.Lock()
SLACK=datetime.timedelta(minutes=2)          # 开始前、结束后各放宽 2 分钟（切相机、手机钟和相机钟差一点）
OPEN=datetime.timedelta(minutes=30)          # 没记结束时最多算 30 分钟
TIME=re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$')
def path(root):return 存取公共.data_dir(root)/'打点.json'
def load(root):
 try:return json.loads(path(root).read_text(encoding='utf-8'))
 except Exception:return {'version':1,'marks':{}}
def save(root,data):
 """{id, students:[…], course, week, date, start, end?, by}，或 {id, remove:true} 撤掉一条。"""
 d=data if isinstance(data,dict) else {}
 mid=str(d.get('id',''))
 if not re.fullmatch(r'[A-Za-z0-9-]{8,64}',mid):raise ValueError('打点编号不对')
 with LOCK:
  obj=load(root);marks=obj.setdefault('marks',{})
  if d.get('remove'):
   marks.pop(mid,None);存取公共.write_json(path(root),obj);return {'ok':True}
  names=[str(n)[:20] for n in d.get('students') or [] if str(n).strip()]
  if not names or len(names)>20:raise ValueError('打点要有学生')
  start=str(d.get('start',''))[:19];end=str(d.get('end') or '')[:19]
  if not TIME.match(start) or (end and not TIME.match(end)):raise ValueError('打点时间不对')
  if end and end<start:raise ValueError('结束比开始还早')
  roster=set(json.loads((存取公共.data_dir(root)/'学生名单.json').read_text(encoding='utf-8')))
  if any(n not in roster for n in names):raise ValueError('名单里没有：'+'、'.join(n for n in names if n not in roster))
  old=marks.get(mid,{})
  marks[mid]={'id':mid,'students':names,'course':str(d.get('course') or '')[:40],'week':str(d.get('week') or '')[:10],'date':start[:10],
   'start':start,'end':end or old.get('end',''),'by':'手机' if d.get('by')=='手机' else 'Mac','at':old.get('at') or 存取公共.now_aware().isoformat(timespec='seconds')}
  存取公共.write_json(path(root),obj)
 return {'ok':True,'mark':marks[mid]}
def listing(root,since=None):
 items=sorted(load(root).get('marks',{}).values(),key=lambda m:m['start'])
 return [m for m in items if not since or m['date']>=since]
def windows(root):
 """每条打点实际覆盖的时间段（已经放宽、没结束的已经补上）。"""
 items=listing(root);out=[]
 for i,m in enumerate(items):
  a=datetime.datetime.fromisoformat(m['start'])
  if m.get('end'):b=datetime.datetime.fromisoformat(m['end'])
  else:
   b=a+OPEN
   nxt=next((datetime.datetime.fromisoformat(x['start']) for x in items[i+1:] if x['start']>m['start']),None)
   if nxt and nxt<b:b=nxt
  out.append((a-SLACK,b+SLACK,m))
 return out
def covering(t,wins):
 """拍摄时间 t（当地时间，不带时区）落在哪条打点里；几条都盖住时取开始最晚的（最近点的那个名字）。"""
 hits=[m for a,b,m in wins if a<=t<=b]
 return max(hits,key=lambda m:m['start']) if hits else None
