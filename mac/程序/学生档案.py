"""学生档案（留存）和剪辑文件夹，都在 Mac 本地（不进 iCloud；用户自己备份到云盘）。
- 档案 ~/Movies/课程与签到_学生档案/学生名/
    课堂记录/2026-10-11 周日 08:00/  上课内容.txt（发给家长的那段编号文字）+ 照片视频（改好的那份）
    成果作品/2026-10-11 成片名.mov   剪好的成片（老师剪或学生剪）
  服务管理里点“已发”时把这节课存进“课堂记录”（再点一次＝按现在的内容更新）。
- 剪辑 ~/Movies/课程与签到_剪辑/学生名/2026-10-11/：素材放替身（不复制大文件）；老师或学生剪好**导出回同一个文件夹**，
  就认成这节课的成片；之后可以把原始素材移到废纸篓（用户确认，不直接抹掉），成片存进“成果作品”。
- 记录：数据/学生档案.json {"lessons": {"日期|学生": {folder, at, files}}, "works": {成片编号: {file, at}}}。"""
import datetime,json,os,shutil,subprocess,time
from 存取公共 import data_dir
from pathlib import Path
from 存取公共 import LOCK,ensure,read,write
ARCHIVE=Path(os.environ.get('LESSON_ARCHIVE',str(Path.home()/'Movies'/'课程与签到_学生档案')))  # 测试时用别的文件夹
EDIT=Path(os.environ.get('LESSON_EDIT',str(Path.home()/'Movies'/'课程与签到_剪辑')))
VIDEO={'.mov','.mp4','.m4v'}
WEEK=['周一','周二','周三','周四','周五','周六','周日']
def clean(name):
 import 收件箱;return 收件箱.clean(name)
def record_path(root):return data_dir(root)/'学生档案.json'
def records(root):
 p=record_path(root)
 return json.loads(p.read_text()) if p.exists() else {'lessons':{},'works':{}}
def save_record(root,fn):
 p=record_path(root)
 with LOCK:
  ensure(p,{'version':1,'lessons':{},'works':{}});obj,rev=read(p);fn(obj);write(p,obj,rev,data_dir(root)/'备份','学生档案')
def place(src,dest):
 """放一份到档案：同一块磁盘就做硬链接（不多占空间），否则复制；已经一样就不动。"""
 if dest.exists() and dest.stat().st_size==src.stat().st_size:return
 dest.unlink(missing_ok=True)
 try:os.link(src,dest)
 except OSError:shutil.copy2(src,dest)
# ---- 剪辑文件夹
def edit_folder(student,day):return EDIT/clean(student)/day
def finals(root=None):
 """剪辑文件夹里导出的成片：真文件（不是替身）、视频、导出完成（10 秒没再变）。[{student, day, path, byStudent}]"""
 out=[]
 if not EDIT.is_dir():return out
 for sd in sorted(EDIT.iterdir()):
  if not sd.is_dir():continue
  for dd in sorted(sd.iterdir()):
   if not dd.is_dir():continue
   for f in sorted(dd.iterdir()):
    if f.is_symlink() or not f.is_file() or f.name.startswith('.') or f.suffix.lower() not in VIDEO:continue
    if time.time()-f.stat().st_mtime<10:continue  # 可能还在导出
    out.append({'student':sd.name,'day':dd.name,'path':f,'byStudent':'学生剪' in f.name})
 return out
def linked_sources(student,day):
 """这个剪辑文件夹里的替身各指向哪个原文件。"""
 d=edit_folder(student,day);out=set()
 if d.is_dir():
  for f in d.iterdir():
   if f.is_symlink():
    try:out.add(str(f.resolve()))
    except OSError:pass
 return out
def open_path(path):
 import 跨平台;跨平台.open_path(path)
# ---- 档案
def lesson_folder(student,day,time_label):
 d=datetime.date.fromisoformat(day)
 return ARCHIVE/clean(student)/'课堂记录'/('%s %s%s'%(day,WEEK[d.weekday()],' '+time_label.split('–')[0] if time_label else ''))
