"""请假标记：数据/请假标记.json。在 Mac 课表（临时安排）或手机课表上给某周某节课的某位学生标“请假”。
标记不记账，只在签课表核对时参考：纸上勾了请假＝请假；纸上没勾请假、但这里标了＝待确认（请人核对）。
一节课在一周里只出现一次（改时间也还是同一节），所以按 周一日期 + 课程编号 + 学生 记。"""
import datetime,json
import 存取公共
from 存取公共 import data_dir
from pathlib import Path
import 周调整存取
from 存取公共 import LOCK,ensure,read,write
def paths(root):data=data_dir(root);return data/'请假标记.json',data/'备份'
def key(week,course,student):return '%s|%s|%s'%(week,course,student)
def all_marks(root):
 store=paths(root)[0]
 return json.loads(store.read_text()).get('marks',{}) if store.exists() else {}
def of_week(root,week):
 """某周的标记：{课程编号: {学生: {by, at}}}，给课表页显示。"""
 week=str(周调整存取.parse_week(week));out={}
 for k,m in all_marks(root).items():
  w,course,student=k.split('|',2)
  if w==week:out.setdefault(course,{})[student]={'by':m.get('by',''),'at':m.get('at','')}
 return out
def find(root,date,course,student):
 """签课表某一行（上课日期、课程编号、学生）有没有请假标记。"""
 week=str(周调整存取.monday(datetime.date.fromisoformat(date)))
 return all_marks(root).get(key(week,course,student))
def set_mark(root,data):
 """标记或取消：{week, course, student, on, by}。by 是“Mac”或“手机”（手机经手机通道转来时由通道填）。只能标这一周实际要上的课里的学生（停了的课不能标）。"""
 if not isinstance(data,dict):raise ValueError('请求无效')
 by=data.get('by') if data.get('by') in ('Mac','手机') else 'Mac'
 week=str(周调整存取.parse_week(data.get('week')));course,student=data.get('course'),data.get('student')
 eff={r['id']:r for r in 周调整存取.load(root,week)['effective']}
 if course not in eff:raise ValueError('这一周没有这节课（可能已停课或课表改过），请刷新')
 if student not in eff[course]['studentNames']:raise ValueError(str(student)+' 不在这节课里，请刷新')
 store,backups=paths(root);k=key(week,course,student)
 with LOCK:
  ensure(store,{'version':1,'marks':{}});obj,rev=read(store)
  if data.get('on'):
   if k not in obj['marks']:obj['marks'][k]={'by':by,'at':存取公共.now_aware().isoformat(timespec='seconds')}
  else:obj['marks'].pop(k,None)
  write(store,obj,rev,backups,'请假标记')
 return {'week':week,'leave':of_week(root,week)}
def label(m):
 """“手机 10/16 14:05” 这样的说明。"""
 try:t=datetime.datetime.fromisoformat(m.get('at',''));when='%d/%d %02d:%02d'%(t.month,t.day,t.hour,t.minute)
 except ValueError:when=''
 return (m.get('by') or '课表')+(' '+when if when else '')
