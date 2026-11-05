"""操作日志（10-22 用户定）：Mac 和手机上每一次改动都记一条，攒“使用经验”，以后变智能体时当规则和例子。
- 课程连接.py 的 do_POST 在每个改动接口前后调 before() / record()，各页面不用改；
- 一条记：什么时候、在哪做（Mac 哪个页面 / 手机）、动作名（以后 AI 调的就是这个工具名）、对谁、改前→改后（涉及学生的剩余课时）、原因、结果；
- 原因只在少见的事上问（请假、改课、补记录、撤销、合并/删除/暂停学生），页面右下角弹一个可不写的小框，不挡操作；
- 只看看、打开文件夹、复制到剪贴板这类不改资料的不记；照片视频内容、上传的图片不记，长文字截短；
- 存在 资料/操作日志/年-月.jsonl，只在这台电脑上（测试版也一样，只存老师自己电脑）。"""
import datetime,json,threading,uuid
from pathlib import Path
import 存取公共,账本存取
LOCK=threading.Lock()
# 路径 → (动作名, 要不要问原因)。不在表里的改动也记，动作名用路径；SKIP 里的不记
ACTIONS={
 '/schedule/save':('改固定课表',False),'/api/adjust/save':('改这周课表',None),
 '/api/leave/set':('请假',True),'/api/attend':('记上课',False),
 '/api/ledger/add':('记账',False),'/api/ledger/batch':('批量记账',False),'/api/ledger/void':('撤销账目',True),'/api/ledger/edit':('课时单改记录',False),
 '/api/student/enroll':('新生报名',False),'/api/student/merge':('合并学生',True),'/api/student/rename':('改名字',False),
 '/api/student/pause':('暂停上课',True),'/api/student/remove':('删除学生',True),
 '/api/packages/save':('设课包',False),'/api/packages/sync':('课包按周扣',False),
 '/api/gaps/resolve':('补记录',True),'/api/gaps/restart':('改起点',True),
 '/api/sheets/generate':('生成签课表',False),'/api/sheets/upload':('上传签课表',False),'/api/sheets/stash':('签课表放待归档',False),
 '/api/sheets/scanned':('扫描签课表',False),'/api/sheets/commit':('签课表入账',False),'/api/sheets/topaper':('签课表转老课表',False),'/api/sheets/archive':('签课表归档',False),
 '/api/paper/file':('老课表归档',False),'/api/paper/restore':('放回老课表',False),
 '/api/setup':('设置向导',False),
 '/api/inbox/status':('改资料状态',False),'/api/inbox/stage':('资料放进待发',False),'/api/inbox/edit':('剪辑资料',False),
 '/api/inbox/reassign':('资料改学生',False),'/api/inbox/card':('传资料',False),'/api/inbox/text':('写上课内容',False),
 '/api/inbox/missing':('没传资料标记',False),
 '/api/archive/sent':('标记已发家长',False),'/api/archive/trashcut':('删剪好的视频',False),
 '/api/works/copy':('复制作品',False),'/api/works/sent':('作品标已发',False),'/api/works/trash':('删作品',False),'/api/works/drop':('放进作品',False),
 '/api/desk/decide':('允许电脑连接',False),'/api/desk/revoke':('取消设备连接',False),
 '/api/camera/import':('相机导入',False),
 '/api/marks/save':('打点',False),
}
SKIP={'/api/inbox/open','/api/archive/open','/api/works/open','/api/inbox/copyfiles','/api/inbox/prepare','/api/sheets/review','/api/camera/scan','/api/lang','/api/log/reason',}
PAGES={'/':'课程管理','/lesson':'课时管理','/service':'服务管理','/works':'作品管理','/setup':'设置向导','/log':'操作日志'}
DROP={'data','image','images','photo','photos','file','files','b64','html','pdf'}   # 上传的内容不进日志
REASON_KEYS=('reason','note')    # 页面自己已经问过原因的（撤销账目、没传资料）直接拿来用
def folder(root):return 存取公共.data_dir(root)/'操作日志'
def roster(root):
 try:return set(json.loads((存取公共.data_dir(root)/'学生名单.json').read_text(encoding='utf-8')))
 except Exception:return set()
def courses(root):
 """课程编号 → 学生名字（改这周课表的请求里只有课程编号）。"""
 try:return {r['id']:r['name'].split('、') for r in json.loads((存取公共.data_dir(root)/'基础排课.json').read_text(encoding='utf-8')) if r.get('id')}
 except Exception:return {}
