/* Keep all three inputs visible. Start changes preserve duration. */
(()=>{document.querySelectorAll('[data-time-mode]').forEach(mode=>{
 const form=mode.closest('form'),start=form.querySelector('[data-time-start]'),end=form.querySelector('[data-time-end]'),duration=form.querySelector('[data-time-duration]');
 const local=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
 function sync(source){
   const s=new Date(start.value);
   if(source==='end'){
     const e=new Date(end.value),minutes=(e-s)/60000;
     duration.value=Number.isFinite(minutes)?minutes:'';
   }else if(start.value&&duration.value&&Number.isFinite(s.getTime())){
     end.value=local(new Date(s.getTime()+Number(duration.value)*60000));
   }else{end.value='';}
   mode.value='end';end.required=true;
 }
 for(const event of ['input','change']){
   start.addEventListener(event,()=>sync('start'));
   duration.addEventListener(event,()=>sync('duration'));
   end.addEventListener(event,()=>sync('end'));
 }
 sync('duration');
});})();
