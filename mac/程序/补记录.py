"""缺记录（10-20）：从每个学生的起点（起始余额那天）到昨天，课表上有课、账本里却没有“上课”也没有“请假”的，列出来请老师确认。
缺记录通常有两种原因：
1. 起点登记得不对（比如老课表的起点定在 6 月，其实那之后的课早已算进余额）→ 改起点：截至某天还剩几节，起点之前的缺口自然消失；
2. 真的漏记了 → 一节节选：上课（扣课时）/ 请假 / 没这节课（以后不再提醒，记在 数据/缺记录确认.json）/ 补录时间（这节挪到别的时间上了，按填的日期钟点记上课）。
课表只能按现在的固定课表 + 每周临时安排往回推，所以以前课表不一样时会多算，老师选“没这节课”就好。
暂停上课的学生，从暂停那天起不算。"""
import datetime,hashlib,json,os
import 存取公共
from 存取公共 import data_dir,LOCK
import 账本存取,签课表,周调整存取,学生状态,课包
def path(root):return data_dir(root)/'缺记录确认.json'
def load(root):
 try:return json.loads(path(root).read_text())
 except Exception:return {'version':1,'dismissed':{}}
def key(name,date,time):return name+'|'+date+'|'+time.replace('–','-')
def starts(root):
 """每个学生的起点：最新那条没撤销的起始余额。"""
 S=账本存取.summary(root);out={}
 for t in reversed(S['transactions']):   # summary 里是新的在前，倒过来按时间
  if t['kind']=='opening' and not t['voided']:out[t['student']]=t
 return S,out
def scan(root,only=None):
 S,start=starts(root);today=str(存取公共.today())
 live=[t for t in S['transactions'] if not t['voided'] and t['kind'] in ('lesson','leave','noshow')]   # 11-05：旷课也算记过
 days={(t['student'],t['date']) for t in live}
 kinds={(t['student'],t['date']):('上课' if t['kind']=='lesson' else '请假' if t['kind']=='leave' else '旷课') for t in live}
 paused=学生状态.load(root).get('paused',{});gone=load(root).get('dismissed',{});pkgs=课包.load(root)['packages']
 names=set(账本存取.roster(root))
 todo={n:o for n,o in start.items() if n in names and (only is None or n==only)}
 if not todo:return {}
 first=min(o['date'] for o in todo.values());out={}
 mon=周调整存取.monday(datetime.date.fromisoformat(first));end=存取公共.today()
 while mon<=end:
  try:_,entries=签课表.entries_for_week(root,str(mon))
  except Exception:entries=[]
  same={}
  for e in entries:same.setdefault((e.get('course'),e['date']),[]).append(e['name'])
  for e in entries:
   n,d=e['name'],e['date']
   if n not in todo or d<=todo[n]['date'] or d>=today:continue
   if n in paused and d>=paused[n]:continue
   if (n,d) in days or key(n,d,e['time']) in gone:continue
   if any(p['student']==n and p['start']<=d<=p['end'] for p in pkgs):continue   # 课包期间按周扣，不算缺
   item={'date':d,'day':e['day'],'time':e['time'],'units':e.get('units',1) if e.get('units') in (1,2) else 1,'course':e.get('course')}
   if only:   # 同班同学那天来没来，补记录时对照（找不到记录时问同班同学也行）
    item['classmates']=[{'name':m,'status':kinds.get((m,d)) or ('没这节课' if key(m,d,e['time']) in gone else '没记')} for m in same.get((e.get('course'),d),[]) if m!=n]
   out.setdefault(n,[]).append(item)
  mon+=datetime.timedelta(days=7)
 for n in out:out[n].sort(key=lambda x:(x['date'],x['time']))
 return out
def overview(root):
 """课时管理页用：{学生: {count, start:{date,delta,note}}}"""
 _,start=starts(root);gaps=scan(root)
 return {'students':{n:{'count':len(v),'start':{k:start[n].get(k) for k in ('date','delta','note','id')}} for n,v in gaps.items()},'total':sum(map(len,gaps.values()))}
def detail(root,name):
 if name not in 账本存取.roster(root):raise ValueError('没有这个学生')
 _,start=starts(root);o=start.get(name)
 S=账本存取.summary(root);since=o['date'] if o else ''
 recorded=[{'date':t['date'],'time':t.get('time') or '','kind':'上课' if t['kind']=='lesson' else '请假' if t['kind']=='leave' else '旷课'} for t in reversed(S['transactions']) if t['student']==name and not t['voided'] and t['kind'] in ('lesson','leave','noshow') and t['date']>=since]  # 11-05：已登记的上课/请假（含时间），补记录时对照
 recorded.sort(key=lambda x:(x['date'],x['time']))
 return {'name':name,'start':{k:o.get(k) for k in ('date','delta','note','id')} if o else None,'items':scan(root,name).get(name,[]),'recorded':recorded}
