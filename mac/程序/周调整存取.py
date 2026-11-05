"""一周内的临时调课：数据/临时调整.json。不改基础课表，只记录“某周某节课取消 / 改时间 / 加一节”。"""
import datetime,html,json,re
from 存取公共 import data_dir
from pathlib import Path
from 存取公共 import LOCK,Conflict,ensure,read,write
from 课表存取 import CLOCK,COLORS,DAYS,minutes,validate
def paths(root):data=data_dir(root);return data/'临时调整.json',data/'基础排课.json',data/'学生名单.json',data/'备份'
def monday(day):return day-datetime.timedelta(days=day.weekday())
def parse_week(value):
 try:day=datetime.date.fromisoformat(value or '')
 except ValueError:raise ValueError('周的日期不对')
 if day.weekday()!=0:raise ValueError('每周从周一算起，请选周一的日期')
 return day
def check_time(r,label):
 if r.get('day') not in DAYS:raise ValueError(label+'：星期不对')
 start,end=r.get('start'),r.get('end')
 if not all(isinstance(v,str) and CLOCK.match(v) for v in (start,end)) or minutes(start)>=minutes(end):raise ValueError(label+'：时间不对')
def effective(rows,ops):
 byid={r['id']:r for r in rows};out=[];cancelled=[]
 gone={o['course'] for o in ops if o['type']=='cancel'};moved={o['course']:o for o in ops if o['type']=='move'}
 for r in rows:
  if r['id'] in gone:cancelled.append(r);continue
  if r['id'] in moved:
   o=moved[r['id']];out.append(dict(r,day=o['day'],start=o['start'],end=o['end'],changed='move',was={'day':r['day'],'start':r['start'],'end':r['end']}));continue
  out.append(dict(r,changed=None))
 for o in ops:
  if o['type']=='add':out.append({'id':o['id'],'name':o['name'],'studentNames':o['studentNames'],'day':o['day'],'start':o['start'],'end':o['end'],'teacher':o['teacher'],'teachers':o.get('teachers') or [o['teacher']],'units':o['units'],'dual':o.get('dual'),'changed':'add'})
 out.sort(key=lambda r:(DAYS.index(r['day']),r['start']))
 return out,cancelled
def warnings(eff):
 found=[]
 for i,a in enumerate(eff):
  for b in eff[i+1:]:
   if a['day']==b['day'] and minutes(a['start'])<minutes(b['end']) and minutes(b['start'])<minutes(a['end']):
    both=set(a['studentNames'])&set(b['studentNames'])
    if both:found.append('%s %s 的课时间重叠：%s %s–%s 与 %s–%s'%(a['day'],'、'.join(sorted(both)),a['name'],a['start'],a['end'],b['start'],b['end']))
 return found
def load(root,week):
 day=parse_week(week);store,sched,_,_=paths(root);ensure(store,{'version':1,'weeks':{}})
 obj,rev=read(store);rows=json.loads(sched.read_text());ops=obj['weeks'].get(str(day),[])
 eff,cancelled=effective(rows,ops)
 return {'week':str(day),'ops':ops,'base':rows,'effective':eff,'cancelled':cancelled,'warnings':warnings(eff),'revision':rev,'weeksWithChanges':sorted(obj['weeks']),'roster':json.loads(paths(root)[2].read_text())}