def walk(x):
 if isinstance(x,dict):
  for v in x.values():yield from walk(v)
 elif isinstance(x,list):
  for v in x:yield from walk(v)
 elif isinstance(x,str):yield x
def students_in(root,body):
 names=roster(root);ids=courses(root);found=[]
 if isinstance(body,dict) and (isinstance(body.get('student'),str) or isinstance(body.get('students'),list)):   # 写明了是谁（记上课、请假、打点）：不按课程编号把全班算进来
  return [n for n in ([body['student']] if isinstance(body.get('student'),str) else body['students']) if isinstance(n,str)][:30]
 for s in walk(body):
  for n in (ids.get(s) or [p for p in s.split('、') if p in names]):
   if n not in found:found.append(n)
 return found[:30]
def balances(root,names):
 if not names:return {}
 try:return {s['name']:s['balance'] for s in 账本存取.summary(root)['students'] if s['name'] in names}
 except Exception:return {}
def trim(x,depth=0):
 """请求内容留个底：去掉上传的文件、长文字截到 200 字，整条不超过 3000 字。"""
 if depth>6:return '…'
 if isinstance(x,dict):return {k:('（文件，没记）' if k in DROP else trim(v,depth+1)) for k,v in list(x.items())[:60]}
 if isinstance(x,list):return [trim(v,depth+1) for v in x[:60]]+(['…还有 %d 条'%(len(x)-60)] if len(x)>60 else [])
 if isinstance(x,str) and len(x)>200:return x[:200]+'…（%d 字）'%len(x)
 return x
def adjust_ops(root,week):
 try:return {o.get('id'):o for o in json.loads((存取公共.data_dir(root)/'临时调整.json').read_text(encoding='utf-8'))['weeks'].get(str(week),[])}
 except Exception:return {}
def adjust_diff(root,body):
 """改这周课表一次会把整周的调整都发过来：只挑出这次新加的、改过的、去掉的。"""
 old=adjust_ops(root,body.get('week'));new={o.get('id'):o for o in body.get('ops') or [] if isinstance(o,dict)}
 strip=lambda o:{k:v for k,v in o.items() if k not in ('createdAt','updatedAt')}
 return {'added':[o for i,o in new.items() if i not in old],'changed':[o for i,o in new.items() if i in old and strip(o)!=strip(old[i])],'removed':[o for i,o in old.items() if i not in new]}
def tx_student(root,txid):
 try:return next((t['student'] for t in json.loads((存取公共.data_dir(root)/'账本.json').read_text(encoding='utf-8'))['transactions'] if t['id']==txid),None)
 except Exception:return None
def before(root,path,body):
 """改之前先看一眼：涉及哪些学生、他们的剩余课时；改这周课表要知道原来有哪些调整（新加了才问原因）。"""
 if path in SKIP or (isinstance(body,dict) and body.get('dry')):return None   # dry＝只看会改什么，没改
 pre={}
 if path=='/api/adjust/save' and isinstance(body,dict):
  pre['adjust']=diff=adjust_diff(root,body)
  if not any(diff.values()):return None   # 原样再存一遍（页面自动保存），没改东西不记
  names=students_in(root,diff)
 else:names=students_in(root,body) if isinstance(body,(dict,list)) else []
 if path=='/api/ledger/void' and isinstance(body,dict):
  who=tx_student(root,body.get('id'))
  if who and who not in names:names.append(who)
 pre.update(students=names,balances=balances(root,names))
 return pre
def describe(path,body,names,action,pre=None):
 b=body if isinstance(body,dict) else {}
 who='、'.join(names[:6])+('等 %d 人'%len(names) if len(names)>6 else '')
 if path=='/api/leave/set':return '%s %s'%(who,'请假' if b.get('on') else '取消请假')
 if path=='/api/attend':return '%s 记上课'%who
 if path=='/api/marks/save':return '%s 打点 %s%s'%(who,str(b.get('start',''))[11:16],'–'+str(b['end'])[11:16] if b.get('end') else ' 开始')
 if path=='/api/student/merge':return '%s 并到 %s'%(b.get('from',''),b.get('to',''))
 if path=='/api/student/rename':return '%s 改名为 %s'%(b.get('from',''),b.get('to',''))
 if path=='/api/gaps/resolve':
  st=[i.get('status') for i in b.get('items') or [] if isinstance(i,dict)]
  return '%s 补记录：%s'%(who,'、'.join('%s %d 节'%(k,st.count(k)) for k in ('上课','请假','没上') if st.count(k)))
 if path=='/api/adjust/save':
  diff=(pre or {}).get('adjust') or {};KIND={'cancel':'停课','move':'改时间','add':'加课'}
  parts=['%s%s'%(verb,'、'.join(KIND.get(o.get('type'),str(o.get('type'))) for o in diff.get(k,[]))) for k,verb in (('added','新'),('changed','改了'),('removed','撤掉')) if diff.get(k)]
  return '%s 这周（%s 起）%s'%(who,str(b.get('week',''))[5:].replace('-','/'),'，'.join(parts))
 return (who+' ' if who else '')+action
