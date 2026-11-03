/* Board state stays on the server. Touch, mouse and forms share one checked API. */
(() => {
  'use strict';
  const root=document.getElementById('kanban');if(!root)return;
  const message=document.getElementById('kb-message'),feedback=document.getElementById('kb-feedback');
  const drawer=document.getElementById('kb-detail'),body=document.getElementById('kb-detail-body');
  let refreshSequence=0;let activeCard=null,busy=false,drag=null,focusId=null,undo=null;
  const drafts=new Map();let openSequence=0;
  const draftKey=form=>form.elements.card?.value+":"+form.elements.action?.value;
  root.addEventListener('input',e=>{
    const form=e.target.closest('#kb-detail form');if(!form)return;
    drafts.set(draftKey(form),[...form.elements].filter(f=>f.name==='version'||f.id&&f.type!=='submit').map(f=>({id:f.id,name:f.name,value:f.value,checked:f.checked,type:f.type})));
  });
  const endpoint=`/tasks/boards/${root.dataset.board}/action`;
  const key=`kanban-${root.dataset.board}`;
  const error=text=>{message.textContent=text;message.hidden=!text;};
  function layout(value){
    if(!['board','focus','list'].includes(value))value='board';
    const area=document.getElementById('kb-columns');area.dataset.layout=value;
    if(!focusId)focusId=area.querySelector('[data-column]')?.dataset.column;
    area.querySelectorAll('[data-column]').forEach(c=>c.classList.toggle('kb-focused',c.dataset.column===focusId));
    root.querySelectorAll('[data-kb-layout]').forEach(b=>{const active=b.dataset.kbLayout===value;b.setAttribute('aria-pressed',String(active));b.classList.toggle('active',active);});
    try{localStorage.setItem(key+'-layout',value);}catch{}
  }
  async function openCard(id,show=true){
    const sequence=++openSequence;
    const response=await fetch(`/tasks/boards/${root.dataset.board}/cards/${id}`,{credentials:'same-origin',headers:{'Accept':'text/html'}});
    if(!response.ok||response.redirected)throw Error('Die Aufgabe ist nicht mehr zugänglich. Bitte das Board aktualisieren.');
    const html=await response.text();if(sequence!==openSequence)return;
    body.innerHTML=html;activeCard=id;
    if(window.PortalDatePicker?.enhance)window.PortalDatePicker.enhance(body);
    for(const form of body.querySelectorAll('form')){
      const draft=drafts.get(draftKey(form));if(!draft)continue;
      for(const state of draft){const field=state.id?form.querySelector('#'+CSS.escape(state.id)):form.elements.namedItem(state.name);if(!field||state.type==='file')continue;field.value=state.value;if(state.type==='checkbox')field.checked=state.checked;}
    }
    if(show)bootstrap.Offcanvas.getOrCreateInstance(drawer).show();
  }
  async function refresh(){
    const sequence=++refreshSequence;
    const area=document.getElementById('kb-columns'),scroll=area.scrollLeft;
    const vertical=Object.fromEntries([...area.querySelectorAll('[data-column]')].map(c=>[c.dataset.column,c.querySelector('.kb-card-list').scrollTop]));
    const openChecks=[...area.querySelectorAll('details[open]')].map(d=>({card:d.closest('[data-card]')?.dataset.card,index:[...d.closest('[data-card]')?.querySelectorAll('details')||[]].indexOf(d)}));
    const response=await fetch(location.href,{credentials:'same-origin'});
    if(!response.ok||response.redirected)throw Error('Board nicht mehr zugänglich. Bitte Seite neu laden.');
    const doc=new DOMParser().parseFromString(await response.text(),'text/html'),next=doc.getElementById('kanban');
    if(sequence!==refreshSequence)return;
    if(!next)throw Error('Board konnte nicht aktualisiert werden.');
    const overview=root.querySelector('.kb-overview');if(overview)overview.innerHTML=next.querySelector('.kb-overview').innerHTML;root.dataset.version=next.dataset.version;root.dataset.level=next.dataset.level;
    area.innerHTML=doc.getElementById('kb-columns').innerHTML;
    root.querySelectorAll('input[name=board_version]').forEach(i=>i.value=root.dataset.version);
    area.scrollLeft=scroll;
    area.querySelectorAll('[data-column]').forEach(c=>{c.querySelector('.kb-card-list').scrollTop=vertical[c.dataset.column]||0;});
    for(const d of openChecks){const card=area.querySelector(`[data-card="${d.card}"]`);const detail=card?.querySelectorAll('details')[d.index];if(detail)detail.open=true;}
    layout(area.dataset.layout);grips();
    if(activeCard&&drawer.classList.contains('show'))await openCard(activeCard,false);
  }
  async function save(data,form){
    if(busy)return;busy=true;++refreshSequence;error('');root.setAttribute('aria-busy','true');
    data.set('csrf',document.querySelector('meta[name=csrf]').content);data.set('board_version',root.dataset.version);
    const submit=form?.querySelector('button[type=submit],button:not([type])');if(submit)submit.disabled=true;
    try{
      const response=await fetch(endpoint,{method:'POST',credentials:'same-origin',headers:{'Accept':'application/json'},body:data});
      let result;try{result=await response.json();}catch{throw Error('Sitzung abgelaufen oder Antwort ungültig. Bitte die Seite neu laden.');}
      if(!response.ok)throw Error(result.detail||'Änderung nicht gespeichert.');
      if(result.redirect){location.assign(result.redirect);return;}
      if(form?.closest('#board-settings')){try{sessionStorage.setItem(key+'-settings','1');}catch{}location.reload();return;}
      if(form?.closest('#kb-detail'))drafts.delete(draftKey(form));
      if(data.get('action')==='create')form?.reset();if(data.get('action')==='attach'){form?.reset();if(library)bootstrap.Offcanvas.getOrCreateInstance(library).hide();}
      await refresh();if(data.get('action')==='move'&&data.get('undo')!=='1'){const previous=data.get('previous');if(previous){undo=JSON.parse(previous);root.querySelector('[data-kb-undo]').hidden=false;}}feedback.textContent='Gespeichert.';
    }catch(e){error(e.message);if(form?.closest('.offcanvas')){let note=form.querySelector('[data-kb-error]');if(!note){note=document.createElement('p');note.dataset.kbError='';note.className='alert alert-danger mt-2';note.setAttribute('role','alert');form.append(note);}note.textContent=e.message;}}
    finally{busy=false;root.removeAttribute('aria-busy');if(submit)submit.disabled=false;}
  }
  root.addEventListener('submit',event=>{const form=event.target.closest('.kb-action');if(!form)return;event.preventDefault();if(form.dataset.confirm&&!confirm(form.dataset.confirm))return;save(new FormData(form),form);});
  root.addEventListener('change',event=>{if(event.target.matches('[data-kb-autosave]'))event.target.form.requestSubmit();});
  root.addEventListener('click',event=>{
    const filterToggle=event.target.closest('[data-kb-filters]');if(filterToggle){const open=root.classList.toggle('kb-filters-open');filterToggle.setAttribute('aria-expanded',String(open));return;}
    if(event.target.closest('[data-kb-undo]')&&undo){const data=new FormData();for(const [k,v]of Object.entries(undo))data.set(k,v);data.set('undo','1');data.set('action','move');const card=root.querySelector(`[data-card="${undo.card}"]`);data.set('version',card?.dataset.taskVersion||'');save(data);undo=null;root.querySelector('[data-kb-undo]').hidden=true;return;}
    const open=event.target.closest('[data-kb-open]');if(open){openCard(open.dataset.kbOpen).catch(e=>error(e.message));return;}
    const mode=event.target.closest('[data-kb-layout]');if(mode){layout(mode.dataset.kbLayout);return;}
    const focus=event.target.closest('[data-kb-focus]');if(focus){focusId=focus.dataset.kbFocus;const area=document.getElementById('kb-columns');if(area.dataset.layout==='focus')layout('focus');else area.querySelector(`[data-column="${focusId}"]`)?.scrollIntoView({block:'nearest',inline:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
    if(event.target.closest('[data-kb-refresh]'))refresh().then(()=>error('')).catch(e=>error(e.message));
  });
  drawer.addEventListener('hidden.bs.offcanvas',()=>{activeCard=null;});
  function grips(){root.querySelectorAll('.kb-card[draggable=true]').forEach(card=>{if(card.querySelector('.kb-grip'))return;const b=document.createElement('button');b.type='button';b.className='kb-grip';b.dataset.kbGrip='';b.setAttribute('aria-label','Karte ziehen; alternativ Verschieben unter weitere Aktionen');b.innerHTML='<i class="fa-solid fa-grip-vertical" aria-hidden="true"></i>';card.prepend(b);});}
  function targetAt(x,y){const el=document.elementFromPoint(x,y),zone=el?.closest('[data-drop-column]');if(!zone)return null;const cards=[...zone.querySelectorAll('[data-card]')].filter(c=>c.dataset.card!==drag?.id);const index=cards.findIndex(c=>y<c.getBoundingClientRect().top+c.getBoundingClientRect().height/2);return {column:zone.dataset.dropColumn,position:index<0?cards.length:index,zone};}
  function moveTo(target){if(!drag||!target)return;const data=new FormData();data.set('action','move');data.set('card',drag.id);data.set('column',target.column);data.set('position',target.position);const card=root.querySelector(`[data-card="${drag.id}"]`);data.set('version',card?.dataset.taskVersion||'');if(card)data.set('previous',JSON.stringify({card:drag.id,column:card.closest('[data-column]').dataset.column,position:[...card.parentElement.children].filter(c=>c.matches('[data-card]')).indexOf(card)}));save(data);}
  root.addEventListener('dragstart',e=>{const card=e.target.closest('[data-card][draggable=true]');if(!card||e.target.closest('input,select,textarea,a,summary')||busy){e.preventDefault();return;}drag={id:card.dataset.card};card.classList.add('kb-dragging');e.dataTransfer.setData('text/plain',drag.id);e.dataTransfer.effectAllowed='move';});
  root.addEventListener('dragover',e=>{if(drag&&e.target.closest('[data-drop-column]'))e.preventDefault();});
  root.addEventListener('drop',e=>{if(!drag)return;e.preventDefault();moveTo(targetAt(e.clientX,e.clientY));});
  root.addEventListener('dragend',()=>{root.querySelectorAll('.kb-dragging').forEach(c=>c.classList.remove('kb-dragging'));drag=null;});
  let touch=null;
  root.addEventListener('pointerdown',e=>{if(e.pointerType==='mouse'||busy||!e.target.closest('[data-kb-grip]'))return;const card=e.target.closest('[data-card]');e.preventDefault();const grip=e.target.closest('[data-kb-grip]');grip.setPointerCapture(e.pointerId);drag={id:card.dataset.card};const rect=card.getBoundingClientRect(),ghost=card.cloneNode(true);ghost.setAttribute('aria-hidden','true');ghost.querySelectorAll('[id]').forEach(el=>el.removeAttribute('id'));ghost.classList.add('kb-drag-ghost');ghost.style.width=rect.width+'px';document.body.append(ghost);touch={ghost,grip,pointer:e.pointerId,offset:e.clientY-rect.top};card.classList.add('kb-dragging');positionTouch(e);});
  function positionTouch(e){if(!touch)return;touch.ghost.style.left=(e.clientX-30)+'px';touch.ghost.style.top=(e.clientY-touch.offset)+'px';root.querySelectorAll('.kb-drop-target').forEach(z=>z.classList.remove('kb-drop-target'));const target=targetAt(e.clientX,e.clientY);target?.zone.classList.add('kb-drop-target');const area=document.getElementById('kb-columns'),rect=area.getBoundingClientRect();if(e.clientX>rect.right-40)area.scrollLeft+=24;else if(e.clientX<rect.left+40)area.scrollLeft-=24;if(target){const box=target.zone.getBoundingClientRect();if(e.clientY>box.bottom-40)target.zone.scrollTop+=20;else if(e.clientY<box.top+40)target.zone.scrollTop-=20;}}
  root.addEventListener('pointermove',e=>{if(touch&&e.pointerId===touch.pointer){e.preventDefault();positionTouch(e);}});
  function finishTouch(e,cancel=false){if(!touch)return;if(!cancel)moveTo(targetAt(e.clientX,e.clientY));touch.ghost.remove();root.querySelectorAll('.kb-dragging,.kb-drop-target').forEach(c=>c.classList.remove('kb-dragging','kb-drop-target'));touch=null;drag=null;}
  root.addEventListener('pointerup',e=>finishTouch(e));root.addEventListener('pointercancel',e=>finishTouch(e,true));
  let saved='board';try{saved=localStorage.getItem(key+'-layout')||'board';if(sessionStorage.getItem(key+'-settings')){sessionStorage.removeItem(key+'-settings');bootstrap.Offcanvas.getOrCreateInstance(document.getElementById('board-settings')).show();}}catch{}
  const library=root.querySelector('#kb-library');
  function renderLibrary(){
    if(!library)return;
    let results=library.querySelector('.kb-library-results');
    if(!results){results=document.createElement('div');results.className='kb-library-results list-group mb-3';results.setAttribute('aria-label','Vorhandene Inhalte');library.querySelector('[data-kb-library-search]').after(results);}
    results.replaceChildren();
    for(const select of library.querySelectorAll('[data-kb-library]')){
      select.hidden=true;library.querySelector(`label[for="${select.id}"]`).hidden=true;
      for(const option of select.options){if(!option.value)continue;
        const button=document.createElement('button');button.type='button';button.className='list-group-item list-group-item-action';
        const kind=document.createElement('span');kind.className='kb-card-type';kind.textContent=select.id==='attach-task'?'Aufgabe':option.textContent.split(' · ')[0];
        const title=document.createElement('strong');title.textContent=select.id==='attach-task'?option.textContent:option.textContent.split(' · ').slice(1).join(' · ');
        button.append(kind,title);button.setAttribute('aria-pressed',String(option.selected));button.classList.toggle('active',option.selected);
        button.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));results.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});});
        results.append(button);
      }
    }
    if(!results.children.length){const empty=document.createElement('p');empty.className='small text-secondary p-3';empty.textContent='Keine zugänglichen Inhalte. Legen Sie zunächst eine Aufgabe oder Umfrage an.';results.append(empty);}
  }
  library?.addEventListener('show.bs.offcanvas',()=>{renderLibrary();library.querySelector('[data-kb-library-search]').value='';const empty=library.querySelector('[data-kb-no-results]');if(empty)empty.hidden=true;});
  library?.addEventListener('input',event=>{
    if(!event.target.matches('[data-kb-library-search]'))return;
    const query=event.target.value.trim().toLocaleLowerCase();
    library.querySelectorAll('[data-kb-library]').forEach(select=>select.value='');
    let matches=0;library.querySelectorAll('.kb-library-results button').forEach(button=>{button.hidden=!button.textContent.toLocaleLowerCase().includes(query);button.classList.remove('active');button.setAttribute('aria-pressed','false');if(!button.hidden)matches++;});
    let empty=library.querySelector('[data-kb-no-results]');if(!empty){empty=document.createElement('p');empty.dataset.kbNoResults='';empty.className='small text-secondary';empty.setAttribute('role','status');empty.textContent='Keine passenden Inhalte. Versuchen Sie einen anderen Suchbegriff.';library.querySelector('.kb-library-results').after(empty);}empty.hidden=matches>0;
    library.querySelectorAll('[data-kb-library] option').forEach(option=>{option.hidden=!!option.value&&!option.textContent.toLocaleLowerCase().includes(query);});
  });
  library?.addEventListener('change',event=>{
    if(event.target.id==='attach-task'&&event.target.value)library.querySelector('#attach-source').value='';
    if(event.target.id==='attach-source'&&event.target.value)library.querySelector('#attach-task').value='';
  });
  const liveRefresh=()=>{if(document.hidden||busy||drag||activeCard||document.activeElement?.closest('form')||root.querySelector('.offcanvas.show'))return;refresh().catch(()=>{});};
  const timer=setInterval(liveRefresh,30000);window.addEventListener('focus',liveRefresh);window.addEventListener('pagehide',()=>clearInterval(timer));
  layout(saved);grips();
})();