def archive_lesson(root,key,text,media):
 """把这节课存进“课堂记录”：上课内容.txt + 照片视频（media: 要发出去的那份文件路径）。按现在的内容同步（多的删、少的补）。"""
 import 收件箱
 day,student=key.split('|',1)
 times=收件箱.lessons(root,[{'date':day+'T00:00:00','students':[student]}])
 folder=lesson_folder(student,day,times.get(key,''));folder.mkdir(parents=True,exist_ok=True)
 keep={'上课内容.txt'}
 if text.strip():(folder/'上课内容.txt').write_text(text.strip()+'\n')
 for i,src in enumerate(media,1):
  name='%02d_%s'%(i,src.name);keep.add(name);place(src,folder/name)
 for f in folder.iterdir():
  if f.name not in keep and not f.name.startswith('.'):f.unlink()
 rec={'folder':str(folder),'at':datetime.datetime.now().isoformat(timespec='seconds'),'files':len(media)}
 save_record(root,lambda o:o['lessons'].__setitem__(key,rec))
 return rec
def archive_works(root,student,day):
 """把这节课剪好的成片存进“成果作品”。"""
 done=[]
 for x in finals():
  if x['student']!=clean(student) or x['day']!=day:continue
  folder=ARCHIVE/clean(student)/'成果作品';folder.mkdir(parents=True,exist_ok=True)
  dest=folder/('%s %s'%(day,x['path'].name));place(x['path'],dest);done.append(str(dest))
  save_record(root,lambda o:o['works'].__setitem__('%s|%s|%s'%(day,clean(student),x['path'].name),{'file':str(dest),'at':datetime.datetime.now().isoformat(timespec='seconds'),'byStudent':x['byStudent']}))
 return done
def trash(paths):
 """移到废纸篓（和在 Finder 里“移到废纸篓”一样，能放回原处；用户自己清空废纸篓才真正删除）。"""
 paths=[str(p) for p in paths if Path(p).exists() or Path(p).is_symlink()]
 if not paths:return 0
 fake=os.environ.get('LESSON_TRASH_DIR')  # 测试时移到这个文件夹，不碰真的废纸篓
 if fake:
  Path(fake).mkdir(parents=True,exist_ok=True)
  for p in paths:shutil.move(p,Path(fake)/(str(time.time_ns())+'_'+Path(p).name))
  return len(paths)
 import 跨平台
 if 跨平台.WIN:return 跨平台.trash_windows(paths)
 js='ObjC.import("Foundation");function run(a){var fm=$.NSFileManager.defaultManager,n=0;a.forEach(function(p){if(fm.trashItemAtURLResultingItemURLError($.NSURL.fileURLWithPath(p),null,null))n++});return n}'
 r=subprocess.run(['/usr/bin/osascript','-l','JavaScript','-e',js,*paths],capture_output=True,text=True,timeout=60)
 try:return int(r.stdout.strip())
 except ValueError:raise ValueError('没能移到废纸篓：'+(r.stderr.strip()[-200:] or '未知原因'))
# ---- 服务管理里的操作
def group_items(root,key):
 import 收件箱
 day,student=key.split('|',1);lst=收件箱.listing(root)
 return lst,[x for x in lst['items'] if x['date'][:10]==day and student in x['students']]
def sent(root,data):
 """点“已发”：这节课的资料标“已发家长”，并存进学生档案（课堂记录 + 成果作品）。data: {key:"日期|学生", text:发给家长的那段文字}"""
 import 收件箱,素材编辑
 key=str((data or {}).get('key',''))
 if '|' not in key:raise ValueError('请求无效')
 _,items=group_items(root,key);items=[x for x in items if x['status'] not in ('已移除','预删除')]
 if not items and not str(data.get('text') or '').strip():raise ValueError('这节课没有资料')  # 只剩文字也能发、能存档
 media=[素材编辑.send_path(root,x['id']) for x in items if x['kind'] in ('photo','video') and not x.get('cut') and not x.get('final')]
 收件箱.mark_sent(root,items,key.split('|',1)[1])
 rec=archive_lesson(root,key,str(data.get('text') or ''),media)
 return dict(收件箱.listing(root),archived=rec,works=0)  # 成片在作品管理里发和存
