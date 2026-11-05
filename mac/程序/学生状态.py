"""学生名单和状态。名单：哪里输入了名单里没有的名字，就在那里直接新建（ensure_students）。状态：目前只有“暂停上课”。数据/学生状态.json：{"paused": {"名字": "从哪天起"}}。暂停的学生账目照常保留，只在课时管理里标出来。"""
import datetime,json,os
import 存取公共
from 存取公共 import data_dir
from pathlib import Path
from 存取公共 import LOCK,read,write
import 账本存取
def path(root):return data_dir(root)/'学生状态.json'
def save_state(root,state):存取公共.write_json(path(root),state)
def load(root):
 try:return json.loads(path(root).read_text())
 except Exception:return {'paused':{}}
def ensure_students(root,names):
 """名单里没有的名字直接新建（加在 学生名单.json 末尾，改前自动备份）；返回新建了哪些。"""
 roster_path=data_dir(root)/'学生名单.json'
 with LOCK:
  obj,rev=read(roster_path);new=[n for n in dict.fromkeys(names) if n not in obj]
  if any(not isinstance(n,str) or n!=n.strip() or not 0<len(n)<=40 for n in new):raise ValueError('学生姓名不对')
  if new:write(roster_path,obj+new,rev,data_dir(root)/'备份','学生名单')
 return new
def remove_student(root,data):
 """删除学生（打错名字、示例学生用）：只能删没上过课、没缴过费、不在课表里的人；他的起始余额记录一起去掉。改前自动备份。"""
 name=(data or {}).get('name');base=data_dir(root);backups=base/'备份'
 if name not in 账本存取.roster(root):raise ValueError('没有这个学生')
 rows=json.loads((base/'基础排课.json').read_text())
 if any(name in r.get('studentNames',[]) for r in rows):raise ValueError(name+' 还在固定课表里，请先在课程管理里把他拖回“未排课学生”')
 try:weeks=json.loads((base/'临时调整.json').read_text()).get('weeks',{})
 except Exception:weeks={}
 if any(name in (o.get('studentNames') or []) for ops in weeks.values() for o in ops if o.get('type')=='add'):raise ValueError(name+' 在临时安排里还有课，请先删掉那节临时课')
 ledger=账本存取.paths(root)[0]
 with LOCK:
  obj,rev=read(ledger);txs=obj['transactions'];mine={t['id'] for t in txs if t.get('student')==name and t['kind']!='void'}
  voided={t.get('target') for t in txs if t['kind']=='void'}   # 撤销掉的缴费（比如名字打错）不算
  if any(t.get('student')==name and t['kind'] not in ('opening','void') and t['id'] not in voided for t in txs):raise ValueError(name+' 已经有上课或缴费记录，不能删除；不来了请用“暂停上课”')
  if mine:write(ledger,dict(obj,transactions=[t for t in txs if t['id'] not in mine and t.get('target') not in mine]),rev,backups,'账本')
  r_obj,r_rev=read(base/'学生名单.json');write(base/'学生名单.json',[n for n in r_obj if n!=name],r_rev,backups,'学生名单')
  state=load(root)
  if name in state.get('paused',{}):
   state['paused'].pop(name);save_state(root,state)
 return 账本存取.summary(root)
def set_paused(root,data):
 """暂停或恢复上课。"""
 name=(data or {}).get('name')
 if name not in 账本存取.roster(root):raise ValueError('没有这个学生')
 try:day=str(datetime.date.fromisoformat(str(data.get('since') or 存取公共.today())))
 except ValueError:raise ValueError('日期不对')
 with LOCK:
  state=load(root);state.setdefault('paused',{})
  if data.get('paused'):state['paused'][name]=day
  else:state['paused'].pop(name,None)
  save_state(root,state)
 return 账本存取.summary(root)
