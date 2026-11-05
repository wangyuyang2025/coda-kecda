"""Coda · 课达 启动（Windows 双击 .bat 时运行；Mac 也能用）。
- 读 数据/发行版.json 里的端口；
- 端口上已经有程序：是这个文件夹的就直接打开网页；是别的文件夹的（比如旧版本）先关掉它，换成这一个；
- 启动程序（后台、不弹黑窗口），等它起来后用默认浏览器打开；
- 起不来就弹窗说明原因（运行记录.log 的最后几行）。
文件名用英文，是为了 Windows 的 .bat 里不用写中文（.bat 遇到中文容易乱码）。"""
import json,os,socket,subprocess,sys,time,urllib.request,webbrowser
from pathlib import Path
HERE=Path(__file__).resolve().parent          # 程序 文件夹
# 两种文件夹结构：v0.7 起 Coda课达/软件文件（不用动）/程序/（资料在 我的资料/）；以前 Coda课达/数据/程序/（资料就在 数据/）
SOFT=HERE.parents[1] if HERE.parent.name=='数据' else HERE.parent   # 程序的上一层（服务里的 ROOT）
APP=SOFT if HERE.parent.name=='数据' else SOFT.parent              # 放“Mac 点这里”“Windows 点这里”的那一层
if not (SOFT/'我的资料').is_dir() and (SOFT/'示例资料').is_dir():__import__('shutil').copytree(SOFT/'示例资料',SOFT/'我的资料')  # 开源版：第一次打开从示例复制一份；我的资料 不进 git
DATA=SOFT/'我的资料' if (SOFT/'我的资料').is_dir() else SOFT/'数据'
WIN=os.name=='nt'
def port():
 try:return int(json.loads((DATA/'发行版.json').read_text(encoding='utf-8')).get('port',18775))
 except Exception:return 18775
def listening(p):
 with socket.socket() as s:
  s.settimeout(0.3)
  return s.connect_ex(('127.0.0.1',p))==0
def running_root(p):
 try:return json.loads(urllib.request.urlopen('http://127.0.0.1:%d/whoami'%p,timeout=2).read()).get('root','')
 except Exception:return ''
def pids_on(p):
 """哪个进程占着这个端口（关掉旧版本用）"""
 try:
  if WIN:
   out=subprocess.run(['netstat','-ano','-p','tcp'],capture_output=True,text=True,creationflags=0x08000000).stdout
   return {l.split()[-1] for l in out.splitlines() if 'LISTENING' in l and l.split()[1].endswith(':%d'%p)}
  out=subprocess.run(['/usr/sbin/lsof','-tiTCP:%d'%p,'-sTCP:LISTEN'],capture_output=True,text=True).stdout
  return set(out.split())
 except Exception:return set()
def stop(p):
 for pid in pids_on(p):
  if WIN:subprocess.run(['taskkill','/PID',pid,'/F'],capture_output=True,creationflags=0x08000000)
  else:subprocess.run(['/bin/kill',pid],capture_output=True)
 for _ in range(20):
  if not listening(p):return
  time.sleep(0.2)
def start():
 py=Path(sys.executable)
 if WIN and py.name.lower()=='python.exe' and py.with_name('pythonw.exe').is_file():py=py.with_name('pythonw.exe')  # 不弹黑窗口
 log=open(DATA/'运行记录.log','w',encoding='utf-8')
 kw={'cwd':str(APP),'stdout':log,'stderr':subprocess.STDOUT,'stdin':subprocess.DEVNULL}
 if WIN:kw['creationflags']=0x00000008|0x00000200|0x08000000   # 独立运行，关掉窗口也不停
 else:kw['start_new_session']=True
 subprocess.Popen([str(py),'-X','utf8','-B',str(HERE/'课程连接.py')],**kw)
def aq(t):
 """把文字变成 AppleScript 的字符串（以前用 json.dumps，中文被写成 \\u 编码，弹窗根本出不来；10-20 发现）。"""
 return '"'+str(t).replace('\\','\\\\').replace('"','\\"').replace('\n','" & return & "')+'"'
def say(msg):
 if os.environ.get('CODA_TEST_ANSWER'):print('[提示]',msg);return   # 自动测试用
 if WIN:
  import ctypes;ctypes.windll.user32.MessageBoxW(None,msg,'Coda 课达',0x30)
 else:subprocess.run(['/usr/bin/osascript','-e','display dialog %s buttons {"好"} with icon caution'%aq(msg)],capture_output=True)
def setup_done(data):
 try:return bool(json.loads((Path(data)/'发行版.json').read_text(encoding='utf-8')).get('setupDone'))
 except Exception:return False
def my_version():
 try:return str(json.loads((DATA/'发行版.json').read_text(encoding='utf-8')).get('version',''))
 except Exception:return ''
def choose_update(target,old_ver):
 """问老师：更新原来那一份，还是在这里新装一份。返回 True＝更新。"""
 msg=('这台电脑上已经有在用的 Coda 课达（v%s）：\n%s\n\n要把这个新版本 v%s 更新到原来那一份吗？\n课表、学生、账本都在那里，不会动。\n\n选“在这里新装一份”会开始一个全新的、空的 Coda 课达。'%(old_ver,target,my_version()))
 if os.environ.get('CODA_TEST_ANSWER'):print('[问]',msg);return os.environ['CODA_TEST_ANSWER']=='update'   # 自动测试用
 if WIN:
  import ctypes;return ctypes.windll.user32.MessageBoxW(None,msg.replace('在这里新装一份','否'),'Coda 课达（点“是”更新原来那一份）',0x24)==6
 r=subprocess.run(['/usr/bin/osascript','-e','display dialog %s buttons {"在这里新装一份","更新原来那一份"} default button "更新原来那一份" with title "Coda 课达"'%aq(msg)],capture_output=True,text=True)
 return '更新原来那一份' in r.stdout