def trash_cut(root,data):
 """成片好了：把这节课已剪进成片的原始素材（和改好的那份、剪辑文件夹里的替身）移到废纸篓，成片存进“成果作品”。"""
 import 收件箱,素材编辑
 key=str((data or {}).get('key',''));_,items=group_items(root,key)
 cut=[x for x in items if x.get('cut')]
 if not cut:raise ValueError('这节课还没有剪好的成片，原始素材不能删')
 day,student=key.split('|',1);paths=[]
 for x in cut:
  src=收件箱.resolve(root,x['id']);paths.append(src);e=素材编辑.edited_file(root,x['id'])
  if e:paths.append(e)
  side=src.with_suffix(src.suffix+'.json')
  if side.exists():paths.append(side)
 folder=edit_folder(student,day)
 if folder.is_dir():
  targets={str(Path(p).resolve()) for p in paths}
  paths+=[f for f in folder.iterdir() if f.is_symlink() and str(f.resolve()) in targets]
 收件箱.set_status(root,{'ids':[x['id'] for x in cut],'status':'已移除'})
 n=trash(paths);works=archive_works(root,student,day)
 return dict(收件箱.listing(root),trashed=len(cut),works=len(works))
def open_place(root,data):
 """在 Finder 打开：这节课的剪辑文件夹 / 档案里的课堂记录 / 成果作品。"""
 key=str((data or {}).get('key',''));what=(data or {}).get('what')
 if '|' not in key:raise ValueError('请求无效')
 day,student=key.split('|',1)
 if what=='edit':path=edit_folder(student,day)
 elif what=='works':path=ARCHIVE/clean(student)/'成果作品'
 else:
  rec=records(root)['lessons'].get(key)
  if not rec:raise ValueError('这节课还没存档')
  path=Path(rec['folder'])
 if not path.is_dir():raise ValueError('文件夹不在了')
 open_path(path);return {'opened':str(path)}
# ---- 作品管理（成果视频单独一个模块，和服务管理的课堂反馈分开）
def project_sources(root,student,day):
 """剪辑文件夹里的素材替身 → 对应收件箱里的哪几条资料（原文件或改好的那份）。"""
 import 收件箱,素材编辑
 linked=linked_sources(student,day);out=[]
 for x in 收件箱.scan(root):
  if x['kind']!='video' or x['date'][:10]!=day or student not in [clean(n) for n in x['students']]:continue
  try:mine={str(收件箱.resolve(root,x['id']).resolve()),str(素材编辑.send_path(root,x['id']).resolve())}
  except ValueError:continue
  if mine&linked:out.append(x)
 return out
def works(root):
 """作品管理首页：剪辑项目（剪辑文件夹，每个学生每天一个）+ 里面导出的成片 + 已存进“成果作品”的作品。"""
 rec=records(root).get('works',{});projects=[];allf=finals()
 if EDIT.is_dir():
  for sd in sorted(EDIT.iterdir()):
   if not sd.is_dir():continue
   for dd in sorted(sd.iterdir(),reverse=True):
    if not dd.is_dir():continue
    clips=[f.name for f in dd.iterdir() if f.is_symlink() and f.exists()]
    fs=[{'name':f['path'].name,'size':f['path'].stat().st_size,'byStudent':f['byStudent'],'path':'edit/%s/%s/%s'%(sd.name,dd.name,f['path'].name),
         'archived':'%s|%s|%s'%(dd.name,sd.name,f['path'].name) in rec,'sent':rec.get('%s|%s|%s'%(dd.name,sd.name,f['path'].name),{}).get('sent')} for f in allf if f['student']==sd.name and f['day']==dd.name]
    if not clips and not fs:continue
    projects.append({'student':sd.name,'day':dd.name,'clips':clips,'finals':fs})
 projects.sort(key=lambda p:p['day'],reverse=True)
 shelf=[]
 if ARCHIVE.is_dir():
  for sd in sorted(ARCHIVE.iterdir()):
   w=sd/'成果作品'
   if w.is_dir():
    for f in sorted(w.iterdir(),reverse=True):
     if f.is_file() and not f.name.startswith('.'):shelf.append({'student':sd.name,'name':f.name,'size':f.stat().st_size,'path':'arc/%s/成果作品/%s'%(sd.name,f.name)})
 return {'projects':projects,'shelf':shelf,'editRoot':str(EDIT),'archiveRoot':str(ARCHIVE)}
