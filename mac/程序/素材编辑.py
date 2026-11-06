"""照片视频的“改好的那份”：转正、剪头尾。原文件永远不动，改好的另存一份；复制、拖、整理发家长都用改好的那份。
- 自动：新进来的照片视频在后台检查一次（素材编辑工具）：
  · 方向：不自动转（iPhone 的方向标记可靠；相机装在支架上本来就是正的）；偶尔侧着的手动拖 ⟳ 转；
  · 预删除：视频开头或结尾捂住镜头约 2 秒（几乎全黑）＝这段不要，标“预删除”（不删，确认后再移除）。
- 手动：服务管理里点照片视频打开编辑：照片左转/右转；视频剪头尾 + 左转/右转；可以“还原”。
- 记录在 数据/收件箱状态.json 每条资料的 auto（自动检查结果）和 edit（rotate/start/end）；
  改好的文件：手机资料放 数据/整理/已编辑/，相机素材放 ~/Movies/课程与签到_相机素材/已编辑/（大文件不进 iCloud）。"""
import hashlib,json,subprocess,threading,time
from pathlib import Path
import 收件箱
from 存取公共 import LOCK,ensure,read,write
TOOL=Path(__file__).with_name('素材编辑工具')
def tool(job,timeout=600):
 if __import__('os').name=='nt':raise ValueError('剪视频暂时只有 Mac 版，Windows 上可以先发原视频')
 if not TOOL.is_file():raise ValueError('缺少 素材编辑工具，请在 数据/程序 里运行“编译素材编辑工具.command”')
 r=subprocess.run([str(TOOL)],input=json.dumps(job,ensure_ascii=False),text=True,capture_output=True,timeout=timeout)
 try:out=json.loads(r.stdout.strip().splitlines()[-1])
 except Exception:raise ValueError('素材编辑工具没有完成：'+(r.stderr.strip()[-200:] or '未知原因'))
 if out.get('error'):raise ValueError(out['error'])
 return out
def state(root):
 p=收件箱.paths(root)[1];ensure(p,{'version':1,'items':{}});return p
def update(root,item_id,**fields):
 p=state(root)
 with LOCK:
  obj,rev=read(p);rec=obj['items'].setdefault(item_id,{})
  for k,v in fields.items():
   if v is None:rec.pop(k,None)
   else:rec[k]=v
  write(p,obj,rev,收件箱.paths(root)[3],'收件箱状态')
def edited_path(root,item_id,kind):
 """改好的那份放哪：相机素材放 Mac 本地，手机资料放 数据/整理/已编辑。"""
 import 相机导入
 base=(相机导入.STORE/'已编辑') if item_id.startswith('camera/') else (收件箱.paths(root)[2]/'已编辑')
 base.mkdir(parents=True,exist_ok=True)
 return base/(hashlib.sha1(item_id.encode()).hexdigest()[:16]+('.mov' if kind=='video' else '.jpg'))
def edited_file(root,item_id,rec=None):
 """这条资料改好的那份（有的话）。"""
 if rec is None:
  p=state(root);rec=json.loads(p.read_text())['items'].get(item_id,{})
 f=rec.get('edit',{}).get('file')
 return Path(f) if f and Path(f).is_file() else None
def send_path(root,item_id):
 """要发出去的那份：改过就用改好的，否则用原文件。"""
 return edited_file(root,item_id) or 收件箱.resolve(root,item_id)
def apply(root,data,auto=False):
 """{id, rotate, start, end}：按原文件重新做一份改好的（每次都从原文件做，不会越改越糊）；全是默认值＝还原。"""
 item_id=str((data or {}).get('id',''));src=收件箱.resolve(root,item_id)
 kind='video' if src.suffix.lower() in 收件箱.VIDEO else 'photo' if src.suffix.lower() in 收件箱.PHOTO else None
 if not kind:raise ValueError('只有照片和视频能编辑')
 rotate=int(data.get('rotate') or 0)%360
 if rotate not in (0,90,180,270):raise ValueError('只能转 90 度的整数倍')
 start=float(data.get('start') or 0);end=data.get('end');end=float(end) if end not in (None,'') else None
 if kind=='photo':start,end=0,None
 out=edited_path(root,item_id,kind)
 if rotate==0 and start<=0.05 and end is None:
  out.unlink(missing_ok=True);update(root,item_id,edit=None);return {'id':item_id,'edit':None}
 if kind=='photo':tool({'photo':str(src),'out':str(out),'rotate':rotate})
 else:
  job={'in':str(src),'out':str(out),'start':start,'rotate':rotate}
  if end is not None:job['end']=end
  tool(job)
 edit={'rotate':rotate,'start':start,'end':end,'file':str(out),'auto':auto}
 update(root,item_id,edit=edit);return {'id':item_id,'edit':edit}
# ---- 后台自动检查新进来的照片视频
def check_new(root):
 p=state(root);items=json.loads(p.read_text())['items'];n=0
 for x in 收件箱.scan(root):
  if x['kind'] not in ('photo','video') or x.get('final') or 'auto' in items.get(x['id'],{}):continue  # 成片是剪好的，不再自动检查
  rec={}
  try:
   src=收件箱.resolve(root,x['id'])
   # 方向：不再自动转（10-16 用户定）。iPhone 拍学生时一定对着人，陀螺仪写的方向标记可靠；
   # 索尼相机装在支架/稳定器上，卡口朝下，拍出来本来就是正的。偶尔侧着拍的，在缩略图上拖 ⟳ 手动转。
   # （看人脸猜方向的功能还在素材编辑工具里 {"upright":…}，需要时再打开）
   rec['rotate']=0;rec['trust']='拍摄时的方向'
   # 捂镜头预删除也关掉了（10-16 用户定：App 里系统相机拍完有“重拍”，拍坏的当场就丢；相机 App/索尼拍坏的在待上传左滑删或 Mac 上点 ×）
   # if x['kind']=='video':rec['covered']=bool(tool({'covered':str(src)},timeout=180).get('covered'))
  except Exception as e:rec['error']=str(e)[:200]
  update(root,x['id'],auto=rec);n+=1
  if rec.get('rotate') and 'edit' not in items.get(x['id'],{}):
   try:apply(root,{'id':x['id'],'rotate':rec['rotate']},auto=True)
   except Exception:pass
  if rec.get('covered') and items.get(x['id'],{}).get('status','新')=='新':update(root,x['id'],status='预删除')
 return n
def start_worker(root):
 def loop():
  while True:
   try:check_new(root)
   except Exception:pass
   time.sleep(20)
 threading.Thread(target=loop,daemon=True).start()
