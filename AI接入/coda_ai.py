#!/usr/bin/python3
"""让 AI 智能体读写 Coda 课达：python3 AI接入/coda_ai.py 命令。说明见 AI接入/00_先读这个.md。
只用标准库。只连本机 127.0.0.1；写入分两步：propose 列清单（不写），老师同意后 confirm 才写。"""
import argparse,datetime,json,re,sys,time,urllib.error,urllib.parse,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'mac'/'我的资料'
PENDING=DATA/'待确认'
REASON='AI 接入：老师确认'
WRITE_OK={'/api/ledger/add','/api/ledger/edit','/api/inbox/text','/api/adjust/save','/api/packages/save'}
READ_POST={'/api/sheets/review'}
DAY=re.compile(r'^\d{4}-\d{2}-\d{2}$');SPAN=re.compile(r'^\d{2}:\d{2}-\d{2}:\d{2}$');WEEK='一二三四五六日'
class Stop(Exception):pass
def port():
 try:return int(json.loads((DATA/'发行版.json').read_text(encoding='utf-8')).get('port') or 18765)
 except Exception:return 18765
def call(path,body=None,query=None,write=False):
 if body is not None and path not in READ_POST and not (write and path in WRITE_OK):raise Stop('不允许调这个写接口：'+path)
 try:token=(DATA/'手机连接'/'本机口令.txt').read_text().strip()
 except Exception:raise Stop('课达没开过：请老师先双击“Mac 点这里”。')
 url='http://127.0.0.1:%d%s'%(port(),path)+('?'+urllib.parse.urlencode(query) if query else '')
 head={'X-Local-Token':token}
 data=None
 if body is not None:data=json.dumps(body,ensure_ascii=False).encode('utf-8');head['Content-Type']='application/json'
 if write:head['X-Coda-Reason']=urllib.parse.quote(REASON)
 try:
  with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=head,method='POST' if body is not None else 'GET'),timeout=30) as r:return json.loads(r.read().decode('utf-8') or '{}')
 except urllib.error.HTTPError as e:
  try:msg=json.loads(e.read().decode('utf-8')).get('error') or str(e)
  except Exception:msg=str(e)
  raise Stop('课达说：'+msg)
 except urllib.error.URLError:raise Stop('课达没开：请老师双击“Mac 点这里”。')
def pick(d,keys):return {k:d.get(k) for k in keys}
def hours(a):
 s=call('/api/ledger')
 if not a.name:return {'students':[pick(x,('name','balance','green','last','paused','hasOpening')) for x in s['students']]}
 st=next((x for x in s['students'] if x['name']==a.name),None)
 if not st:raise Stop('名单里没有「%s」'%a.name)
 return {'student':st,'recent':[pick(t,('id','date','kind','delta','time','note','voided')) for t in s['transactions'] if t['student']==a.name][:a.limit]}
def week(a):
 w=call('/api/mobile/week');return {'today':w.get('today'),'rows':[pick(r,('date','day','start','end','students','teacher','units','changed','leave','booked')) for r in w.get('rows',[])]}
def courses(a):
 d=_date(a.date);mon=d-datetime.timedelta(days=d.weekday());w=call('/api/adjust',query={'week':str(mon)})
 return {'week':w.get('week'),'courses':[pick(r,('id','name','studentNames','day','start','end','teacher','units')) for r in w.get('effective',[])],'ops':w.get('ops',[])}
def gaps(a):return call('/api/gaps/student',query={'name':a.name}) if a.name else call('/api/gaps')
def texts(a):
 t=call('/api/inbox').get('texts',{});return {'texts':{k:v for k,v in t.items() if (not a.date or k.startswith(a.date+'|')) and (not a.student or k.endswith('|'+a.student))}}
def log(a):
 l=call('/api/log',query={'month':a.month} if a.month else None);rows=l.get('items') or l.get('entries') or l.get('rows') or []
 if a.student:rows=[r for r in rows if a.student in (r.get('students') or [])]
 return {'rows':[pick(r,('at','page','action','summary','change','result')) for r in rows[-a.limit:]]}
def changes(a):return call('/api/ledger/changes',query={'name':a.name})
def paper(a):return call('/api/paper/student',query={'name':a.name})
def sheets(a):return call('/api/sheets')
def sheet(a):
 r=call('/api/sheets/review',{'reviewId':a.id})
 return dict(pick(r,('reviewId','sheetId','week','sourceFile','booked')),rows=[dict(pick(x['entry'],('id','name','date','day','time','units')),**pick(x,('status','reason','booked','leaveMark','unknown'))) for x in r['rows']])