def work_file(rel):
 """作品管理里预览 / 复制用的文件：edit/学生/日期/文件 或 arc/学生/成果作品/文件，只认这两个文件夹里的真文件。"""
 rel=str(rel);base={'edit':EDIT,'arc':ARCHIVE}.get(rel.split('/',1)[0])
 if not base:raise ValueError('找不到这个文件')
 p=(base/rel.split('/',1)[1]).resolve()
 if base.resolve() not in p.parents or not p.is_file():raise ValueError('找不到这个文件')
 return p
def works_copy(root,data):
 """把成片放到剪贴板，到微信里 ⌘V。"""
 paths=[str(work_file(p)) for p in ((data or {}).get('paths') or [])]
 if not paths:raise ValueError('请先选成片')
 import 跨平台
 if 跨平台.WIN:跨平台.copy_windows(paths);return {'copied':len(paths)}
 r=subprocess.run(['/usr/bin/osascript','-l','JavaScript',str(Path(__file__).with_name('复制文件到剪贴板.js')),*paths],capture_output=True,text=True,timeout=20)
 if r.stdout.strip()!='ok':raise ValueError('没能放到剪贴板：'+(r.stderr.strip()[-200:] or '未知原因'))
 return {'copied':len(paths)}
def works_sent(root,data):
 """成片发好了：存进学生档案“成果作品”并记下已发。data: {student, day}"""
 student,day=str((data or {}).get('student','')),str((data or {}).get('day',''))
 done=archive_works(root,student,day)
 if not done:raise ValueError('这个剪辑文件夹里还没有成片')
 now=datetime.datetime.now().isoformat(timespec='seconds')
 def mark(o):
  for k,v in o['works'].items():
   if k.startswith(day+'|'+clean(student)+'|'):v['sent']=now
 save_record(root,mark)
 return dict(works(root),archived=len(done))
def works_trash(root,data):
 """成片好了：把这个剪辑项目用到的原始素材（连同改好的那份、旁边的 json、剪辑文件夹里的替身）移到废纸篓，成片先存进“成果作品”。"""
 import 收件箱,素材编辑
 student,day=str((data or {}).get('student','')),str((data or {}).get('day',''))
 if not [f for f in finals() if f['student']==clean(student) and f['day']==day]:raise ValueError('还没有剪好的成片，原始素材不能删')
 archive_works(root,student,day);used=project_sources(root,student,day);paths=[]
 for x in used:
  src=收件箱.resolve(root,x['id']);paths.append(src);e=素材编辑.edited_file(root,x['id'])
  if e:paths.append(e)
  side=src.with_suffix(src.suffix+'.json')
  if side.exists():paths.append(side)
 folder=edit_folder(student,day)
 paths+=[f for f in folder.iterdir() if f.is_symlink()]  # 替身（包括已经指不到东西的）
 if used:收件箱.set_status(root,{'ids':[x['id'] for x in used],'status':'已移除'})
 trash(paths)
 return dict(works(root),trashed=len(used))
def works_open(root,data):
 student,day,what=str((data or {}).get('student','')),str((data or {}).get('day','')),(data or {}).get('what')
 path=ARCHIVE/clean(student)/'成果作品' if what=='shelf' else edit_folder(student,day)
 if not path.is_dir():raise ValueError('文件夹不在了')
 open_path(path);return {'opened':str(path)}
def works_drop(root,data):
 """不剪了：只清掉剪辑文件夹里的替身（不动原始素材）；文件夹里有成片就不让清。"""
 student,day=str((data or {}).get('student','')),str((data or {}).get('day',''));folder=edit_folder(student,day)
 if [f for f in finals() if f['student']==clean(student) and f['day']==day]:raise ValueError('这里已经有成片了，不能清')
 if folder.is_dir():
  for f in folder.iterdir():
   if f.is_symlink():f.unlink()
  try:folder.rmdir()
  except OSError:pass
 return works(root)