def pick(cands,ver):
 """电脑上有好几份在用的 Coda 课达：列出来让老师选更新哪一份；选“在这里新装一份”或关掉就返回 None。"""
 items=['v%s · %s'%(ver(x),x) for x in cands]
 if os.environ.get('CODA_TEST_ANSWER'):print('[选]',items);return cands[int(os.environ.get('CODA_TEST_PICK','0'))]
 r=subprocess.run(['/usr/bin/osascript','-e','choose from list %s with title "Coda 课达" with prompt "这台电脑上有好几份在用的 Coda 课达，要把新版本更新到哪一份？（资料都在原来那里，不会动）" default items {%s} OK button name "更新这一份" cancel button name "在这里新装一份"'%('{'+','.join(aq(i) for i in items)+'}',aq(items[0]))],capture_output=True,text=True)
 out=r.stdout.strip()
 return next((x for x,i in zip(cands,items) if i==out),None)
def handoff():
 """10-20：安装包和更新包合成一个（Coda课达_vX.zip）。新解压的这份还没设置过时，先看电脑上有没有在用的 Coda 课达：
 有 → 问一声，把新程序换进原来那一份（资料不动），以后双击这份也直接打开原来那一份；没有 → 照常当新安装。返回 True＝已经交给原来那一份了。"""
 return False  # 开源版：不去找、不去更新电脑上别的 Coda 课达
 if SOFT==APP or setup_done(DATA):return False          # 已经在用的这份：照常打开
 if (DATA/'不更新旧版.json').is_file():return False      # 上次选了“在这里新装一份”
 target=None
 try:target=Path(json.loads((DATA/'已更新到.json').read_text(encoding='utf-8'))['path'])
 except Exception:pass
 if target is None or not target.is_dir():
  try:
   sys.path.insert(0,str(HERE));import 安装更新 as U
   cands=[x for x in U.find() if x.resolve()!=APP.resolve() and setup_done(U.layout(x)['data'])]
   if os.environ.get('CODA_TEST_ONLY'):cands=[x for x in cands if str(x).startswith(os.environ['CODA_TEST_ONLY'])]   # 自动测试：只看测试文件夹，别碰电脑上别的
  except Exception:return False
  if not cands:return False
  def used(x):
   try:return (U.layout(x)['data']/'账本.json').stat().st_mtime
   except Exception:return 0
  cands.sort(key=used,reverse=True)
  if len(cands)==1 or WIN:target=cands[0];ok=choose_update(target,U.version_of(target))   # Windows 弹窗做不了列表，就问最近用过的那份
  else:target=pick(cands,U.version_of);ok=target is not None                              # 不止一份：列出来让老师选
  if not ok:
   (DATA/'不更新旧版.json').write_text(json.dumps({'skipped':[str(x) for x in cands]},ensure_ascii=False),encoding='utf-8');return False
  kw={'creationflags':0x08000000} if WIN else {}
  r=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'安装更新.py'),'--目标',str(target),'--来源',str(APP),'--确定','--不打开'],capture_output=True,text=True,timeout=900,**kw)
  if '✅' not in (r.stdout or ''):
   say('更新没有完成，原来那一份的资料没有动。\n\n'+'\n'.join(((r.stdout or '')+(r.stderr or '')).strip().splitlines()[-4:]));return True
  (DATA/'已更新到.json').write_text(json.dumps({'path':str(target),'at':time.strftime('%Y-%m-%d %H:%M')},ensure_ascii=False),encoding='utf-8')
  say('已经把原来那一份 Coda 课达 更新到 v%s，资料都在。\n以后请打开原来那一份：\n%s\n\n这个新解压的文件夹可以删掉了。'%(my_version(),target))
 prog=next((p for p in (target/'软件文件（不用动）'/'程序',target/'数据'/'程序') if (p/'coda_start.py').is_file()),None)
 if not prog:return False
 kw={'creationflags':0x00000008|0x00000200|0x08000000} if WIN else {'start_new_session':True}
 subprocess.Popen([sys.executable,'-X','utf8','-B',str(prog/'coda_start.py')],cwd=str(target),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kw)
 return True
def main():
 if handoff():return
 p=port()
 old=APP/'数据'   # Windows 从旧结构搬家后，正在用的旧 Python 当时搬不动、只复制了一份；现在用的是新的，把旧的删掉
 if SOFT!=APP and old.is_dir() and set(os.listdir(old))<={'python'}:
  import shutil;shutil.rmtree(old,ignore_errors=True)
 if listening(p) and Path(running_root(p) or '/').resolve()!=SOFT.resolve():stop(p)   # 别的文件夹的 Coda 课达：换成这个
 if not listening(p):
  start()
  for _ in range(60):
   if listening(p):break
   time.sleep(0.25)
 if listening(p):webbrowser.open('http://127.0.0.1:%d/'%p);return
 try:tail='\n'.join((DATA/'运行记录.log').read_text(encoding='utf-8',errors='replace').strip().splitlines()[-3:])
 except Exception:tail=''
 say('Coda 课达 没能启动。\n\n'+tail)
if __name__=='__main__':main()