def record(root,path,body,pre,result,device=None,referer=None,reason=None):
 """改完记一条。result：'ok' / '冲突：…' / '失败：…'。返回 (编号, 要不要问原因)。"""
 if pre is None:return None,False
 action,ask=ACTIONS.get(path,(path,False))
 names=list(pre['students'])
 for k in ('name','to'):   # 新生报名、改名：新名字改之前还不在名单里
  if path in ('/api/student/enroll','/api/student/rename') and isinstance(body,dict) and isinstance(body.get(k),str) and body[k] and body[k] not in names:names.append(body[k])
 after=balances(root,names);change={n:[pre['balances'].get(n),after.get(n)] for n in names if pre['balances'].get(n)!=after.get(n)}
 if ask is None:ask=bool(pre['adjust']['added'] or pre['adjust']['changed'])   # 改这周课表：新加、改了才问；只是撤掉调整不问
 b=body if isinstance(body,dict) else {}
 own=next((str(b[k]).strip()[:200] for k in REASON_KEYS if isinstance(b.get(k),str) and b[k].strip() and b[k].strip()!='撤销'),'')
 if own or reason:ask=False
 page=PAGES.get(urlpath(referer),'') if referer else ''
 entry={'id':uuid.uuid4().hex[:12],'at':存取公共.now_aware().isoformat(timespec='seconds'),
  'from':'手机' if device=='iPhone' or b.get('by')=='手机' else 'Mac','page':page,'action':action,'path':path,
  'summary':describe(path,body,names,action,pre),'students':names,'change':change,
  'reason':(reason or own or '')[:200],'result':result,'request':trim(body)}
 write(root,entry)
 return entry['id'],bool(ask and result=='ok')
def urlpath(u):
 from urllib.parse import urlparse
 try:return urlparse(u).path
 except Exception:return ''
def month_file(root,at):return folder(root)/(at[:7]+'.jsonl')
def write(root,entry):
 f=month_file(root,entry['at'])
 with LOCK:
  f.parent.mkdir(parents=True,exist_ok=True)
  with f.open('a',encoding='utf-8') as out:out.write(json.dumps(entry,ensure_ascii=False)+'\n')
def entries(root,month=None):
 base=folder(root)
 files=[base/(month+'.jsonl')] if month else sorted(base.glob('*.jsonl'))[-1:]
 out=[]
 for f in files:
  if not f.is_file():continue
  for line in f.read_text(encoding='utf-8').splitlines():
   try:out.append(json.loads(line))
   except Exception:pass
 return out
def listing(root,month=None):
 months=sorted(p.stem for p in folder(root).glob('*.jsonl')) if folder(root).is_dir() else []
 if month and month not in months:raise ValueError('没有这个月的日志')
 return {'months':months,'month':month or (months[-1] if months else None),'items':list(reversed(entries(root,month)))}
def set_reason(root,data):
 """补原因（右下角小框，或日志页里补写）：{id, reason}。只改这一条，其他不动。"""
 d=data or {};eid=str(d.get('id',''));reason=str(d.get('reason','')).strip()[:200]
 if not eid or len(eid)>20:raise ValueError('请求无效')
 base=folder(root)
 with LOCK:
  for f in sorted(base.glob('*.jsonl'),reverse=True) if base.is_dir() else []:
   lines=f.read_text(encoding='utf-8').splitlines();hit=False
   for i,line in enumerate(lines):
    try:e=json.loads(line)
    except Exception:continue
    if e.get('id')==eid:e['reason']=reason;lines[i]=json.dumps(e,ensure_ascii=False);hit=True;break
   if hit:
    tmp=f.with_name(f.name+'.'+uuid.uuid4().hex[:8]+'.tmp');tmp.write_text('\n'.join(lines)+'\n',encoding='utf-8');tmp.replace(f)
    return {'ok':True}
 raise ValueError('找不到这条记录')
