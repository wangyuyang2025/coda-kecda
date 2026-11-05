"""课包（10-20 用户定，方案 A + 按周扣，和平时课时同一本账）：
比如暑假 7/1–8/31 每周 4 节。这段时间不按课表一节节扣、不算缺记录，而是按周扣：
- 每周默认扣“每周节数”（4）；某周请了假，可以把那周改成实际来的节数（比如 2），一周最多扣每周节数；
- 一周过完（到周日）才扣；扣的时候记一条“手动调整”到账本（编号 pkg-课包编号-那周周一），流水和课时单里看得到；
- 改了某周的节数、或删掉课包，已经扣过的那条会撤销再按新的记（历史都留着）。
交钱照常记“缴费”。文件：资料/课包.json。"""
import datetime,json,os
import 存取公共
from 存取公共 import data_dir,LOCK
import 账本存取
def path(root):return data_dir(root)/'课包.json'
def load(root):
 try:return json.loads(path(root).read_text(encoding='utf-8'))
 except Exception:return {'version':1,'packages':[]}
def monday(d):return d-datetime.timedelta(days=d.weekday())
def weeks(p):
 """课包覆盖的每一周（周一日期）。开始、结束那周不满一周也算一周。"""
 a,b=datetime.date.fromisoformat(p['start']),datetime.date.fromisoformat(p['end']);m=monday(a);out=[]
 while m<=b:out.append(m);m+=datetime.timedelta(days=7)
 return out
def week_count(p,m):
 v=(p.get('weeks') or {}).get(str(m))
 return p['perWeek'] if v is None else v
def covering(root,student,day):
 """这一天这个学生在不在课包期间（签课表、补记录、记上课用）。"""
 for p in load(root)['packages']:
  if p['student']==student and p['start']<=str(day)<=p['end']:return p
 return None
def view(p):
 today=存取公共.today()
 return dict(p,weekList=[{'monday':str(m),'sunday':str(m+datetime.timedelta(days=6)),'count':week_count(p,m),'state':'done' if m+datetime.timedelta(days=6)<today else 'now' if m<=today else 'later'} for m in weeks(p)])
def listing(root,student=None):
 sync(root)
 return {'packages':[view(p) for p in load(root)['packages'] if student in (None,'',p['student'])]}
def save_file(root,obj):存取公共.write_json(path(root),obj)
def sync(root):
 """把“该扣的”和账本对齐：过完的周按节数扣；节数改了、课包删了，就撤销旧的再记新的。重复调用没关系。"""
 obj=load(root);want={}
 today=存取公共.today()
 for p in obj['packages']:
  for m in weeks(p):
   if m+datetime.timedelta(days=6)>=today:continue   # 这周还没过完
   n=week_count(p,m)
   if n:want['pkg-%s-%s'%(p['id'],m)]=(p['student'],-n,'课包 %s 起这一周扣 %d 节%s'%(m.strftime('%m/%d'),n,'（'+p['note']+'）' if p.get('note') else ''),str(m+datetime.timedelta(days=6)))
 S=账本存取.summary(root);live={}
 for t in S['transactions']:
  if t['id'].startswith('pkg-') and t['kind']!='void' and not t['voided']:live[t['id'].split('#')[0]]=t
 for base,t in live.items():
  w=want.get(base)
  if not w or w[1]!=t['delta'] or w[0]!=t['student']:账本存取.void(root,{'id':t['id'],'note':'课包改了，重新按周扣'})
 S=账本存取.summary(root);ids={t['id'] for t in S['transactions']};still={t['id'].split('#')[0] for t in S['transactions'] if t['id'].startswith('pkg-') and t['kind']!='void' and not t['voided']}
 items=[]
 for base,(student,delta,note,day) in want.items():
  if base in still or student not in 账本存取.roster(root):continue
  k=1;tid=base
  while tid in ids:k+=1;tid='%s#%d'%(base,k)   # 撤销过的编号不能再用，加个序号
  items.append({'id':tid,'kind':'adjust','student':student,'date':day,'delta':delta,'note':note})
 if items:账本存取.add_batch(root,{'items':items})
def add_week(root,student,mon,n):
 """补记录里选“课包”（10-27 用户定）：那一周按课包扣 n 节。和前后紧挨着的补记录课包连成一个（每周节数都写死在 weeks 里），不然新建一个一周的。"""
 if isinstance(n,bool) or not isinstance(n,int) or not 1<=n<=20:raise ValueError('课包这周扣几节：1 到 20')
 obj=load(root);m=monday(mon);sun=m+datetime.timedelta(days=6)
 for p in obj['packages']:
  if p['student']==student and not (str(sun)<p['start'] or str(m)>p['end']):raise ValueError('%s 这周（%s 起）已经在课包 %s–%s 里了'%(student,m.strftime('%m/%d'),p['start'],p['end']))
 near=[p for p in obj['packages'] if p['student']==student and p.get('note')=='补记录' and (p['end']==str(m-datetime.timedelta(days=1)) or p['start']==str(sun+datetime.timedelta(days=1)))]
 if near:
  p=near[0];ws={str(w):week_count(p,w) for w in weeks(p)};ws[str(m)]=n
  p.update(start=min(p['start'],str(m)),end=max(p['end'],str(sun)),perWeek=max(ws.values()))
  p['weeks']={k:v for k,v in ws.items() if v!=p['perWeek']}
 else:obj['packages'].append({'id':os.urandom(4).hex(),'student':student,'start':str(m),'end':str(sun),'perWeek':n,'note':'补记录','weeks':{}})
 with LOCK:save_file(root,obj)
def save(root,data):
 """新建或修改一个课包：{id?, student, start, end, perWeek, note, weeks:{周一: 节数}}；delete:true 删除。"""
 d=data or {};obj=load(root)
 if d.get('delete'):
  obj['packages']=[p for p in obj['packages'] if p['id']!=d.get('id')]
  with LOCK:save_file(root,obj)
  sync(root);return listing(root,d.get('student'))
 student=d.get('student')
 if student not in 账本存取.roster(root):raise ValueError('没有这个学生')
 try:a,b=datetime.date.fromisoformat(str(d.get('start'))),datetime.date.fromisoformat(str(d.get('end')))
 except ValueError:raise ValueError('请填开始和结束日期')
 if b<a:raise ValueError('结束日期要在开始日期之后')
 if (b-a).days>366:raise ValueError('课包最长一年')
 per=d.get('perWeek')
 if isinstance(per,bool) or not isinstance(per,int) or not 1<=per<=20:raise ValueError('每周节数要在 1 到 20 之间')
 pid=d.get('id') or os.urandom(4).hex()
 for p in obj['packages']:
  if p['student']==student and p['id']!=pid and not (str(b)<p['start'] or str(a)>p['end']):raise ValueError('这段时间和 %s 已有的课包（%s–%s）重叠了'%(student,p['start'],p['end']))
 ws={}
 for k,v in (d.get('weeks') or {}).items():
  try:m=monday(datetime.date.fromisoformat(k))
  except ValueError:continue
  if isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=per:raise ValueError('每周最多扣 %d 节（%s 那周写的是 %s）'%(per,k,v))
  if v!=per:ws[str(m)]=v
 p={'id':pid,'student':student,'start':str(a),'end':str(b),'perWeek':per,'note':str(d.get('note') or '').strip()[:40],'weeks':ws}
 obj['packages']=[x for x in obj['packages'] if x['id']!=pid]+[p]
 with LOCK:save_file(root,obj)
 sync(root)
 return listing(root,student)