def save(root,data):
 if not isinstance(data,dict):raise ValueError('请求无效')
 day=parse_week(data.get('week'));ops=data.get('ops')
 store,sched,rosterfile,backups=paths(root)
 if not isinstance(ops,list) or len(ops)>200:raise ValueError('调整内容格式不对')
 rows={r['id']:r for r in json.loads(sched.read_text())};roster=set(json.loads(rosterfile.read_text()))
 known={x.get('id') for x in (read(store)[0]['weeks'].get(str(day),[]) if store.exists() else [])}
 seen=set();touched=set();clean=[];new_names=[]
 for o in ops:
  if not isinstance(o,dict) or not isinstance(o.get('id'),str) or not o['id'] or o['id'] in seen:raise ValueError('调整编号缺失或重复')
  seen.add(o['id']);kind=o.get('type');note=str(o.get('note',''))[:200]
  if kind in ('cancel','move'):
   course=o.get('course')
   if course not in rows:
    if o['id'] in known:continue
    raise ValueError('找不到这节课，课表可能已变，请刷新页面')
   if course in touched:raise ValueError(rows[course]['name']+'这周只能有一条调整')
   touched.add(course)
   if kind=='cancel':clean.append({'id':o['id'],'type':'cancel','course':course,'note':note})
   else:check_time(o,rows[course]['name']);clean.append({'id':o['id'],'type':'move','course':course,'day':o['day'],'start':o['start'],'end':o['end'],'note':note})
  elif kind=='add':  # 名单里没有的学生，保存时直接新建
   names=o.get('studentNames')
   if not isinstance(names,list) or not names or not all(isinstance(n,str) and 0<len(n.strip())<=40 for n in names):raise ValueError('临时课的学生姓名不对')
   names=[n.strip() for n in names];new_names+=[n for n in names if n not in roster]
   row={'id':o['id'],'name':'、'.join(names),'studentNames':names,'day':o.get('day'),'start':o.get('start'),'end':o.get('end'),'teacher':o.get('teacher'),'teachers':o.get('teachers') or [o.get('teacher')],'units':o.get('units'),'dual':o.get('dual')}
   validate([row]);clean.append(dict(row,type='add',note=note))
  else:raise ValueError('调整类型不对')
 added=[]
 if new_names:
  import 学生状态;added=学生状态.ensure_students(root,new_names)
 with LOCK:
  ensure(store,{'version':1,'weeks':{}});obj,rev=read(store)
  if data.get('revision') not in (None,rev):raise Conflict('这一周的调整刚被别处改过，请刷新页面后再改')
  if clean:obj['weeks'][str(day)]=clean
  else:obj['weeks'].pop(str(day),None)
  write(store,obj,rev,backups,'临时调整')
 return dict(load(root,str(day)),added=added)
def cancelled_between(root,start,end):
 """start–end（含）之间在临时安排里停掉的课：[{date, day, time, name, students, note}]，给看板统计“停课”（休假、学校上课、调课等，不是学生请假）。"""
 a,b=datetime.date.fromisoformat(start),datetime.date.fromisoformat(end);out=[]
 store=paths(root)[0]
 if not store.exists():return out
 for wk in sorted(json.loads(store.read_text()).get('weeks',{})):
  mon=datetime.date.fromisoformat(wk)
  if mon>b or mon+datetime.timedelta(days=6)<a:continue
  data=load(root,wk);notes={o['course']:o.get('note','') for o in data['ops'] if o['type']=='cancel'}
  for r in data['cancelled']:
   d=mon+datetime.timedelta(days=DAYS.index(r['day']))
   if a<=d<=b:out.append({'date':str(d),'day':r['day'],'time':r['start']+'–'+r['end'],'name':r['name'],'students':r['studentNames'],'note':notes.get(r['id'],'')})
 return sorted(out,key=lambda x:(x['date'],x['time']))
def cancelled_keys(root,week):
 """某周停掉的课：{(课程编号, 日期)}，签课表核对时用来把这些行标成“停课”。"""
 try:data=load(root,week)
 except Exception:return set()
 mon=datetime.date.fromisoformat(data['week'])
 return {(r['id'],str(mon+datetime.timedelta(days=DAYS.index(r['day'])))) for r in data['cancelled']}
def cancelled_slots(root,week):
 """同上，按 (日期, 时段, 学生) 认：签课表上没带课程编号的行（10-20 发现：打印后课表改过的那行）也能认出是停课。"""
 try:data=load(root,week)
 except Exception:return set()
 mon=datetime.date.fromisoformat(data['week'])
 slots={(str(mon+datetime.timedelta(days=DAYS.index(r['day']))),r['start']+'–'+r['end'],n) for r in data['cancelled'] for n in (r.get('studentNames') or [])}
 # 整天都停了的日子（比如 10/10 学校上课，周六全停）：那天没带课程编号的行一律算停课，哪怕之后课表又改过
 busy={r['day'] for r in data['effective']}
 for day in {r['day'] for r in data['cancelled']}-busy:slots.add((str(mon+datetime.timedelta(days=DAYS.index(day))),'*','*'))
 return slots