def _date(v,what='日期'):
 if not isinstance(v,str) or not DAY.match(v):raise Stop('%s要写成 YYYY-MM-DD：%s'%(what,v))
 return datetime.date.fromisoformat(v)
def _short(d):
 x=datetime.date.fromisoformat(d);return '%d/%d 周%s'%(x.month,x.day,WEEK[x.weekday()])
def clean(it,names):
 """检查一条，给老师看的文字由这里生成。"""
 if not isinstance(it,dict):raise Stop('清单格式不对')
 t=it.get('type')
 if t in ('record','content','package','edit') and it.get('student') not in names:raise Stop('名单里没有「%s」'%it.get('student'))
 if t=='record':
  kind=it.get('kind')
  if kind not in ('lesson','leave'):raise Stop('只能记上课和请假')
  _date(it.get('date'));span=(it.get('time') or '').replace('–','-')
  if span and not SPAN.match(span):raise Stop('时间格式不对：'+span)
  units=it.get('units',1)
  if units not in (1,2):raise Stop('课时数只能 1 或 2')
  word='上课，扣 %d 节'%units if kind=='lesson' else '请假，扣 0 节'
  return dict(type=t,kind=kind,student=it['student'],date=it['date'],time=span,units=units,txid='ai-'+uuid.uuid4().hex[:20],label='%s　%s %s　%s'%(it['student'],_short(it['date']),span,word))
 if t=='content':
  _date(it.get('date'));text=str(it.get('text') or '').strip()
  if not text or len(text)>5000:raise Stop('上课内容不能为空，也不能超过 5000 字')
  return dict(type=t,student=it['student'],date=it['date'],text=text,label='%s　%s　上课内容：%s'%(it['student'],_short(it['date']),text))
 if t=='edit':
  action=it.get('action')
  if action not in ('edit','package'):raise Stop('不能删除记录，请老师在课时单里操作')
  if not it.get('id'):raise Stop('改记录要给 id')
  keep={k:it[k] for k in ('kind','date','time','units','perWeek') if it.get(k) not in (None,'')}
  if keep.get('kind') not in (None,'lesson','leave'):raise Stop('只能改成上课或请假')
  if 'date' in keep:_date(keep['date'])
  if 'time' in keep:keep['time']=keep['time'].replace('–','-')
  what='这一周改按课包扣 %s 节'%keep.get('perWeek') if action=='package' else '改成 '+' '.join(str(v) for v in keep.values())
  return dict(type=t,id=it['id'],student=it['student'],action=action,label='%s　改记录 %s：%s'%(it['student'],it['id'][:12],what),**keep)
 if t=='schedule':
  d=_date(it.get('date'),'那周的日期');op=it.get('op')
  if not isinstance(op,dict) or op.get('type') not in ('move','cancel','add'):raise Stop('调课只能是 move、cancel、add')
  word={'move':'改到','cancel':'停课','add':'加临时课'}[op['type']]
  who=op.get('name') or op.get('course') or '';when=' '.join(str(op[k]) for k in ('day','start','end') if op.get(k));mon=d-datetime.timedelta(days=d.weekday())
  return dict(type=t,week=str(mon),op=dict(op,id=op.get('id') or 'ai-'+uuid.uuid4().hex[:12]),label=('%d/%d 这周　%s %s %s　%s'%(mon.month,mon.day,who,word,when,op.get('note') or '')).rstrip())
 if t=='package':
  _date(it.get('start'));_date(it.get('end'));n=it.get('perWeek')
  if not isinstance(n,int) or not 1<=n<=20:raise Stop('每周节数 1 到 20')
  return dict(type=t,student=it['student'],start=it['start'],end=it['end'],perWeek=n,note=str(it.get('note') or ''),label='%s　课包 %s 到 %s，每周 %d 节'%(it['student'],it['start'],it['end'],n))
 raise Stop('不支持这类事：%s（不能删除、缴费、发家长）'%t)
def _path(pid):
 if not re.fullmatch(r'[\w-]+',str(pid)):raise Stop('清单编号不对')
 return PENDING/(pid+'.json')
