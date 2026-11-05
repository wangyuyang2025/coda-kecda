"""课时账本：数据/账本.json 只追加流水，不改历史；记错了用“撤销”追加一条反向流水。余额 = 全部流水 delta 之和。"""
import datetime,json,re,uuid
import 存取公共
from 存取公共 import data_dir
from pathlib import Path
from 存取公共 import LOCK,ensure,read,write
KINDS={'opening','payment','lesson','leave','noshow','makeup','adjust'}  # 10-31：旷课、补课；请假也先扣课时
SPAN=re.compile(r'^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$')
def paths(root):data=data_dir(root);return data/'账本.json',data/'学生名单.json',data/'备份'
def roster(root):return json.loads(paths(root)[1].read_text())
def split_balance(live):
 """11-04 黑绿课时：按时间顺序重放流水（不改账本）。黑＝正常课时；绿＝请假后待补的课时。
 请假（扣过课时的）：黑色有多少就转多少成绿（不让黑色因请假变负；没缴费的课时不凭空变成绿）。
 上课/旷课/负的调整：先扣黑，黑扣完扣绿，都没了黑色才变负（红）。老请假（delta=0）不动。"""
 black=green=0
 for t in sorted(live,key=lambda x:(x['date'],x.get('createdAt',''))):
  d=t['delta']
  if t['kind']=='leave':
   u=-d if d<0 else (t.get('units',1) if t.get('toGreen') else 0)
   if u:
    m=min(max(black,0),u);black-=m;green+=m
  elif d>0:black+=d
  elif d<0:
   u=-d;m=min(max(black,0),u);black-=m;u-=m
   m=min(green,u);green-=m;u-=m;black-=u
 return black,green
def summary(root):
 ledger,_,_=paths(root);ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger)
 txs=obj['transactions'];voided={t['target'] for t in txs if t['kind']=='void'}
 names=list(roster(root));names+=sorted({t['student'] for t in txs}-set(names))
 try:paused=json.loads((data_dir(root)/'学生状态.json').read_text()).get('paused',{})
 except Exception:paused={}
 students=[]
 for n in names:
  mine=[t for t in txs if t['student']==n]
  bal=sum(t['delta'] for t in mine)
  # 11-02 请假/旷课标注：本期＝最近一次缴费（或起始余额）以来，续费就从 0 重新数；没扣过课时的老请假（delta=0）从可退里减掉
  live=sorted((t for t in mine if t['id'] not in voided and t['kind']!='void'),key=lambda t:t['date']);start=max((i for i,t in enumerate(live) if t['kind'] in ('payment','opening')),default=0)
  per=live[start:];lv=[t for t in per if t['kind']=='leave'];ns=[t for t in per if t['kind']=='noshow']
  undeducted=sum(1 for t in lv+ns if not t['delta'])
  enrolled=per[0]['delta'] if per and per[0]['kind'] in ('payment','opening') and per[0]['delta']>0 else 0   # 报名课数＝本期这次缴费/起始的节数
  black,green=split_balance(live)
  students.append({'name':n,'green':green,'rawBalance':bal,'enrolled':enrolled,'leaveRate':round(len(lv)/enrolled,3) if enrolled else None,'leaveN':len(lv),'noshowN':len(ns),'refundable':max(0,bal-undeducted),'periodFrom':per[0]['date'] if per else None,'balance':black,'owed':max(0,-black),'hasOpening':any(t['kind']=='opening' and t['id'] not in voided for t in mine),'count':len(mine),'last':max((t['date'] for t in mine),default=None),'paused':paused.get(n)})
 leaves={t['id'] for t in txs if t['kind']=='leave'}
 shown=[dict(t,voided=t['id'] in voided,**({'delta':0} if t['kind']=='leave' or (t['kind']=='void' and t.get('target') in leaves) else {})) for t in reversed(txs)]  # 11-04：流水里请假一律显示 0 节
 return {'students':students,'transactions':shown,'revision':rev}
