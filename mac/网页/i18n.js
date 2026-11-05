/* Coda · 课达 多语言（中文 / English）
 * 做法：页面和程序本身都只写中文；选了 English 时，这个脚本把屏幕上的中文换成英文
 * （按钮、提示、出错信息、弹窗、课时单图片、打印的签课表）。资料（学生名字、备注、课表里的“周一”）一律不动。
 * 中文模式下什么都不做。语言存在浏览器里（coda-lang），第一次按浏览器语言自动选。 */
(function(){
'use strict';
var KEY='coda-lang',lang=window.CODA_LANG,fresh=false;
// 语言以程序里存的为准（界面设置.json）：它还决定按北京时间（中文）还是电脑时区（English）算“今天”
if(lang!=='zh'&&lang!=='en'){try{lang=localStorage.getItem(KEY)}catch(e){}if(lang!=='zh'&&lang!=='en')lang=/^zh/i.test(navigator.language||'zh')?'zh':'en';fresh=!window.CODA_NO_LANG_TOGGLE}
window.CodaLang=lang;
function saveLang(l){return fetch('/api/lang',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':window.CODA_KEY||''},body:JSON.stringify({lang:l})}).catch(function(){})}
if(fresh)saveLang(lang);
window.setCodaLang=function(l){try{localStorage.setItem(KEY,l)}catch(e){}saveLang(l).then(function(){location.reload()})};
// 页面算“今天”“这周”都用 codaNow()：中文按北京时间，English 按电脑时区
window.codaNow=function(){var d=new Date();return lang==='zh'?new Date(d.getTime()+(480+d.getTimezoneOffset())*60000):d};
function addToggle(){
 if(document.getElementById('codalang')||window.CODA_NO_LANG_TOGGLE)return;
 var b=document.createElement('button');b.type='button';b.id='codalang';b.setAttribute('data-noi18n','');
 b.textContent=lang==='en'?'中文':'English';b.title=lang==='en'?'切换成中文':'Switch to English';
 b.onclick=function(){window.setCodaLang(lang==='en'?'zh':'en')};
 var nav=document.querySelector('.modnav .mods');
 if(nav){b.className='tab';b.style.cssText='margin-left:6px;cursor:pointer;border:0;font:inherit';var conn=nav.querySelector('.conn');conn?nav.insertBefore(b,conn):nav.appendChild(b)}
 else{b.style.cssText='position:fixed;top:14px;right:16px;z-index:50;padding:6px 14px;border-radius:999px;border:1px solid #d5dbe5;width:auto;margin:0;background:#fff;color:#223047;font:14px -apple-system,"Microsoft YaHei",sans-serif;cursor:pointer';document.body.appendChild(b)}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',addToggle);else addToggle();
if(lang!=='en'){window.codaT=function(s){return s};return}
document.documentElement.lang='en';

/* ---------- 对照表：中文片段 → 英文。长的先换，短的后换；单个字只在整段就是它时才换（免得把学生名字换掉） ---------- */
var D={
// 导航、标题
'课程管理':'Courses','课时管理':'Lessons','设置向导':'Setup','修改设置':'Settings','课程管理 · 排课':'Courses · Schedule','测试版':'Beta','课达':'Coda','Coda 课达':'Coda',
'每周课表':'Weekly schedule','固定课表':'Regular schedule','临时安排':'This week only','添加课程':'Add course','编辑课程':'Edit course','未排课学生':'Unscheduled students',
// 课程管理
'学生姓名':'Student name','学生名字':'Student name','输入学生姓名':'Enter student name','输入名字':'Enter name','搜索姓名':'Search name','授课方式':'Teaching mode',
'单师':'One teacher','双师':'Two teachers','双师轮流':'Two teachers, alternating','双师一同':'Two teachers together','两位老师一起':'Both teachers together','双师轮流 ':'Two teachers, alternating ',
'老师':'Teacher','红老师':'Red teacher','蓝老师':'Blue teacher','色老师':' teacher','未标老师':'No teacher',
'每次上课扣几课时':'Lessons deducted per class','每次扣一课时':'Deduct 1 lesson each time','每次扣两课时':'Deduct 2 lessons each time','时间':'Time','选择时间':'Choose time','选择星期和时间':'Choose day and time','开始时间':'Start time','分钟':'min','分钟以上）':' min or more)',
'前段':'First part','前段时长':'First part length','前段老师':'First part teacher','后段老师':'Second part teacher','，后段':', second part',
'更多设置：老师、课时、双师':'More: teacher, lessons, two teachers','收起更多设置':'Hide more settings','老师设置':'Teacher settings','老师设置：收起并保存':'Teacher settings: save and close',
'老师设置已保存，之后排课可使用这些老师。':'Teacher settings saved. You can use these teachers when scheduling.','老师设置未保存，请重试。':'Teacher settings not saved. Please try again.',
'保存修改':'Save changes','取消排课':'Unschedule','加入课表':'Add to schedule','退出这节课':'Leave this class','移回待排':'Move back to unscheduled','可单独拖出这位学生':'You can drag this student out alone',
'班课可单独拖出一位学生':'In a group class you can drag out one student','拖入学生安排课程':'Drag a student here to schedule','拖到“未排课学生”取消':'Drag to “Unscheduled students” to cancel',
'课程拖回此栏即可取消排课':'Drag a class back here to unschedule it','暂停上课的':'Paused: ','人没列出（在课时管理里恢复）':' not listed (resume in Lessons)',
'拖动学生到星期，再选时间；修改会自动保存。':'Drag a student onto a day, then pick a time. Changes save automatically.','拖动改时间和星期':'Drag to change day and time','拉卡片下边缘改时长':'Drag the card’s bottom edge to change length',
'按住（或右键）一节课：记上课、标请假（固定课表里是本周那一次）':'Press and hold (or right-click) a class to record attendance or mark leave (in the regular schedule this means this week’s class)',
'课表已从数据文件载入，修改会自动保存。':'Schedule loaded. Changes save automatically.','已保存到数据文件，手机刷新后可见；改动前的版本已备份。':'Saved. The previous version was backed up.','已保存到数据文件':'Saved',
'没有读到数据文件，改动不会保存。请用“启动课程管理”打开。':'Could not read your data, so changes will not be saved. Please open the app from its launcher.',
'本页没有连上数据文件，改动不会保存。请用“启动课程管理”重新打开。':'This page is not connected to your data, so changes will not be saved. Please reopen it from the launcher.',
'数据文件已在别处更新，本页不再保存。请刷新页面后重新修改。':'The data was changed somewhere else. This page will no longer save. Please refresh and try again.','数据文件已被别处更新':'The data was changed somewhere else',
'连接服务不可用，未保存。请勿关闭本页，先启动课程管理。':'Not saved: the app is not running. Keep this page open and start the app first.','连接服务不可用，未保存。请勿关闭本页。':'Not saved: the app is not running. Keep this page open.','连接服务不可用，没记上。':'Not recorded: the app is not running.','连接服务不可用':'The app is not running','服务不可用':'Service unavailable',
'保存失败，数据文件未改动':'Save failed; your data was not changed','保存失败，请再点一次':'Save failed. Please click again','保存失败，请重试':'Save failed. Please try again','未能保存：':'Could not save: ','正在保存…':'Saving…','请重试':'Please try again',
'空档':'Free slots','复制空档（发微信）':'Copy free slots (to send)','看某位老师哪些时间还空着，复制发给家长':'See which times a teacher still has free, and copy them to send to parents','教室（所有老师都没课）':'Room (no teacher has class)',
'灰色＝已经排了课，绿色＝空着（只列':'Grey = booked, green = free (only lists ','）可以约的时间：':') available times:','工作时间：周一到周五':'Working hours: Mon to Fri','已排满':'Fully booked','这一周已经排满了':'This week is fully booked',
'展开固定星期顺序':'Show Mon–Sun order','展开按周一到周日，收起按当天优先':'Expanded: Mon to Sun. Collapsed: today first','收起恢复当天优先':'Collapse: today first',
'临时加课':'Extra class','临时加课：':'Extra class: ','临时约课（只这一周）':'Extra class (this week only)','修改临时课':'Edit extra class','临时调整':'Weekly change','只改这一周的时间':'Change the time for this week only','只改这一周，固定课表不变':'This week only; the regular schedule stays the same',
'本周改时间':'Time changed this week','改时间：':'Time changed: ','停课':'Cancelled','这一周停课':'Cancelled this week','整周停课':'Cancel the whole week','这一周停了':'Cancelled this week','这一周整周停课（':'Whole week cancelled (',
'节固定课全部停课？':' regular classes all cancelled?','把这一周的所有调整恢复成固定课表？':'Undo all changes for this week and go back to the regular schedule?','恢复原样':'Restore','恢复':'Restore','撤销上一步':'Undo','已撤销上一步':'Undone',
'停课；固定课表没变。点“撤销上一步”或':'cancelled; the regular schedule did not change. Click “Undo” or ','可以撤回。':'you can undo it.','固定课表不变；之后可以逐节恢复，或点“恢复原样”。':'The regular schedule is unchanged. You can restore classes one by one, or click “Restore”.',
'已保存。这一周只能改时间、取消或加临时课；老师和课时请在“固定课表”里改。':'Saved. For one week you can only change times, cancel, or add extra classes. Change teachers and lessons in “Regular schedule”.',
'已保存，只影响这一周，固定课表没变。':'Saved. Only this week is affected; the regular schedule did not change.','已回到固定课表，修改会自动保存。':'Back to the regular schedule. Changes save automatically.',
'起这一周：只对这一周有效。':' this week: applies to this week only.','这一周的固定课已经全部停了。':'All regular classes this week are cancelled.','这一周没有课':'No classes this week','这一周已经过去了':'This week is already over',
'这一周刚被别处改过':'This week was just changed somewhere else','这一周的调整刚被别处改过，请刷新页面后再改':'This week was just changed somewhere else. Please refresh and try again','，已刷新，请重新操作。':'; refreshed, please try again.',
'这一周没有这节课（可能已停课或课表改过），请刷新':'This class is not in this week (it may be cancelled or the schedule changed). Please refresh',
'已保存，并新建学生：':'Saved, and added new students: ','已新建学生：':'New students added: ','已加入':'Added','加入：':'Added: ','已并入':'Merged into','已单独排到':'Moved alone to','已排到':'Moved to','已框选':'Selected','已把框选的':'Moved the selected ','已选':'Selected',
'已退出这节课，回到未排课学生。':'left this class and went back to unscheduled students.','的这次排课已移除。仍有其他课程的学生会继续显示在课表中。':'’s class was removed. Students with other classes stay on the schedule.',
'的课时间重叠：':'’s classes overlap: ','这节课在':'This class is in ','这节课。':'this class.','这节课还没保存好，稍等一下再操作。':'This class is not saved yet. Please wait a moment.',
'请选择开始时间':'Please choose a start time','请选择当天有效时间':'Please choose a valid time that day','，请选择时间后点“':', choose a time and click “','时段不能跨到次日':'A class cannot run past midnight','正在调整':'Adjusting',
'记上课':'Record lesson','已记上课':'Lesson recorded','已记上课，扣':'Lesson recorded, deducted ','这节课已经记过':'This class is already recorded','节课还没到日子，先不记上课，到了再核对':' classes are not due yet; record them on the day',
'请假':'Leave','已记请假':'Leave recorded','取消请假：':'Leave removed: ','的请假标记已取消。':'’s leave mark was removed.','在课表上标了请假':'marked leave on the schedule','在课表上标了请假，请核对':'marked leave on the schedule, please check',
'已标请假（只是标记，不扣课时）。签课表核对时：纸上勾了请假就算请假；纸上没勾会请你确认。':'Leave marked (a mark only, no lesson deducted). When checking the sign-in sheet: a ticked box counts as leave; otherwise you will be asked to confirm.',
'这节课在临时安排里停了':'This class is cancelled this week','这节课本周停了（或还没保存好），没有可记的。':'This class is cancelled this week (or not saved yet); nothing to record.','，还没到，不能先记上课（请假可以提前标）':' has not happened yet, so it cannot be recorded (leave can be marked early)',
'还在固定课表里，请先在课程管理里把他拖回“未排课学生”':' is still on the regular schedule. In Courses, drag them back to “Unscheduled students” first','在临时安排里还有课，请先删掉那节临时课':' still has an extra class this week. Delete that extra class first',
'找不到这节课，课表可能已变，请刷新页面':'Class not found. The schedule may have changed; please refresh','不在这节课里，请刷新':' is not in this class, please refresh',
'班课':'Group class','共同':'Together','一起':'together','排课':'Schedule','课表':'Schedule','课程名称缺失':'Course name missing','课程编号缺失或重复':'Course ID missing or duplicated','课程编号重复，请核对排课':'Duplicate course ID, please check the schedule','课表格式不对':'Schedule format is wrong',
'：星期不对':': wrong day','：时间不对':': wrong time','：老师设置不对':': wrong teacher','：双老师设置不对':': wrong two-teacher settings','：课时数只能是':': lessons can only be ','：请填':': please fill in ','临时课的学生姓名不对':'Student name for the extra class is wrong',
'调整内容格式不对':'Change format is wrong','调整类型不对':'Change type is wrong','调整编号缺失或重复':'Change ID missing or duplicated','这周只能有一条调整':'Only one change per class per week','周的日期不对':'Week date is wrong','每周从周一算起，请选周一的日期':'Weeks start on Monday; please choose a Monday',
'读取本周课表失败：':'Could not read this week’s schedule: ','读取课表失败':'Could not read the schedule','出勤状态不对':'Attendance status is wrong',
// 补充（第一轮检查漏掉的）
'”扫描。':'”.','。拉卡片下边缘可改时长，左边可改老师和课时。':'. Drag the card’s bottom edge to change length; change teacher and lessons on the left.','。记课时账时按这个数扣，记账时也可以单独改。':'. This many lessons are deducted each time; you can change it when recording.',
'。请勿关闭本页。':'. Please keep this page open.','一键生成本周签课表并打开':'Create this week’s sign-in sheet and open it','上下拉动调整时长':'Drag up or down to change length','上课了：':'Attended: ','临时安排里停了，不入账':'cancelled this week, not recorded',
'二维码五分钟有效，仅可使用一次。':'The QR code is valid for 5 minutes and can be used once.','二维码生成失败，请确认连接服务已开启':'Could not create the QR code. Make sure the app is running','关闭二维码':'Close QR code','作品管理':'Works','服务管理':'Services',
'学生姓名不对':'Wrong student name','就够）':' is enough)','已登记':'Set','未登记':'Not set','开始使用时剩余课时':'Lessons left when starting','欠课填负数':'negative if they owe',
'手机':'Phone','手机只能查看课表和上传资料':'The phone can only view the schedule and upload materials','手机左滑，点“扫码连接':'On the phone, swipe left and tap “Scan to connect','手机已连接':'Phone connected','手机未连接':'Phone not connected','手机连接':'Phone connection','手机连接情况':'Phone connection status','手机配对二维码':'Phone pairing QR code','未连接手机':'No phone connected',
'正在检查设备连接…':'Checking devices…','正在生成二维码…':'Creating QR code…','点击生成配对二维码':'Click to create a pairing QR code','请使用手机扫码连接':'Scan with your phone to connect','连接设备':'Connect device','连接服务':'App service',
'没有这个文件':'No such file','没标上：':'Not marked: ','没记上：':'Not recorded: ','签课识别工具无法运行：':'The recognition tool could not run: ','识别工具没有完成：':'The recognition tool did not finish: ','识别工具没有反应。如果屏幕上弹出“无法验证开发者”，请到':'The recognition tool did not respond. If you saw “cannot verify the developer”, go to ',
'系统设置':'System Settings','隐私与安全性':'Privacy & Security','里点“仍要打开”，再导入一次':', click “Open Anyway”, then import again','这台电脑打不开':'This computer cannot open ','请上传':'Please upload ','请填名字':'Please enter a name','请选一个学生':'Please choose a student','请假标记':'Leave mark',
'结束于':'Ends ','节课在':' classes on ','，以后在课时管理里补。':'; add them later in Lessons.','，手机刷新后可见':'','课程资料暂不可读取，请在':'Course materials cannot be read right now; please ','检查数据文件夹。':'check the data folder.',
'蓝色':'Blue','红色':'Red','橙色':'Orange','黄色':'Yellow','绿色':'Green','青色':'Cyan','紫色':'Purple',
'这张签课表都已经入账了，没有要记的，点“稍后再核对”关掉就行。':'Everything on this sheet is already recorded. Click “Check later” to close.','请先对照签字图核对一遍，然后勾上下面“我已逐行核对过学生、签字和请假”，再点确认入账。':'Check the rows against the signature image first, tick “I have checked every row: students, signatures, and leave” below, then click Confirm and record.',
'小明 10\n小红 8\n小刚':'Emma 10\nLiam 8\nNoah',
'刚才那张已放进“不要的”（没有删除）。点错了可以撤销。':'That photo was moved to “Discarded” (not deleted). Clicked by mistake? You can undo.','点“不要”的照片都在这里，没有删除。点“放回”就回到待归档。':'Photos you discarded are kept here, not deleted. Click “Put back” to return one to the archive queue.',
'放回':'Put back','已放回待归档':'Put back in the archive queue','回到待归档':'Back to archive queue','不要的 ':'Discarded ','待归档 ':'To archive ','没有了':'Nothing here',
'合并到另一个名字…':'Merge into another name…','合并「':'Merge “','」':'”','同一个学生在名单里有两个名字时用：把这个名字的课时、课表、老课表都并到另一个名字下，然后这个名字就没了。':'Use this when one student has two names. Lessons, schedule and paper records move to the other name, and this name is removed.',
'合并到（保留的名字）':'Merge into (name to keep)','请选择…':'Choose…','名字相近':'Similar names','全部学生':'All students','选一个要保留的名字。':'Choose the name to keep.','会搬过去：流水 ':'Will move: ','合并':'Merge',
'两边都有起始余额：保留较新的，撤销较早的那条（':'Both have a starting balance: the newer one is kept and the older one is undone (','合并后按「':'after merging, the status of “','」自己的状态':'” is used','」是暂停上课的；':'” is paused; ',
'注意：服务管理 / 作品管理里「':'Note: Services / Works data for “','」的资料不会搬，还留在原来的名字下。':'” is not moved and stays under the old name.','合并前会自动备份。':'A backup is made before merging.','确定把「':'Merge “','」合并到「':'” into “','」？':'”?',
'已把 ':'Merged ',' 合并到 ':' into ','两个名字都要在名单里':'Both names must be on the list','请选另一个名字':'Please choose a different name','在同一时段都记过课（':' both have records at the same time (','），请先在流水里撤销重复的那条再合并':'). Undo the duplicate in History first, then merge',' · 课表里 ':' · classes on schedule: ',' · 老课表照片 ':' · paper photos: ',
'从起点到昨天，课表上有课、但没记上课也没记请假的。起点登记得不对就改起点；真的漏记了就一节节选。':'Classes on the schedule from the starting point to yesterday with no lesson or leave recorded. If the starting point is wrong, change it; if records were really missed, choose for each class.',
'先把缺的记录补完，课时单上的余额才是对的；补完就能生成课时单。':'Fill in the missing records first so the balance on the statement is right; then you can create the statement.',
'起点登记得不对？改起点':'Starting point wrong? Change it','填“截至哪天（算上那天的记录）还剩几节”。那天之前的缺口就不用补了；旧起点会撤销，流水里看得到。':'Enter how many lessons were left as of a date (including that day). Gaps before it no longer need filling; the old starting point is undone and stays visible in History.',
'那天还剩几节':'Lessons left that day','改起点':'Change starting point','起点改好了':'Starting point changed','全部选：':'Set all: ','没这节课':'No class','补录时间':'Other time','老课表照片（点开对照）：':'Old schedule photos (tap to compare): ','实际上课：':'Actual lesson: ','补录时间：请填实际上课的日期和钟点':'Other time: fill in the actual date and time','确认选好的':'Confirm selected','没有缺的了 🎉':'Nothing missing 🎉','起点：':'Starting point: ','还没有起点':'No starting point yet',
'读不到缺记录':'Could not load missing records','的缺记录补完了':': missing records done','已确认 ':'Confirmed ','请填那天还剩几节':'Please enter lessons left that day','还没选：每一节选 上课 / 请假 / 没这节课（可以用上面的“全部选”）':'Nothing chosen: pick Lesson / Leave / No class for each (or use “Set all” above)',
'把 ':'Change ',' 的起点改成：截至 ':'’s starting point to: as of ',' 还剩 ':', lessons left ','点这里补记录':'Click to fill in missing records','起点不能是以后的日期':'The starting point cannot be in the future','请填那天还剩几节课（整数，欠课填负数）':'Please enter lessons left that day (whole number; negative if owed)','请为每一节选 上课 / 请假 / 没这节课':'Choose Lesson / Leave / No class for each','请至少选一节':'Choose at least one',
'同班：':'Classmates: ','没记':'not recorded',
'这样保存会把 ':'Saving this will remove ','从这节课里去掉（他们会回到“未排课学生”）。':'from this class (they go back to “Unscheduled students”).','只想把某一个学生挪到别的时间，请直接拖他的名字。':'To move just one student to another time, drag their name instead.','确定要去掉吗？':'Remove them?',
'请不要直接打开这个网页：回到 Coda 课达 文件夹，双击“Mac 点这里”（Windows 是“Windows 点这里”）':'Please don’t open this page directly: go back to the Coda folder and double-click “Mac 点这里” (on Windows, “Windows 点这里”)',
'程序没在运行：请回到 Coda 课达 文件夹，双击“Mac 点这里”（Windows 是“Windows 点这里”），再在打开的网页里填':'The app is not running: go back to the Coda folder, double-click “Mac 点这里” (on Windows, “Windows 点这里”), then fill this in on the page that opens',
'没有读到数据文件，改动不会保存。请用“Mac 点这里”（Windows 是“Windows 点这里”）打开。':'Could not read your data, so changes will not be saved. Open the app with “Mac 点这里” (on Windows, “Windows 点这里”).',
'本页没有连上数据文件，改动不会保存。请用“Mac 点这里”（Windows 是“Windows 点这里”）重新打开。':'This page is not connected to your data, so changes will not be saved. Reopen it with “Mac 点这里” (on Windows, “Windows 点这里”).',
'读不到账本，请用“Mac 点这里”（Windows 是“Windows 点这里”）打开本页。':'Could not read the ledger. Open this page with “Mac 点这里” (on Windows, “Windows 点这里”).',
'识别到 ':'Recognized ',' 个学生：':' students: ','学生名单里有 ':'The student list has ',' 处要改一下（下面红字），改好再点完成':' problem(s) (in red below). Fix them, then click Done',
'前面没有名字':' has no name before it','：剩余课时要写整数（写的是 ':': lessons left must be a whole number (you wrote ','：看不懂“':': cannot read “','”是几节':'” as a number','：名字里有空格。名字和课时之间空一格，名字本身别带空格':': the name has a space. Put one space between the name and the number, but no spaces inside the name',
'”不像名字':'” does not look like a name','：名字最长 12 个字，不能有斜杠':': names can be at most 12 characters, no slashes',' 写了两次，只留第一次':' is listed twice; only the first is kept','不像学生名字（名字里不能有空格，也不能只是数字）':'does not look like a student name (no spaces, not just a number)',
'例如：\n小明 10\n小红 8\n小刚（不写就是 0）':'e.g.\nEmma 10\nLiam 8\nNoah (blank = 0)',
'课表刚在别的窗口里改过，这一下的改动没有保存。':'The schedule was just changed in another window, so this change was not saved.','点“好”会刷新成最新的课表，请再改一次。':'Click OK to reload the latest schedule, then make the change again.','这一周刚在别的窗口里改过，这一下的改动没有保存。':'This week was just changed in another window, so this change was not saved.','点“好”会刷新成最新的样子，请再改一次。':'Click OK to reload, then make the change again.',
' 已经有课了':' already has a class',' 这位老师已经在上「':' this teacher is already teaching “','」':'”','时间撞了。确定还要这样排吗？':'Time clash. Schedule it anyway?',
'改名字…':'Rename…','把「':'Rename “','」改成什么名字？':'” to:','（课时、课表、老课表都会跟着改）':'(lessons, schedule and paper records follow the new name)',' 已改名为 ':' renamed to ','请写新名字':'Please enter a new name',
' 已经在名单里了；同一个人有两个名字请用“合并到另一个名字”':' is already on the list; if it is the same person, use “Merge into another name”','新名字最长 12 个字，不能有空格、逗号、顿号、斜杠，也不能只是数字':'The new name can be at most 12 characters, with no spaces, commas or slashes, and not just a number',
'」的照片视频还在原来的名字下，没有跟着改。':'” photos and videos stay under the old name.',
'一周上两节：已经排了课的学生，在这里再输入名字、选另一个时间就行。':'Twice a week: for a student who already has a class, type their name here again and pick another time.',
'全部老师':'All teachers','只看 ':'Only ','整节 ':'Whole class ','这天没有这位老师的课':'No classes for this teacher','只看某位老师的课':'Show one teacher only',
'写你的名字就行。有别的老师一起上课，再点下面加一位，课表里会用颜色分开。':'Just your name. If another teacher works with you, add them below; the schedule shows each teacher in a color.','＋ 还有别的老师':'+ Add another teacher','只有我一位老师':'Just me','老师名字（必填）':'Teacher name (required)','第二位老师的名字':'Second teacher’s name','课表里蓝色、红色分别是这两位老师。':'Blue and red in the schedule are these two teachers.',
'欢迎使用 Coda · 课达':'Welcome to Coda','欢迎使用 · Coda 课达':'Welcome · Coda','修改设置 · Coda 课达':'Settings · Coda',
'上课扣 ':'Lesson deducts ','上课 −':'Lesson −','选了 ':'Selected ','：上课 ':': lessons ','（共扣 ':' (deducts ',' 课时）· 请假 ':' in total) · leave ',' · 没这节课 ':' · no class ','每一节选 上课 / 请假 / 没这节课':'Choose Lesson / Leave / No class for each',
'同班的 ':'Classmates ',' 这几节也还没记。':' also have these classes unrecorded.','要按一样的（上课 / 请假 / 没这节课）一起记上吗？':'Record them the same way (lesson / leave / no class)?','点“取消”就只记 ':'Click Cancel to record only ','，同班同学一起记了 ':', and classmates recorded: ',
'课包…':'Package…',' · 课包':' · Package','课包期间（比如暑假）不按课表一节节扣、也不算缺记录，':'During a package (e.g. summer), lessons are not deducted class by class and gaps are not counted; ','按周扣':'deducted weekly','：每周默认扣“每周节数”，哪周请了假就把那周改小；一周过完（周日）才扣。交钱照常点“缴费”。':': each week deducts the weekly number by default; lower a week if they missed classes. Deducted after the week ends (Sunday). Record payments with “Payment” as usual.',
'新建课包':'New package','开始':'Start','结束':'End','每周节数':'Per week','比如：暑假课包':'e.g. summer package','建课包':'Create','删除这个课包':'Delete package','已扣':'Deducted','这周还没过完':'This week','以后':'Later','还没有课包':'No packages yet','共扣 ':'Total ','（已扣 ':' (deducted ','。改了周数直接保存。':'). Changes save automatically.','请选结束日期':'Please choose an end date',
'删除这个课包？已经按周扣的会撤销（流水里看得到）。':'Delete this package? Weekly deductions already made will be undone (visible in History).','每周 ':'per week ',
'在课包期间，按周扣，这一行不另外扣':' is in a package period (deducted weekly); this row is not deducted','这段时间是课包，按周扣，不用一节节记；要改这周扣几节，去课时管理“…”→“课包”':' is on a package for this period (deducted weekly). To change a week, go to Lessons “…” → “Package”',
'）时间重合了。':') overlaps.','要并成一节班课吗？':'Merge into one group class?','点“取消”就单独排在 ':'Click Cancel to schedule separately at ',' 已并进 ':' merged into ',' 这节课，现在是：':'; the class is now: ',
'这是签课表 → 送去识别':'This is a sign-in sheet → recognize','这是老课表 → 放进纸质课表归档':'This is an old paper record → archive it','已当成签课表识别；那张照片从待归档挪进了“不要的”':'Recognized as a sign-in sheet; the photo was moved from the archive queue to “Discarded”','没认出签课表（要拍到四个角的黑块），照片还留在待归档':'No sign-in sheet found (the four black corners must be in the photo); the photo stays in the archive queue',
'把这张当成老课表，放进“纸质课表归档”？':'Treat this as an old paper record and move it to the paper archive?','这次的识别结果会拿掉（备份里留着）。':'This recognition result will be removed (a backup is kept).','已放进纸质课表归档，点“待归档”去归档':'Moved to the paper archive; click “To archive” to file it',
'这张已经入账了 ':'This sheet already has ',' 行，不能改成老课表；要改先在课时管理的流水里撤销':' rows recorded and cannot become an old record; undo them in History first','找不到原来的照片':'Original photo not found','PDF 扫描件不能放进纸质课表（那里只收照片）':'PDF scans cannot go to the paper archive (photos only)',
'没认出签课表：':'No sign-in sheet recognized: ','。照片还留在待归档。':'. The photo stays in the archive queue.',
'怎么办：① 纸放平、正对着、光线均匀，四个黑角都拍进去，用手机 App「收集 → 拍签课表」重拍（拍完会直接识别）；② 用扫描仪扫一下，点上面的「导入签字扫描件」；③ 实在认不出，在课程管理里按住那节课直接记上课 / 请假。这张拍坏的可以点「不要」。':'What to do: ① lay the paper flat, shoot straight on in even light with all four black corners, and retake it in the phone app (Collect → Scan sign-in sheet); ② or scan it with a scanner and use “Import signed scans” above; ③ if it still fails, record lessons / leave directly by holding the class in Courses. You can click “Discard” for this bad photo.',
// 星期
'周一':'Mon','周二':'Tue','周三':'Wed','周四':'Thu','周五':'Fri','周六':'Sat','周日':'Sun','本周':'This week','上周':'Last week','下周':'Next week','下下周':'Week after next','本月':'This month','上月':'Last month','上一周':'Previous week','下一周':'Next week',
// 颜色
'蓝':'Blue','红':'Red','橙':'Orange','黄':'Yellow','绿':'Green','青':'Cyan','紫':'Purple',
// 课时管理
'余额 = 起始余额 + 缴费 − 上课。记错了不用改，点“流水”撤销即可，历史会保留。':'Balance = starting balance + payments − lessons. Made a mistake? Undo it in “History”; nothing is erased.',
'上课。记错了不用改，点“流水”撤销即可，历史会保留。':'lessons. Made a mistake? Undo it in “History”; nothing is erased.',
'余额':'Balance','起始余额':'Starting balance','缴费':'Payment','上课':'Lesson','流水':'History','课时单':'Lesson statement','手动调整':'Adjust','暂停上课':'Pause lessons','恢复上课':'Resume lessons','删除这个学生':'Delete this student',
'全部':'All','欠课':'Owes lessons','未登记起始余额':'No starting balance','打印本周签课表':'Print this week’s sign-in sheet','打印其他周':'Print another week','打印其他周签课表':'Print another week’s sign-in sheet','导入签字扫描件':'Import signed scans',
'＋ 新生报名':'+ New student','新生报名':'New student','报名':'Enroll','报名日期':'Enrollment date','缴费课时数':'Lessons paid','金额（元，可不填）':'Amount (optional)','暂停上课（先不排课）':'Pause lessons (do not schedule yet)',
'报名后会出现在课程管理左边的“未排课学生”里，拖进课表就排好时间了。':'After enrolling, the student appears under “Unscheduled students” in Courses. Drag them onto the schedule to set a time.',
'报名后标为暂停上课，不会出现在课程管理里；以后在他那一行点“恢复上课”。':'The student will be marked as paused and will not appear in Courses. Later, click “Resume lessons” on their row.',
'已报名':' enrolled','，去课程管理排时间':'. Go to Courses to schedule','（暂停上课）':' (paused)','已经在名单里了；要缴费请在他那一行点“缴费”':' is already on the list. To add a payment, click “Payment” on their row','请填学生名字（一个人一个名字）':'Please enter the student’s name (one person per name)',
'登记起始余额':'Set starting balance','批量登记起始余额':'Set starting balances','批量登记起始余额（':'Set starting balances (','批量登记':'Bulk entry','位学生的起始余额':' students’ starting balances',
'填每位学生现在':'Enter each student’s current ','剩余的课时数':'remaining lessons','（欠课填负数）。不填的先跳过，以后再补。按回车跳到下一个。':' (negative if they owe). Blank ones are skipped for now. Press Enter for the next one.','截至日期':'As of',
'老课表归档时会自动登记；没有老课表的学生在这里批量填。':'Filled in automatically when you archive an old paper sheet. For students without one, fill in here.','人未登记':' not set',
'要续费':'Needs renewal','暂时没有人需要续费':'No one needs to renew right now','人（不提醒）':' (no reminders)','点名字打开课时单':'Click a name to open the statement','打开课时单':'Open statement','没有符合条件的学生':'No matching students',
'名学生':' students','个学生':' students','欠':'owes ','最近':'Last ','上课人次':'Lesson visits','请假人次':'Leave count','人次':' visits','上课扣课时':'Lessons deducted','销课':'Lessons used',
'记一次上课':'Record a lesson','记一次请假（不扣课时）':'Record leave (no lesson deducted)','手动调整课时':'Adjust lessons','日期':'Date','课时数':'Lessons','时段（可不填，例如':'Time (optional, e.g. ','备注':'Note','（可不填）':' (optional)','（必填）':' (required)',
'起始余额（课时，欠课填负数）':'Starting balance (lessons; negative if they owe)','调整课时数（加课填正数，扣课填负数）':'Adjustment (positive to add, negative to deduct)','调整课时数':'Adjustment',
'已记录：':'Recorded: ','撤销':'Undo','已撤销':'Undone','撤销原因（可不填）：':'Reason for undo (optional):','还没有记录':'No records yet','记录':'Record','，还可以再撤销':', can be undone again',
'只有没上过课、没缴过费、不在课表里的学生能删；不来了请用“暂停上课”。':'Only students with no lessons, no payments, and no scheduled class can be deleted. If they stopped coming, use “Pause lessons”.','删除“':'Delete “','已删除':'Deleted',
'已经有上课或缴费记录，不能删除；不来了请用“暂停上课”':' has lesson or payment records and cannot be deleted. If they stopped coming, use “Pause lessons”','已标为暂停上课':' marked as paused','已恢复上课':' resumed',
'课时记录':'Lesson record','截至':'As of','，剩余':', remaining','剩余':'Left','课时':'lessons','（已欠课）':' (owes)','内容':'Item','签字':'Signature','复制图片（粘贴到微信）':'Copy image (to paste in chat)','保存图片':'Save image','已复制':'Copied','，可直接粘贴到微信':', ready to paste',
'复制没有成功：请允许浏览器访问剪贴板，或点“保存图片”':'Copy failed: allow clipboard access in your browser, or click “Save image”','这个浏览器不支持复制图片，请点“保存图片”':'This browser cannot copy images; please click “Save image”',
'上次缴费前结余':'Balance before last payment','从最近一次缴费（':'From the latest payment (','）到今天':') to today','正在生成…':'Generating…',
'读不到账本，请用“启动课程管理”打开本页。':'Could not read the ledger. Please open this page from the launcher.',
'这个学生不在名单里':'This student is not on the list','名单里没有这个学生':'This student is not on the list','没有这个学生':'No such student','日期不对':'Wrong date','记录类型不对':'Wrong record type','记录编号无效':'Invalid record ID','请求无效':'Invalid request','请求无效或文件太大':'Invalid request or file too large',
'备注请控制在':'Keep notes within ','字内':' characters','要在':' must be between ','之间的整数':' (whole number)','到':' and ','缴费课时数要在':'Lessons paid must be between ','金额不对':'Wrong amount','手动调整不能为':'Adjustment cannot be ','，并且要写备注':', and needs a note',
'时间格式不对，例如':'Wrong time format, e.g. ','这个学生已登记过起始余额；要改请先撤销，或用“手动调整”':'This student already has a starting balance. To change it, undo it first or use “Adjust”','这个学生这天这个时段已经记过了':'This student is already recorded for this time on this day',
'这条记录已经撤销过了':'This record was already undone','找不到这条记录':'Record not found',
// 签课表
'签课表':'Sign-in sheet','每周上课签到表':'Weekly sign-in sheet','打印':'Print','生成并打开打印页':'Create and open print page','待打印':'To print','重新生成':'Regenerate','已生成的签课表（点一下打开，可再打印）':'Created sheets (click to open and print again)',
'按这一周实际要上的课生成（临时安排里停的课不打印，临时加的课会打印），班课一人一行。打印时选“实际大小':'Made from this week’s actual classes (cancelled ones are left out, extra ones included); one row per student in group classes. When printing, choose “Actual size',
'、实际大小、无边距':', actual size, no margins','打印设置：纸张':'Print settings: paper ','，缩放':', scale ','，边距':', margins ','实际大小':'Actual size','。四个角的黑块要完整打出来。':'. The four black corner squares must print completely.','”，四个角的黑块要完整。':'”; the four black corner squares must be complete.',
'签字表示已上课；请假勾选方框。空白待确认。请保留四角黑色定位标记。':'Sign = attended; tick the box = leave; blank = to confirm. Keep the four black corner marks.','签字为课堂签课表扫描截图':'Signatures are from the scanned sign-in sheet',
'签字格':'Signature','请假框':'Leave box','请假请勾选方框':'Tick the box for leave','学生':'Student','生成于':'Created ','编号':'No.','页':'page',
'本周人数过多，签字空间不足，请分批生成':'Too many students this week to fit; please print in batches','签课表最多':'A sheet holds at most ','行；请减少本次打印的课程':' rows; please print fewer classes','表单编号不对':'Wrong sheet number','找不到这张签课表':'Sheet not found',
'正在识别':'Recognizing','识别出':'Recognized ','识别到':'Found ','待核对':'To check','待确认':'To confirm','已签扫描件':'Signed scans','扫描件':'Scan','确认入账':'Confirm and record','稍后再核对':'Check later','归档这张，不再提醒':'Archive this one, stop reminding','已归档，不再提醒':'Archived','我已逐行核对过学生、签字和请假':'I have checked every row: students, signatures, and leave',
'识别结果：签了字＝上课，勾了框＝请假，空白＝待确认。请对照签字图逐行核对，“待确认”的这次不入账，以后可以再补。':'Result: signed = lesson, ticked = leave, blank = to confirm. Check each row against the image. “To confirm” rows are not recorded; you can add them later.',
'条待确认（可在“待核对”里补）':' to confirm (finish them under “To check”)','已入账':'Recorded','这些签课表都已入账过':'These sheets were already recorded','条已有记录':' already recorded',
'节。以后纸上签了字也不会重复扣；记错了到课时管理的流水里撤销。':' lessons. Signing the paper later will not deduct twice; to fix mistakes, undo in History.',
'纸上签了字、没勾请假，但':'Signed on paper without ticking leave, but ','签字和请假均有笔迹，请核对':'Both signature and leave box have marks, please check','请核对签字':'Please check the signature','请核对请假勾选':'Please check the leave box','未检测到明确笔迹':'No clear mark found',
'这一行没完全对准（纸不平或拍斜了），请看图核对':'This row is not fully aligned (paper not flat or photo tilted). Please check the image',
'已不在名单里，这一行没入账':' is no longer on the list; this row was not recorded','请假，要改请先到课时管理的流水里撤销':'leave; to change it, undo it in History first','（要改到课时管理撤销）':' (undo in Lessons to change)',
'照片里的表格没能对准（纸不平或拍得太斜），请把纸放平、正对着重拍，或用扫描仪':'Could not line up the table in the photo (paper not flat or too tilted). Lay it flat and shoot straight on, or use a scanner',
'这些文件没有识别出来：':'These files could not be recognized: ','这张图打不开':'This image cannot be opened','这张照片浏览器打不开，请换成':'Your browser cannot open this photo. Please convert it to ','（或截图）再导入':' (or take a screenshot) and import again',
'照片：请在手机上把照片存成':'Photos: on your phone, save the photo as ','照片读不出来':'Cannot read the photo','照片转换失败，请改用':'Photo conversion failed, please use ','格式的扫描件':' scans','打不开，请确认文件完整':' cannot be opened; check that the file is complete',
'页空白或背面':' pages blank or back sides','页里没有找到签课表（':' pages had no sign-in sheet (','文件太小或超过':'File too small or larger than ','文件没有传完整，请重试':'The file did not upload completely, please try again','，请降低扫描分辨率（':', please lower the scan resolution (',
'找不到这张图':'Image not found','找不到这张照片':'Photo not found','找不到这张照片，请重新导入':'Photo not found, please import again','找不到签字图片':'Signature image not found','找不到这次识别结果':'Recognition result not found','识别结果不完整，请重新导入':'Incomplete result, please import again',
'找不到这张表（编号':'Sheet not found (No. ','）的版式快照，请确认是本系统打印的表单':') layout. Please make sure the sheet was printed by this app','核对结果无效':'Invalid check result','核对记录无效':'Invalid check record','来源不符':'Source does not match',
'识别程序没加载上，请刷新页面再试':'Recognition did not load, please refresh and try again','读取程序没加载上，请刷新页面再试':'Reader did not load, please refresh and try again','读取失败：':'Read failed: ','读取文件失败':'Could not read the file',
'张签课表':' sheets','签课表，共':' sheet, ','第':'No. ','行':'row','，跳过':', skipped','，还有':', and ','后面还有':' more after this','；另外':'; also ','注意：':'Note: ',
// 纸质课表（老课表）
'纸质课表':'Paper records','纸质课表归档':'Archive paper records','纸质课表都归档好了':'All paper records archived','老课表':'Old paper record','归档':'Archive','待归档':'To archive','不要':'Discard','不要的':'Discarded','已放进“不要的”':'Moved to “Discarded”','下一张':'Next',
'学生名字“':'Student name “','名单里没有「':'Not on the list: “','」，归档时会新建这个学生。':'”; archiving will add this student.','相近的有：':'Similar: ','，是不是打错了？':' — a typo?','最后一次上课':'Last lesson','最后一次上课后':'After the last lesson',
'请填最后一次上课的日期':'Please enter the date of the last lesson','那时剩几节':'Lessons left then','请填那时剩几节课（整数，欠课填负数）':'Please enter lessons left then (whole number; negative if owed)','现在还剩几节课':'Lessons left now',
'看不懂这个日期，可以写成':'Cannot read this date; you can write ','看不懂这个日期':'Cannot read this date','；别的年份写前面：':'; for other years put the year first: ',
'已作为起点：剩':'Set as starting point: ','这张的余课会作为':'This sheet’s remaining lessons become ','在系统里的起点。':'’s starting point in the app.','已手动登记过起始余额，这张只存档。':'A starting balance was entered manually; this sheet is only archived.','已有手动登记的起始余额，这张只存档':'Starting balance already entered manually; this sheet is only archived',
'已有更晚的老课表起点，这张只存档':'A later paper record is already the starting point; this one is only archived','已有更晚的老课表（':'A later paper record (','）作起点，这张只存档。':') is the starting point; this one is only archived.','换成更晚的老课表（':'Switch to the later paper record (','会换掉之前那张较早的老课表，以这张作为起点。':'This replaces the earlier paper record and uses this one as the starting point.',
'注意：系统里已有':'Note: the app already has ','当天或之前的记录，可能已经算在这张的余课里，会重复。':' records on or before that day; they may already be counted in this sheet and be counted twice.','（休假、学校上课、调课等，不算请假）':' (holiday, school, rescheduled — not leave)',
'纸质':'Paper','照片':'Photo','手机上传':'Phone upload',
// 设置向导
'课表用蓝、红两种颜色分老师。只有你一位，就只填蓝色。':'The schedule uses blue and red for two teachers. If it is just you, fill in blue only.','蓝色老师的名字（必填）':'Blue teacher name (required)','红色老师的名字（没有就空着）':'Red teacher name (leave empty if none)','蓝色老师':'Blue teacher','课表默认看':'Schedule shows','新加的课默认给':'New classes go to','填好老师和学生就能开始。资料只存在这台电脑上，以后都能改。':'Fill in teachers and students to start. Your data stays on this computer, and you can change it later.','学生和课表在课程管理、课时管理里改。':'Change students and the schedule in Courses and Lessons.','接入你自己的 AI':'Connect your own AI','在这个文件夹里打开 Claude Code、Codex 这类 AI，把下面这句话发给它，就能用说话的方式记课时。写入前它会先给你看清单。':'Open an AI such as Claude Code or Codex in this folder and send it the sentence below. You can then record lessons by talking to it. It shows you a list before writing anything.','请先读这个文件夹里的 AGENTS.md，然后帮我用课达记课时。':'Please read AGENTS.md in this folder first, then help me record lessons in Coda.','复制这句话':'Copy this sentence','已复制':'Copied','没复制上，请手动选中上面这句':'Could not copy. Please select the sentence above by hand.','设置':'Settings',
'欢迎使用':'Welcome to','先花一分钟填几样东西，就能开始排课、记课时。所有资料都只存在这台电脑上。以后都还能改。':'Take a minute to fill in a few things, then start scheduling and tracking lessons. Everything stays on this computer, and you can change it later.',
'工作室名称':'Studio name','显示在页面右上角，可以不填。':'Shown at the top right. Optional.','比如：小星星音乐工作室':'e.g. Little Star Music Studio','课表里用颜色分老师。只有你一位老师的话，红色那格空着就行。':'Teachers are shown by color. If you are the only teacher, leave the red one empty.',
'蓝色：老师名字（必填）':'Blue: teacher name (required)','红色：第二位老师（可以空着）':'Red: second teacher (optional)','一行一个学生。名字后面空一格，可以写上':'One student per line. After the name, add a space and you can write ','现在还剩几节课（':'how many lessons are left (',
'先留着示例学生和示例课表（想先看看怎么用）':'Keep the sample students and schedule (to try it out first)','完成，开始排课':'Done — start scheduling','改工作室名和老师名字':'Change studio and teacher names','改工作室名和老师名字。学生和课表在课程管理、课时管理里改。':'Change the studio and teacher names. Change students and the schedule in Courses and Lessons.',
'返回，不改了':'Back, no changes','请写蓝色老师的名字':'Please enter the blue teacher’s name','请至少写一位老师的名字':'Please enter at least one teacher','请写至少一个学生，或者勾选“先留着示例学生”':'Please enter at least one student, or keep the sample students','”里不能有顿号、逗号、斜杠，最长':'” cannot contain commas or slashes; at most ','个字':' characters',
'已经设置过了，学生和课表请在课程管理、课时管理里改':'Already set up. Change students and the schedule in Courses and Lessons','只有试用版有设置向导':'Setup is only in the beta','试用版没有这个功能':'Not available in the beta','个写了剩余课时）':' with remaining lessons)','位老师：':' teachers: ','学生名单':'Student list',
'程序没在运行：请回到文件夹，双击“打开':'The app is not running: go back to the folder and double-click “','请不要直接打开这个网页：回到文件夹，双击“打开':'Please don’t open this page directly: go back to the folder and double-click “','”，再在打开的网页里填':'”, then fill it in on the page that opens',
'请通过启动入口打开':'Please open it from the launcher','未知错误':'Unknown error','保存':'Save','取消':'Cancel','关闭':'Close','确定':'OK','名字':'Name','人数':'People','次':'times','起':'from','元':'','无':'None','条':' records','张':' sheets','人':'','节':' lessons','节课':' classes','节）':' lessons)','节：':' lessons: ','节以内':' lessons or fewer','（扣':' (deduct ','人）':')',
'（本周':' (this week','起）':' on)','，不写就是':'; if blank, it is ','；一次连上两节的课选':'; for double classes choose ','通常选':'Usually choose ','剩':'Left ','扣':'Deduct ','与':' and ','或':' or ','也可以按':'You can also press ','行。打印选':' rows. When printing choose ','超过':'more than ','缺少':'missing ','还没有':'None yet','已打开':'Opened','已连接':'Connected','未连接':'Not connected','调整':'Adjust','年月':'year-month','日号':'day','程序':'Program','模板':'Template'
};
var PRE=[[/有\s*(\d+)\s*张签课表待入账，点这里去核对\s*›/g,'$1 sign-in sheet(s) waiting to be booked — review now ›'],[/待补\s*(\d+)\s*节/g,'To make up: $1 lessons'],[/缺记录\s*(\d+)\s*人\s*·\s*(\d+)\s*节/g,'Missing records: $1 students · $2 lessons'],[/缺\s*(\d+)\s*节/g,'missing $1'],[/(\d{4}-\d{2}-\d{2})\s*起/g,'Week of $1'],[/第\s*(\d+)\s*位老师[：:]?\s*/g,'Teacher $1: ']];
var REGEX=[
 [/(\d+(?:\.\d+)?)\s*课时/g,'$1 lessons'],[/(\d+)\s*节课/g,'$1 classes'],[/(\d+)\s*节/g,'$1 lessons'],[/(\d+)\s*名学生/g,'$1 students'],[/(\d+)\s*位/g,'$1 '],[/(\d+)\s*人次/g,'$1 visits'],[/(\d+)\s*人/g,'$1 students'],
 [/(\d+)\s*张/g,'$1 sheets'],[/(\d+)\s*条/g,'$1 records'],[/(\d+)\s*次/g,'$1×'],[/(\d+)\s*行/g,'$1 rows'],[/(\d+)\s*页/g,'$1 pages'],[/(\d+)\s*分钟/g,'$1 min'],[/(\d+)\s*个字/g,'$1 characters'],
 [/扣\s*(\d+)/g,'−$1 '],[/欠\s*(\d+)/g,'owes $1'],[/剩\s*(-?\d+)/g,'left $1'],[/¥\s*(\d)/g,'¥$1'],[/(\d+(?:\.\d+)?)\s*元/g,'¥$1'],[/(\d{4})年(\d{1,2})月(\d{1,2})日/g,'$1-$2-$3'],[/(\d{1,2})月(\d{1,2})日/g,'$1/$2']
];
var PUNCT={'，':', ','。':'. ','：':': ','；':'; ','（':' (','）':')','、':', ','？':'? ','！':'! ','“':'“','”':'”','「':'“','」':'”','　':' ','～':'~','—':'—'};
var CJK=/[一-鿿]/;
// 11-01：旷课、补课、待补
Object.assign(D,{'旷课':'No-show','补课':'Make-up','已记旷课':'No-show recorded','记一次旷课（先扣课时，可补）':'Record a no-show (lesson deducted, can be made up)','记一次补课（加回课时）':'Record a make-up (lesson added back)','记一次请假（先扣课时，可补）':'Record leave (lesson deducted, can be made up)','待补 ':'To make up: ','正在上':'In class','旷课：':'No-show: ','上课了：':'Attended: ','已记旷课，扣 ':'No-show recorded, deducted ','点这里去核对 ›':'Review now ›'});
if(window.CODA_NO_LANG_TOGGLE){D['请假']='Off'}   // 打印的签课表：请假那一栏很窄
var keys=Object.keys(D).filter(function(k){return k.length>1}).sort(function(a,b){return b.length-a.length});
var BIG=new RegExp(keys.map(function(k){return k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}).join('|'),'g');
var cache=new Map();
function T(s){
 if(s==null)return s;s=String(s);
 if(!CJK.test(s)&&!/[，。：；（）、]/.test(s))return s;
 if(cache.has(s))return cache.get(s);
 var t=s,trim=s.trim();
 if(Object.prototype.hasOwnProperty.call(D,trim)&&!(NAMESET&&NAMESET.has(trim)))t=s.replace(trim,D[trim]);
 else{
  var keep=[];
  if(NAMES)t=t.replace(NAMES,function(m){keep.push(m);return ''+(keep.length-1)+''});
  PRE.forEach(function(r){t=t.replace(r[0],r[1])});
  t=t.replace(BIG,function(m){return D[m]});
  REGEX.forEach(function(r){t=t.replace(r[0],r[1])});
  if(Object.prototype.hasOwnProperty.call(D,t.trim()))t=D[t.trim()];
  t=t.replace(/[，。：；（）、？！“”「」　～]/g,function(c){return PUNCT[c]});
  t=t.replace(/(^|[^\d.])([−-]?1) (lesson|student|class|sheet|record|row|page|visit|character)(e?s)\b/g,function(m,a,n,w){return a+n+' '+w});
  if(keep.length)t=t.replace(/(\d+)/g,function(m,i){return keep[+i]});
  t=t.replace(/ {2,}/g,' ').replace(/ ([,.:;)])/g,'$1').replace(/\( /g,'(');
 }
 if(cache.size<5000)cache.set(s,t);
 return t;
}
window.codaT=T;
var NAMES=null,NAMESET=null;
function protect(list){
 var add=false;NAMESET=NAMESET||new Set();
 (list||[]).forEach(function(n){if(typeof n==='string'&&CJK.test(n)&&n.length<=40&&!NAMESET.has(n)){NAMESET.add(n);add=true}});
 if(!add)return;
 NAMES=new RegExp(Array.from(NAMESET).sort(function(a,b){return b.length-a.length}).map(function(k){return k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}).join('|'),'g');cache.clear();
}
window.codaProtect=protect;
var lt=window.LESSON_TEACHERS;if(lt)protect(Object.keys(lt).map(function(k){return lt[k]}));
var F=window.fetch;
window.fetch=function(u,o){   // 新报名、排课时填的新名字也保护起来
 try{if(o&&o.body&&typeof o.body==='string'){var b=JSON.parse(o.body),l=[];['name','student','studio','blue','red'].forEach(function(k){if(typeof b[k]==='string')l.push(b[k].trim())});(b.students||[]).forEach(function(x){if(x&&x.name)l.push(String(x.name).trim())});(b.rows||[]).forEach(function(r){(r.studentNames||[]).forEach(function(n){l.push(n)})});protect(l)}}catch(e){}
 return F.apply(this,arguments);
};
var ATTRS=['placeholder','title','aria-label','alt'];
function skip(el){for(;el;el=el.parentElement){var n=el.nodeName;if(n==='SCRIPT'||n==='STYLE'||n==='TEXTAREA'||(el.hasAttribute&&el.hasAttribute('data-noi18n'))||el.isContentEditable)return true}return false}
function doText(n){if(!n.nodeValue||skip(n.parentElement))return;var v=n.nodeValue,t=T(v);if(t!==v)n.nodeValue=t}
function doEl(el){
 if(el.nodeType!==1||skip(el.parentElement)||el.hasAttribute('data-noi18n'))return;   // 输入框自己的提示文字（placeholder）也要翻，输入的内容不碰
 for(var i=0;i<ATTRS.length;i++){var a=el.getAttribute(ATTRS[i]);if(a){var t=T(a);if(t!==a)el.setAttribute(ATTRS[i],t)}}
 if(el.nodeName==='INPUT'&&/^(button|submit)$/i.test(el.type)&&el.value){var v=T(el.value);if(v!==el.value)el.value=v}
}
function walk(root){
 if(root.nodeType===3){doText(root);return}
 if(root.nodeType!==1&&root.nodeType!==9&&root.nodeType!==11)return;
 if(root.nodeType===1){if(skip(root))return;doEl(root)}
 var w=document.createTreeWalker(root,5,null),n;
 while((n=w.nextNode())){if(n.nodeType===3)doText(n);else doEl(n)}
}
var mo=new MutationObserver(function(list){
 if(!ready)return;
 for(var i=0;i<list.length;i++){var m=list[i];
  if(m.type==='characterData')doText(m.target);
  else if(m.type==='attributes')doEl(m.target);
  else for(var j=0;j<m.addedNodes.length;j++)walk(m.addedNodes[j]);
 }
 if(document.title&&CJK.test(document.title))document.title=T(document.title);
});
mo.observe(document.documentElement,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:ATTRS.concat(['value'])});
var ready=false,hide=document.createElement('style');hide.textContent='html{visibility:hidden}';document.documentElement.appendChild(hide);
function first(){if(!ready)return;walk(document.documentElement);if(CJK.test(document.title))document.title=T(document.title)}
function go(){if(ready)return;ready=true;var lt2=window.LESSON_TEACHERS;if(lt2)protect(Object.keys(lt2).map(function(k){return lt2[k]}));var st=document.querySelector('.modnav .conn [data-noi18n]');if(st)protect([st.textContent]);first();hide.remove()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',first);
F('/schedule',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){protect(j.roster||[]);protect(Object.keys(j.paused||{}))}).catch(function(){}).then(function(){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go()});
setTimeout(go,1500);
var A=window.alert,C=window.confirm,P=window.prompt;
window.alert=function(m){return A.call(window,T(m))};
window.confirm=function(m){return C.call(window,T(m))};
window.prompt=function(m,d){return P.call(window,T(m),d)};
// 课时单是画在 canvas 上的：只翻译标了 data-i18n 的画布（不碰 PDF 识别用的画布）
var CP=CanvasRenderingContext2D.prototype,FT=CP.fillText,MT=CP.measureText;
CP.fillText=function(s){var a=[].slice.call(arguments);if(this.canvas&&this.canvas.dataset&&this.canvas.dataset.i18n)a[0]=T(s);return FT.apply(this,a)};
CP.measureText=function(s){return MT.call(this,this.canvas&&this.canvas.dataset&&this.canvas.dataset.i18n?T(s):s)};
})();
