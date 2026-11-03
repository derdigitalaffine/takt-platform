/* Explicit end times stay authoritative; the server validates the final range. */
(()=>{document.querySelectorAll('[data-time-mode]').forEach(mode=>{
 const form=mode.closest('form'),start=form.querySelector('[data-time-start]'),end=form.querySelector('[data-time-end]'),duration=form.querySelector('[data-time-duration]');
 const local=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
 function sync(){const explicit=mode.value==='end';end.required=explicit;end.disabled=!explicit;duration.disabled=explicit;form.querySelector('[data-time-end-wrap]').hidden=!explicit;duration.closest('div').hidden=explicit;
 if(!explicit||!end.value){const d=new Date(start.value);if(!Number.isNaN(d.getTime())){d.setMinutes(d.getMinutes()+Number(duration.value));end.value=local(d);}}
 end.min=start.value;}
 mode.addEventListener('change',sync);start.addEventListener('change',sync);duration.addEventListener('change',sync);sync();
});})();