def enroll(root,data):
 """新生报名：加进名单、记缴费（起始余额记 0，这样不会被提醒“未登记起始余额”），可以顺便标“暂停上课”。
 没暂停的会出现在课程管理的“未排课学生”里，等排时间。全部校验通过才写。"""
 if not isinstance(data,dict):raise ValueError('请求无效')
 name=str(data.get('name') or '').strip()
 if not 0<len(name)<=40 or any(c in name for c in '、,，/'):raise ValueError('请填学生名字（一个人一个名字）')
 if name in 账本存取.roster(root):raise ValueError(name+' 已经在名单里了；要缴费请在他那一行点“缴费”')
 ident=data.get('id')
 if not isinstance(ident,str) or not 8<=len(ident)<=40:raise ValueError('请求无效')
 day=data.get('date') or str(存取公共.today())
 pay=账本存取.make_tx({'id':ident+'-pay','kind':'payment','student':name,'date':day,'count':data.get('count'),'money':data.get('money'),'note':str(data.get('note') or '新生报名')},[name])
 opening=账本存取.make_tx({'id':ident+'-open','kind':'opening','student':name,'date':day,'delta':0,'note':'新生报名'},[name])
 ensure_students(root,[name])
 账本存取.add_batch(root,{'items':[dict(opening,delta=0),dict(pay,count=pay['delta'])]})
 if data.get('paused'):return set_paused(root,{'name':name,'paused':True,'since':day})
 return 账本存取.summary(root)
def merge(root,data):
 """合并学生（同一个人在名单里有两个名字时用）：把“from”的资料全并到“to”名下，然后从名单里去掉“from”。
 会改：账本流水、固定课表、临时安排、请假标记、暂停状态、归档的老课表照片、待核对的签课表。改前每个文件都自动备份。
 两边都有起始余额：保留日期较晚的那条，另一条撤销（流水里看得到）。同一天同一时段两边都记过课：停下，请先撤销其中一条。
 服务管理 / 作品管理的资料按名字放在文件路径里，不动（页面会提醒）。dry=True 时只返回会改什么，不写。"""
 import re,shutil
 from 存取公共 import ensure
 d=data or {};a=str(d.get('from') or '').strip();b=str(d.get('to') or '').strip()
 names=账本存取.roster(root)
 if a not in names or b not in names:raise ValueError('两个名字都要在名单里')
 if a==b:raise ValueError('请选另一个名字')
 base=data_dir(root);backups=base/'备份';ledger=账本存取.paths(root)[0]
 def swap(lst):
  out=[]
  for n in lst:
   n=b if n==a else n
   if n not in out:out.append(n)
  return out
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions']
  voided={t['target'] for t in txs if t['kind']=='void'}
  live=lambda n:[t for t in txs if t.get('student')==n and t['kind']!='void' and t['id'] not in voided]
  la,lb=live(a),live(b)
  clash=sorted({(t['date'],t.get('time')) for t in la if t['kind'] in ('lesson','leave') and t.get('time')}&{(t['date'],t.get('time')) for t in lb if t['kind'] in ('lesson','leave') and t.get('time')})
  if clash:raise ValueError('%s 和 %s 在同一时段都记过课（%s），请先在流水里撤销重复的那条再合并'%(a,b,'、'.join(x[0][5:]+' '+x[1] for x in clash[:3])))
  oa=[t for t in la if t['kind']=='opening'];ob=[t for t in lb if t['kind']=='opening']
  drop=None
  if oa and ob:drop=min(oa[0],ob[0],key=lambda t:(t['date'],t.get('createdAt','')))
  rows,rrev=read(base/'基础排课.json')
  try:weeks,wrev=read(base/'临时调整.json')
  except Exception:weeks,wrev=None,None
  paper=base/'纸质课表'/a
  photos=[p for p in paper.glob('*') if p.is_file() and p.name!='记录.json'] if paper.is_dir() else []
  try:service=any(k.split('|')[-1]==a for k in json.loads((base/'学生档案.json').read_text()).get('lessons',{}))
  except Exception:service=False
  info={'from':a,'to':b,'records':len([t for t in txs if t.get('student')==a]),'courses':sum(1 for r in rows if a in r.get('studentNames',[])),'photos':len(photos),
   'openingDropped':(drop['student']+' '+drop['date']+' 起始余额 '+str(drop['delta'])) if drop else '','service':service,'paused':a in load(root).get('paused',{})}
  if d.get('dry'):return info
  # 1. 账本：重复的起始余额先撤销，再整体改名
  if drop:
   now=存取公共.now_aware()
   txs.append({'id':'void-'+os.urandom(16).hex(),'kind':'void','target':drop['id'],'student':drop['student'],'date':str(now.date()),'delta':-drop['delta'],'note':'合并 %s → %s：保留较新的起始余额'%(a,b),'createdAt':now.isoformat(timespec='seconds')})
  for t in txs:
   if t.get('student')==a:t['student']=b;t.setdefault('mergedFrom',a)
  write(ledger,obj,rev,backups,'账本')
  # 2. 固定课表、临时安排
  for r in rows:
   if a in r.get('studentNames',[]):r['studentNames']=swap(r['studentNames']);r['name']='、'.join(r['studentNames'])
  write(base/'基础排课.json',rows,rrev,backups,'基础排课')
  if weeks:
   touched=False
   for ops in weeks.get('weeks',{}).values():
    for o in ops:
     if a in (o.get('studentNames') or []):o['studentNames']=swap(o['studentNames']);o['name']='、'.join(o['studentNames']);touched=True
     if o.get('student')==a:o['student']=b;touched=True
   if touched:write(base/'临时调整.json',weeks,wrev,backups,'临时调整')
  # 3. 请假标记
  mp=base/'请假标记.json'
  if mp.exists():
   m,mrev=read(mp);marks=m.get('marks',{});new={}
   for k,v in marks.items():
    parts=k.split('|')
    if parts[-1]==a:k='|'.join(parts[:-1]+[b])
    new.setdefault(k,v)
   if new!=marks:m['marks']=new;write(mp,m,mrev,backups,'请假标记')
  # 4. 暂停状态：留“to”自己的；“from”的去掉
  st=load(root)
  if a in st.get('paused',{}):
   st['paused'].pop(a);save_state(root,st)
  # 5. 老课表照片
  if paper.is_dir():
   dest=base/'纸质课表'/b;dest.mkdir(parents=True,exist_ok=True)
   try:book_a=json.loads((paper/'记录.json').read_text())
   except Exception:book_a={}
   try:book_b=json.loads((dest/'记录.json').read_text())
   except Exception:book_b={}
   for p in photos:
    t=dest/p.name
    if t.exists():t=dest/(p.stem+'_'+os.urandom(3).hex()+p.suffix)
    shutil.move(str(p),str(t))
    if p.name in book_a:book_b[t.name]=book_a[p.name]
   存取公共.write_json(dest/'记录.json',book_b)
   try:(paper/'记录.json').unlink()
   except Exception:pass
   try:paper.rmdir()
   except Exception:pass
  # 6. 待核对的签课表
  for f in (base/'签课表'/'待核对').glob('*.json') if (base/'签课表'/'待核对').is_dir() else []:
   try:rv=json.loads(f.read_text())
   except Exception:continue
   hit=False
   for r in rv.get('rows',[]):
    if r.get('entry',{}).get('name')==a:r['entry']['name']=b;hit=True
   if hit:shutil.copy2(f,backups/('待核对_'+f.name));存取公共.write_json(f,rv,indent=None)
  # 7. 名单最后改
  r_obj,r_rev=read(base/'学生名单.json');write(base/'学生名单.json',[n for n in r_obj if n!=a],r_rev,backups,'学生名单')
 return dict(账本存取.summary(root),merged=info)