def resolve(root,data):
 """逐节确认：status 是 上课 / 请假 / 没上。上课、请假写进账本；没上 记下来，以后不再提醒。"""
 d=data or {};name=d.get('name');items=d.get('items')
 if name not in 账本存取.roster(root):raise ValueError('没有这个学生')
 if not isinstance(items,list) or not 1<=len(items)<=500:raise ValueError('请至少选一节')
 known={(x['date'],x['time']):x for x in scan(root,name).get(name,[])}
 txs,skip,pkg=[],[],{}
 for it in items:
  if not isinstance(it,dict):raise ValueError('请求无效')
  slot=known.get((it.get('date'),it.get('time')))
  if not slot:continue   # 已经补过了
  st=it.get('status')
  if st not in ('上课','请假','没上','改时间','课包'):raise ValueError('请为每一节选 上课 / 请假 / 没这节课')
  if st=='课包':   # 10-27：这一周按课包扣（老师填这周扣几节），这周的缺记录就不再一节节补
   n=it.get('perWeek');m=str(课包.monday(datetime.date.fromisoformat(slot['date'])))
   if pkg.get(m,n)!=n:raise ValueError('同一周的课包节数要一样')
   pkg[m]=n;continue
  if st=='没上':skip.append(key(name,slot['date'],slot['time']));continue
  if st=='改时间':   # 10-27：这节其实挪到别的日子/钟点上了（课在中间换过时间）→ 按填的时间记上课，原来那格不再提醒
   at=moved(slot,it);skip.append(key(name,slot['date'],slot['time']))
   txs.append({'id':'gap-'+hashlib.sha1((key(name,slot['date'],slot['time'])+'>'+at[0]+' '+at[1]).encode()).hexdigest()[:16],'kind':'lesson','student':name,'date':at[0],'units':slot['units'],'time':at[1],
    'note':'补记录（课表 %s %s，实际 %s %s）'%(slot['date'],slot['time'].replace('–','-'),at[0],at[1])});continue
  txs.append({'id':'gap-'+hashlib.sha1(key(name,slot['date'],slot['time']).encode()).hexdigest()[:16],'kind':'lesson' if st=='上课' else 'leave','student':name,'date':slot['date'],'units':slot['units'],'time':slot['time'].replace('–','-'),'note':'补记录'})
 for m,n in sorted(pkg.items()):课包.add_week(root,name,datetime.date.fromisoformat(m),n)
 if pkg:课包.sync(root)
 if txs:账本存取.add_batch(root,{'items':txs})
 if skip:
  with LOCK:
   obj=load(root);now=存取公共.now_aware().isoformat(timespec='seconds')
   for k in skip:obj.setdefault('dismissed',{})[k]={'at':now}
   存取公共.write_json(path(root),obj)
 return dict(detail(root,name),saved=len(txs),skipped=len(skip),packaged=len(pkg),overview=overview(root))
def moved(slot,it):
 """补录时间：新日期 + 新开始钟点，下课时间按原来那节的长度顺延。"""
 try:day=datetime.date.fromisoformat(str(it.get('newDate','')))
 except ValueError:raise ValueError('补录时间：日期不对')
 if day>=存取公共.today():raise ValueError('补录时间：只能补今天以前的课')
 hm=str(it.get('newTime',''))
 try:h,m=map(int,hm.split(':'));assert 0<=h<24 and 0<=m<60
 except Exception:raise ValueError('补录时间：钟点不对（例如 17:30）')
 a,_,b=slot['time'].replace('–','-').partition('-')
 try:dur=(int(b[:2])*60+int(b[3:5]))-(int(a[:2])*60+int(a[3:5]))
 except Exception:dur=0
 s=h*60+m;t='%02d:%02d'%(h,m)
 if dur>0:e=min(s+dur,1439);t+='-%02d:%02d'%(e//60,e%60)
 return str(day),t
def restart(root,data):
 """起点登记得不对：改成“截至某天（含这天的记录）还剩几节”。旧起点撤销（流水里看得到），新起点按那天之前已有的记录倒推，让那天的余额正好是填的数。"""
 d=data or {};name=d.get('name')
 if name not in 账本存取.roster(root):raise ValueError('没有这个学生')
 try:day=datetime.date.fromisoformat(str(d.get('date','')))
 except ValueError:raise ValueError('日期不对')
 if day>存取公共.today():raise ValueError('起点不能是以后的日期')
 left=d.get('remaining')
 if isinstance(left,bool) or not isinstance(left,int) or not -500<=left<=500:raise ValueError('请填那天还剩几节课（整数，欠课填负数）')
 S,start=starts(root);old=start.get(name)
 if old:账本存取.void(root,{'id':old['id'],'note':'改起点：截至 %s 剩 %d 节'%(day,left)})
 S=账本存取.summary(root)
 before=sum(t['delta'] for t in S['transactions'] if t['student']==name and t['kind'] not in ('opening',) and not t['voided'] and t['kind']!='void' and t['date']<=str(day))
 账本存取.add(root,{'id':'restart-'+os.urandom(6).hex(),'kind':'opening','student':name,'date':str(day),'delta':left-before,'note':'改起点：截至 %s 剩 %d 节'%(day,left)})
 return dict(detail(root,name),overview=overview(root))
