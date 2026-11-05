"""数据文件的公共读写：版本号、改前备份（放 数据/备份/）、原子替换。调用 write 前要持有 LOCK。"""
import datetime,hashlib,json,os,threading,uuid
from pathlib import Path
LOCK=threading.RLock()
# 时区（10-20 用户定）：界面选中文 → 一律按北京时间算“今天”“现在”；选英文 → 按老师自己电脑的时区。
# 语言存在 资料/界面设置.json，课程连接.py 启动和切换语言时调 set_lang。
LANG='zh'
def set_lang(lang):
 global LANG
 LANG='en' if lang=='en' else 'zh'
def now_aware():
 if LANG=='zh':return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
 return datetime.datetime.now().astimezone()
def now():return now_aware().replace(tzinfo=None)
def today():return now_aware().date()
class Conflict(Exception):pass
def data_dir(root):
 """资料文件夹：v0.7 起的测试版是 软件文件（不用动）/我的资料；以前的（包括自己在用的这套）是 根目录/数据。有“我的资料”就用它。"""
 r=Path(root);return r/'我的资料' if (r/'我的资料').is_dir() else r/'数据'
def revision(raw):return hashlib.sha256(raw).hexdigest()
def dump(obj):return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
def ensure(path,default):
 path=Path(path)
 if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(dump(default))
def write_json(path,obj,indent=1):
 """不留版本号、不备份的小文件（界面设置、学生状态、缺记录确认 ……）：先写临时文件再换名，断电也不会写坏。"""
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=indent),encoding='utf-8');os.replace(temp,path)
def read(path):
 raw=Path(path).read_bytes();return json.loads(raw),revision(raw)
PRUNE=False  # 试用版打开：备份只留最近的（10-19 测试：每存一次就多一份，用几个月会有几千个文件）
def prune(backups,prefix):
 """同一种资料的备份：最近 30 份全留，再往前每天只留最后一份，最多留 90 天。"""
 files=sorted(Path(backups).glob(prefix+'_*.json'))  # 文件名里带时间，按名字排就是按时间
 if len(files)<=60:return
 keep=set(files[-30:]);days={}
 for f in files:days[f.name[len(prefix)+1:len(prefix)+9]]=f
 keep|=set(sorted(days.values())[-90:])
 for f in files:
  if f not in keep:
   try:f.unlink()
   except OSError:pass
def write(path,obj,expected,backups,prefix):
 path=Path(path);old=path.read_bytes()
 if revision(old)!=expected:raise Conflict('数据文件已被别处更新')
 if json.loads(old)==obj:return False,expected
 backups=Path(backups);backups.mkdir(parents=True,exist_ok=True)
 (backups/(prefix+'_'+now().strftime('%Y%m%d_%H%M%S_%f')+'.json')).write_bytes(old)
 if PRUNE:prune(backups,prefix)
 new=dump(obj);temp=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp');temp.write_bytes(new);os.replace(temp,path)
 return True,revision(new)
