"""课表读写：数据/基础排课.json 是唯一的课表；每次修改前，先把旧文件备份到 数据/备份/。"""
import json,re
from 存取公共 import data_dir
from pathlib import Path
from 存取公共 import LOCK,Conflict,revision,write
DAYS=('周一','周二','周三','周四','周五','周六','周日')
COLORS={'red','orange','yellow','green','cyan','blue','purple'}
CLOCK=re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
def files(root):
 data=data_dir(root);return data/'基础排课.json',data/'学生名单.json',data/'备份'
def minutes(value):hour,minute=value.split(':');return int(hour)*60+int(minute)
def load(root):
 schedule,roster,_=files(root);raw=schedule.read_bytes()
 return {'rows':json.loads(raw),'roster':json.loads(roster.read_text()),'revision':revision(raw)}
def validate(rows):
 if not isinstance(rows,list) or len(rows)>500:raise ValueError('课表格式不对')
 seen=set()
 for r in rows:
  if not isinstance(r,dict):raise ValueError('课表格式不对')
  ident=r.get('id')
  if not isinstance(ident,str) or not ident or ident in seen:raise ValueError('课程编号缺失或重复')
  seen.add(ident)
  names=r.get('studentNames')
  if not isinstance(names,list) or not names or not all(isinstance(n,str) and 0<len(n)<=40 for n in names):raise ValueError('学生姓名不对')
  if not isinstance(r.get('name'),str) or not r['name']:raise ValueError('课程名称缺失')
  if r.get('day') not in DAYS:raise ValueError(r['name']+'：星期不对')
  start,end=r.get('start'),r.get('end')
  if not all(isinstance(v,str) and CLOCK.match(v) for v in (start,end)) or minutes(start)>=minutes(end):raise ValueError(r['name']+'：时间不对')
  if r.get('teacher') not in COLORS or not all(c in COLORS for c in r.get('teachers',[])):raise ValueError(r['name']+'：老师设置不对')
  if r.get('units') not in (1,2) or type(r['units']) is not int:raise ValueError(r['name']+'：课时数只能是 1 或 2')
  dual=r.get('dual')
  if dual is not None:
   if not isinstance(dual,dict) or type(dual.get('minutes')) is not int or not 0<dual['minutes']<minutes(end)-minutes(start) or any(dual.get(k) not in COLORS|{'both'} for k in ('left','right')):raise ValueError(r['name']+'：双老师设置不对')
 return rows
def save(root,rows,expected):
 """保存固定课表；课里出现名单里没有的学生，直接新建。"""
 validate(rows)
 import 学生状态
 schedule,_,backups=files(root)
 with LOCK:
  changed,new=write(schedule,rows,expected,backups,'基础排课')
  added=学生状态.ensure_students(root,[n for r in rows for n in r['studentNames']])
  return {'changed':changed,'revision':new,'added':added}
