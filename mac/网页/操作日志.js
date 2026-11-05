// 操作日志的小框（10-22）：少见的改动（请假、改课、补记录、撤销、合并/删除/暂停学生）存好以后，右下角问一句“原因（可不写）”。
// 不挡操作：不写就不管它，10 秒后自己收起；在框里打字时不收。服务器回的 X-Coda-Ask 决定问不问，X-Coda-Log 是这条日志的编号。
(function(){
 if(window.__codaLog)return;window.__codaLog=true;
 const KEY=window.CODA_LOG_KEY||window.CODA_KEY||'';
 const raw=window.fetch.bind(window);
 window.fetch=async function(input,init){
  const res=await raw(input,init);
  try{if(res.ok&&res.headers.get('X-Coda-Ask')==='1')ask(res.headers.get('X-Coda-Log'),KEY)}catch(e){}
  return res;
 };
 let box,timer;
 function ask(id,token){
  if(!id)return;
  if(!box){
   box=document.createElement('div');
   box.style.cssText='position:fixed;right:18px;bottom:18px;z-index:99999;background:#fff;border:1px solid #d9dee7;border-radius:12px;padding:10px 12px;box-shadow:0 6px 20px rgba(30,40,60,.12);font:14px -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#223047;display:flex;gap:8px;align-items:center;max-width:min(460px,calc(100vw - 36px))';
   box.innerHTML='<span style="white-space:nowrap;color:#68788d">原因（可不写）</span><input style="flex:1;min-width:120px;font:inherit;padding:6px 8px;border:1px solid #d9dee7;border-radius:8px" placeholder="比如：发烧、琴行停电"><button type="button" style="font:inherit;padding:6px 12px;border-radius:8px;border:1px solid #275de0;background:#275de0;color:#fff">记下</button><button type="button" aria-label="不写" style="font:inherit;padding:6px 9px;border-radius:8px;border:1px solid #d9dee7;background:#fff;color:#68788d">×</button>';
   const [input,save,close]=[box.querySelector('input'),...box.querySelectorAll('button')];
   input.addEventListener('focus',()=>clearTimeout(timer));
   input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();save.click()}if(e.key==='Escape')hide()});
   close.onclick=hide;
   save.onclick=async()=>{
    const reason=input.value.trim();if(!reason){hide();return}
    try{const r=await raw('/api/log/reason',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':box.dataset.token},body:JSON.stringify({id:box.dataset.id,reason})});if(!r.ok)throw 0;input.value='';hide()}
    catch(e){input.style.borderColor='#d64545';input.placeholder='没存上，再点一次'}
   };
  }
  const open=[...document.querySelectorAll('dialog[open]')].pop();(open||document.body).appendChild(box);   // 开着弹窗时页面别处点不了，小框要放进弹窗里
  box.dataset.id=id;box.dataset.token=token;box.style.display='flex';
  const input=box.querySelector('input');input.value='';input.style.borderColor='#d9dee7';
  clearTimeout(timer);timer=setTimeout(()=>{if(document.activeElement!==input)hide()},10000);
 }
 function hide(){clearTimeout(timer);if(box)box.style.display='none'}
})();