def integer(value,low,high,label):
 if type(value) is not int or not low<=value<=high:raise ValueError(label+'要在 %d 到 %d 之间的整数'%(low,high))
 return value
def make_tx(data,names):
 """校验一条记录并生成流水（还不写入）。"""
 if not isinstance(data,dict):raise ValueError('请求无效')
 ident=data.get('id')
 if not isinstance(ident,str) or not 8<=len(ident)<=64 or ident.startswith('void-'):raise ValueError('记录编号无效')
 kind,student=data.get('kind'),data.get('student')
 if kind not in KINDS:raise ValueError('记录类型不对')
 if student not in names:raise ValueError('这个学生不在名单里')
 try:date=datetime.date.fromisoformat(data.get('date',''))
 except ValueError:raise ValueError('日期不对')
 if not 2020<=date.year<=2100:raise ValueError('日期不对')
 note=str(data.get('note','')).strip()
 if len(note)>200:raise ValueError('备注请控制在 200 字内')
 span=data.get('time') or ''
 if span:
  m=SPAN.match(span)
  if not m or span[:5]>=span[6:]:raise ValueError('时间格式不对，例如 09:00-09:45')
 tx={'id':ident,'kind':kind,'student':student,'date':str(date),'note':note}
 if kind in ('lesson','leave','noshow'):
  units=data.get('units',1);integer(units,1,2,'课时数');tx['units']=units;tx['delta']=0 if kind=='leave' else -units
  if kind=='leave':tx['toGreen']=True  # 11-04：请假记 0 节（转绿色待补，见 split_balance）；旷课仍先扣
  if span:tx['time']=span
 elif kind=='makeup':
  units=data.get('units',1);integer(units,1,2,'课时数');tx['units']=units;tx['delta']=units
 elif kind=='payment':
  tx['delta']=integer(data.get('count'),1,500,'缴费课时数')
  money=data.get('money')
  if money not in (None,''):
   if isinstance(money,bool) or not isinstance(money,(int,float)) or not 0<=money<=1000000:raise ValueError('金额不对')
   tx['money']=money
 elif kind=='opening':tx['delta']=integer(data.get('delta'),-500,500,'起始余额')
 else:
  tx['delta']=integer(data.get('delta'),-500,500,'调整课时数')
  if tx['delta']==0 or not note:raise ValueError('手动调整不能为 0，并且要写备注')
 return tx
def check_live(tx,txs):
 """和已有流水对照：起始余额只能有一条；同一天同一时段不能重复记上课。"""
 voided={t['target'] for t in txs if t['kind']=='void'}
 live=[t for t in txs if t['id'] not in voided and t['kind']!='void' and t['student']==tx['student']]
 if tx['kind']=='opening' and any(t['kind']=='opening' for t in live):raise ValueError('这个学生已登记过起始余额；要改请先撤销，或用“手动调整”')
 if tx['kind'] in ('lesson','leave','noshow') and tx.get('time') and any(t['kind'] in ('lesson','leave','noshow') and t['date']==tx['date'] and t.get('time')==tx['time'] for t in live):raise ValueError('这个学生这天这个时段已经记过了')
def match_teacher(root,student,date,span='',cache=None):
 """11-05：按课表给一节课配老师。先对这周实际课表的同学生同日（时间相同优先，连 course/dual 一起）；对不上（调课、假期）就看这个学生课表里是不是只有一位老师。配不出返回 {}，绝不挡记录。"""
 import 签课表,周调整存取
 try:
  d=datetime.date.fromisoformat(date);monday=str(d-datetime.timedelta(days=d.weekday()));cache=cache if cache is not None else {}
  if monday not in cache:cache[monday]=签课表.entries_for_week(root,monday)[1]
  same=[e for e in cache[monday] if e['name']==student and e['date']==date]
  exact=[e for e in same if e['time'].replace('–','-')==(span or '').replace('–','-')]
  pick=exact or same
  if pick and len({e.get('teacher') for e in pick})==1 and pick[0].get('teacher'):
   return {k:pick[0][k] for k in ('course','teacher','dual') if pick[0].get(k) is not None}
  rows=json.loads((data_dir(root)/'基础排课.json').read_text())
  who={r.get('teacher') for r in rows if student in r.get('studentNames',[])}
  if len(who)==1 and None not in who:return {'teacher':who.pop()}
 except Exception:pass
 return {}