def rename(root,data):
 """改名字（名字打错了）：新名字不能已经在名单里（那种情况用“合并”）。做法是先把新名字加进名单，再用 merge 把旧名字的资料全搬过去，最后让新名字留在旧名字原来的位置。"""
 d=data or {};a=str(d.get('from') or '').strip();b=str(d.get('to') or '').strip()
 names=账本存取.roster(root)
 if a not in names:raise ValueError('没有这个学生')
 if not b or b==a:raise ValueError('请写新名字')
 if b in names:raise ValueError(b+' 已经在名单里了；同一个人有两个名字请用“合并到另一个名字”')
 if any(c in b for c in '、,，/|\\') or len(b)>12 or b.isdigit() or any(c.isspace() for c in b):raise ValueError('新名字最长 12 个字，不能有空格、逗号、顿号、斜杠，也不能只是数字')
 pos=names.index(a)
 ensure_students(root,[b])
 out=merge(root,{'from':a,'to':b})
 base=data_dir(root)/'学生名单.json'
 with LOCK:
  r_obj,r_rev=read(base);r_obj=[n for n in r_obj if n!=b];r_obj.insert(min(pos,len(r_obj)),b);write(base,r_obj,r_rev,data_dir(root)/'备份','学生名单')
 return dict(账本存取.summary(root),renamed={'from':a,'to':b,'service':out['merged']['service']})