def propose(a):
 raw=sys.stdin.read() if a.file=='-' else Path(a.file).read_text(encoding='utf-8')
 try:obj=json.loads(raw)
 except ValueError as e:raise Stop('清单不是合法的 JSON：%s'%e)
 items=obj.get('items') if isinstance(obj,dict) else None
 if not isinstance(items,list) or not 1<=len(items)<=60:raise Stop('清单要 1 到 60 条')
 names=set(json.loads((DATA/'学生名单.json').read_text(encoding='utf-8')));rows=[clean(x,names) for x in items]
 PENDING.mkdir(exist_ok=True);pid=time.strftime('%m%d%H%M%S')+'-'+uuid.uuid4().hex[:6]
 _path(pid).write_text(json.dumps({'id':pid,'summary':str(obj.get('summary') or '')[:200],'items':rows,'status':'pending'},ensure_ascii=False,indent=1),encoding='utf-8')
 return {'id':pid,'written':False,'show_to_teacher':[r['label'] for r in rows],'note':'还没写。把这几行给老师看，老师说可以才 confirm '+pid}
def _load(pid):
 try:p=json.loads(_path(pid).read_text(encoding='utf-8'))
 except OSError:raise Stop('找不到这份清单：'+pid)
 if p.get('status')!='pending':raise Stop('这份清单已经处理过了')
 return p
def apply_one(it):
 t=it['type']
 if t=='record':
  b={'id':it['txid'],'kind':it['kind'],'student':it['student'],'date':it['date'],'units':it['units'],'note':'AI 接入，老师确认'}
  if it.get('time'):b['time']=it['time']
  return call('/api/ledger/add',b,write=True)
 if t=='content':return call('/api/inbox/text',{'key':'%s|%s'%(it['date'],it['student']),'text':it['text']},write=True)
 if t=='edit':return call('/api/ledger/edit',{k:v for k,v in it.items() if k not in ('type','label')},write=True)
 if t=='package':return call('/api/packages/save',pick(it,('student','start','end','perWeek','note')),write=True)
 if t=='schedule':   # 这个接口按周整体保存：先读这周已有的调整，加上这一条
  w=call('/api/adjust',query={'week':it['week']});return call('/api/adjust/save',{'week':it['week'],'ops':(w.get('ops') or [])+[it['op']]},write=True)
 raise Stop('不支持')
def confirm(a):
 p=_load(a.id);ok,bad=[],[]
 for it in p['items']:
  try:
   r=apply_one(it);ok.append(it['label']+('（已记过）' if isinstance(r,dict) and r.get('duplicate') else ''))
  except Stop as e:bad.append('%s：%s'%(it['label'],e))
 p.update(status='done',ok=ok,bad=bad);_path(a.id).write_text(json.dumps(p,ensure_ascii=False,indent=1),encoding='utf-8')
 return {'written':ok,'failed':bad}
def reject(a):
 p=_load(a.id);p['status']='rejected';_path(a.id).write_text(json.dumps(p,ensure_ascii=False,indent=1),encoding='utf-8');return {'rejected':a.id,'note':'作废了，什么都没写'}
def main():
 for st in (sys.stdin,sys.stdout,sys.stderr):
  try:st.reconfigure(encoding='utf-8',errors='replace')
  except Exception:pass
 P=argparse.ArgumentParser(description='Coda 课达：查和写。说明见 AI接入/00_先读这个.md');S=P.add_subparsers(dest='cmd',required=True)
 def c(name,fn,*args):
  q=S.add_parser(name);q.set_defaults(fn=fn)
  for x,kw in args:q.add_argument(x,**kw)
 opt=dict(nargs='?',default='')
 c('hours',hours,('name',opt),('limit',dict(nargs='?',type=int,default=20)));c('week',week);c('courses',courses,('date',{}));c('gaps',gaps,('name',opt))
 c('texts',texts,('--date',dict(default='')),('--student',dict(default='')));c('log',log,('--month',dict(default='')),('--student',dict(default='')),('--limit',dict(type=int,default=40)))
 c('changes',changes,('name',opt));c('paper',paper,('name',{}));c('sheets',sheets);c('sheet',sheet,('id',{}))
 c('propose',propose,('file',{}));c('confirm',confirm,('id',{}));c('reject',reject,('id',{}))
 a=P.parse_args()
 try:print(json.dumps(a.fn(a),ensure_ascii=False,indent=1))
 except Stop as e:print(e,file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