def tag_teacher(root,tx,cache=None):
 if tx.get('kind') in ('lesson','leave','noshow') and not tx.get('teacher'):
  tx.update(match_teacher(root,tx['student'],tx['date'],tx.get('time',''),cache))
 return tx
def stamp(tx):tx['createdAt']=存取公共.now_aware().isoformat(timespec='seconds');return tx
def fresh_id(ident,txs):
 """11-05：同一个编号的记录被撤销过，又要重新记（补记录的编号按 学生+日期+时间 固定）→ 换个新编号再记，不再被当成“已经记过”悄悄跳过。"""
 voided={t['target'] for t in txs if t['kind']=='void'}
 if ident in voided:
  n=2
  while any(t['id']==ident+'-r%d'%n for t in txs):n+=1
  return ident+'-r%d'%n
 return ident
def add(root,data):
 tx=make_tx(data,roster(root));ledger,_,backups=paths(root)
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions']
  tx['id']=fresh_id(tx['id'],txs)
  if any(t['id']==tx['id'] for t in txs):return dict(summary(root),duplicate=True)
  check_live(tx,txs);tag_teacher(root,tx);txs.append(stamp(tx))
  write(ledger,obj,rev,backups,'账本')
 return summary(root)
def add_batch(root,data):
 """一次登记多条（例如批量起始余额）：全部校验通过才写入，只写一次文件、留一份备份；已登记过的编号自动跳过。"""
 items=data.get('items') if isinstance(data,dict) else None
 if not isinstance(items,list) or not 1<=len(items)<=300:raise ValueError('请求无效')
 names=roster(root);built=[]
 for x in items:
  try:built.append(make_tx(x,names))
  except ValueError as e:raise ValueError(str((x or {}).get('student','') if isinstance(x,dict) else '')+'：'+str(e))
 ledger,_,backups=paths(root);added=0;week_cache={}
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions'];known={t['id'] for t in txs}
  for tx in built:
   tx['id']=fresh_id(tx['id'],txs)
   if tx['id'] in known:continue
   try:check_live(tx,txs)
   except ValueError as e:raise ValueError(tx['student']+'：'+str(e))
   tag_teacher(root,tx,week_cache);txs.append(stamp(tx));known.add(tx['id']);added+=1
  if added:write(ledger,obj,rev,backups,'账本')
 return dict(summary(root),added=added)
def changes_path(root):return data_dir(root)/'改动记录.json'
def changes(root,student=None):
 """11-05 改动记录：课时单里改某一节（类型、日期、时间、课时数、课包、删除）时留一行，不再靠流水里“撤销/未撤销”看。"""
 f=changes_path(root)
 try:obj=json.loads(f.read_text(encoding='utf-8'))
 except Exception:obj={'version':1,'changes':[]}
 rows=obj.get('changes',[])
 return [r for r in rows if not student or r.get('student')==student]
def _brief(t):
 return {'kind':t['kind'],'date':t['date'],'time':t.get('time') or '','units':t.get('units',1),'delta':t['delta']}
def edit(root,data):
 """课时单里改一节：{id, student, action:'edit'|'delete'|'package', kind:lesson|leave|noshow, date, time, units, perWeek}。
 账本仍是追加式：撤销旧的、记新的（用户看不到撤销，只看到改动记录）。"""
 if not isinstance(data,dict) or not isinstance(data.get('id'),str):raise ValueError('请求无效')
 action=data.get('action','edit');ledger,_,backups=paths(root)
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions']
  old=next((t for t in txs if t['id']==data['id']),None)
  voided={t['target'] for t in txs if t['kind']=='void'}
  if not old or old['kind'] in ('void','opening','payment') or old['id'] in voided:raise ValueError('找不到这一条（可能已经改过），请刷新')
  now=存取公共.now_aware()
  def void_old(note):
   txs.append({'id':'void-'+uuid.uuid4().hex,'kind':'void','target':old['id'],'student':old['student'],'date':str(now.date()),'delta':-old['delta'],'note':note,'createdAt':now.isoformat(timespec='seconds')})
  new=None;label=''
  if action=='delete':
   void_old('课时单删除这一节');label='删除'
  elif action=='package':
   import 课包
   perWeek=data.get('perWeek')
   try:day=datetime.date.fromisoformat(old['date'])
   except ValueError:raise ValueError('日期不对')
   void_old('课时单改成按课包扣')
   write(ledger,obj,rev,backups,'账本');obj,rev=None,None
   课包.add_week(root,old['student'],课包.monday(day),perWeek);课包.sync(root);label='改成按课包扣 %s 节'%perWeek
   _log(root,old,None,label,now);return summary(root)
  else:
   kind=data.get('kind') or old['kind']
   if kind not in ('lesson','leave','noshow','adjust'):raise ValueError('类型不对')
   new=make_tx(dict(id='edit-'+uuid.uuid4().hex[:20],kind=kind,student=old['student'],date=data.get('date') or old['date'],time=data.get('time',old.get('time') or ''),units=data.get('units',old.get('units',1)),note=old.get('note','') if kind==old['kind'] else (old.get('note','')+' 改自'+old['kind'])[:200],delta=data.get('delta',old.get('delta'))),roster(root))
   for k in ('course','teacher','dual','via'):
    if old.get(k) is not None:new[k]=old[k]
   rest=[t for t in txs if t['id']!=old['id']]
   check_live(new,rest)
   if new['date']!=old['date'] or new.get('time')!=old.get('time'):
    for k in ('course','teacher','dual'):new.pop(k,None)
   tag_teacher(root,new)
   void_old('课时单改这一节');txs.append(stamp(new));label='修改'
  write(ledger,obj,rev,backups,'账本')
 _log(root,old,new,label,now)
 return summary(root)
def _log(root,old,new,label,now):
 f=changes_path(root);backups=paths(root)[2]
 with LOCK:
  ensure(f,{'version':1,'changes':[]});obj,rev=read(f)
  obj['changes'].append({'at':now.isoformat(timespec='seconds'),'student':old['student'],'label':label,'from':_brief(old),'to':_brief(new) if new else None})
  obj['changes']=obj['changes'][-2000:]
  write(f,obj,rev,backups,'改动记录')
def void(root,data):
 if not isinstance(data,dict) or not isinstance(data.get('id'),str):raise ValueError('请求无效')
 ledger,_,backups=paths(root);note=str(data.get('note','')).strip()[:200]
 with LOCK:
  ensure(ledger,{'version':1,'transactions':[]});obj,rev=read(ledger);txs=obj['transactions']
  target=next((t for t in txs if t['id']==data['id']),None)
  if not target or target['kind']=='void':raise ValueError('找不到这条记录')
  if any(t['kind']=='void' and t['target']==target['id'] for t in txs):raise ValueError('这条记录已经撤销过了')
  now=存取公共.now_aware()
  txs.append({'id':'void-'+uuid.uuid4().hex,'kind':'void','target':target['id'],'student':target['student'],'date':str(now.date()),'delta':-target['delta'],'note':note or '撤销','createdAt':now.isoformat(timespec='seconds')})
  write(ledger,obj,rev,backups,'账本')
 return summary(root)
