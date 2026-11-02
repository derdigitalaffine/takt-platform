(() => {
'use strict';
const root=document.getElementById('seminar-planner');
const source=document.getElementById('sp-data');
if(!root||!source)return;
const config=JSON.parse(source.textContent),initial=config.initial||{},terms=initial.terms||[];
const errorBox=document.getElementById('sp-error'),statusBox=document.getElementById('sp-status');
const error=message=>{if(!errorBox)return;errorBox.textContent=message;errorBox.hidden=!message;if(message)errorBox.scrollIntoView({block:'nearest',behavior:'smooth'});};
const announce=message=>{if(statusBox)statusBox.textContent=message;};
const button=(label,classes,handler)=>{const node=document.createElement('button');node.type='button';node.className=classes;node.textContent=label;node.addEventListener('click',handler);return node;};
async function action(term,name,extra={}){
  error('');
  const response=await fetch(`${window.location.pathname.replace(/\/planen$/,'')}/terms/${term.id}/action`,{
    method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},credentials:'same-origin',
    body:JSON.stringify({csrf:config.csrf,row_revision:initial.revision,term_revision:term.revision,action:name,...extra})
  });
  let result={};try{result=await response.json();}catch(_){/* handled below */}
  if(!response.ok)throw new Error(result.detail||'Terminaktion konnte nicht ausgeführt werden.');
  announce('Termin aktualisiert.');
  window.location.assign(result.redirect||window.location.pathname);
}
function run(term,name,question,extra={}){
  if(question&&!window.confirm(question))return;
  action(term,name,extra).catch(err=>error(err.message));
}
function deleteQuestion(term){
  const notify=initial.status==='published'&&term.published&&!term.cancelled?' Betroffene Personen erhalten vorher eine Kalender-Stornierung.':'';
  return `Diesen Termin endgültig löschen? Der Termin verschwindet vollständig aus der Reihe; terminbezogene Buchungen und Daten werden entfernt.${notify} Diese Aktion kann nicht rückgängig gemacht werden. Ungespeicherte Änderungen auf dieser Seite gehen verloren.`;
}
function cancelPanel(card,term){
  const old=card.querySelector('[data-sp-cancel-panel]');if(old){old.remove();return;}
  const panel=document.createElement('div');panel.dataset.spCancelPanel='1';panel.className='border rounded p-3 mt-2';
  const label=document.createElement('label');label.className='form-label';label.textContent='Absagegrund';
  const input=document.createElement('input');input.className='form-control form-control-sm';input.maxLength=500;input.placeholder='Zum Beispiel: Dozent verhindert';
  const actions=document.createElement('div');actions.className='d-flex gap-2 flex-wrap mt-2';
  actions.append(button('Termin absagen','btn btn-sm btn-danger',()=>{
    const reason=input.value.trim();if(!reason){input.setCustomValidity('Bitte einen Absagegrund angeben.');input.reportValidity();return;}
    input.setCustomValidity('');
    if(!window.confirm('Diesen Termin absagen und betroffene Personen informieren?'))return;
    action(term,'cancel',{reason}).catch(err=>error(err.message));
  }),button('Abbrechen','btn btn-sm btn-outline-secondary',()=>panel.remove()));
  panel.append(label,input,actions);card.append(panel);input.focus();
}
function focusMove(card){
  const details=card.querySelector('details');if(details)details.open=true;
  const start=card.querySelector('input[type="datetime-local"]');if(start){start.focus();start.scrollIntoView({block:'center',behavior:'smooth'});}
  announce('Beginn oder Ende ändern und anschließend „Änderungen speichern“ wählen. Betroffene Personen erhalten dann eine aktualisierte Kalenderdatei.');
}
function enhance(){
  const cards=[...root.querySelectorAll('#sp-terms .sp-term')];
  cards.forEach((card,index)=>{
    const term=terms[index];if(!term?.id||card.dataset.spActions==='1')return;
    card.dataset.spActions='1';
    const bar=document.createElement('div');bar.className='d-flex gap-2 flex-wrap align-items-center mt-2';
    const label=document.createElement('span');label.className='small text-secondary me-auto';
    if(term.cancelled){
      label.textContent='Abgesagt'+(term.reason?`: ${term.reason}`:'');bar.append(label);
      bar.append(button('Reaktivieren','btn btn-sm btn-outline-success',()=>run(term,'reactivate','Diesen abgesagten Termin wieder aktivieren? Betroffene Personen erhalten eine aktualisierte Kalenderdatei. Ungespeicherte Änderungen auf dieser Seite gehen verloren.')));
      bar.append(button('Termin löschen','btn btn-sm btn-outline-danger',()=>run(term,'delete',deleteQuestion(term))));
      card.append(bar);return;
    }
    if(initial.status==='published'&&term.published){
      label.textContent='Veröffentlichter Termin';bar.append(label);
      bar.append(button('Verschieben','btn btn-sm btn-outline-primary',()=>focusMove(card)));
      bar.append(button('Veröffentlichung zurücknehmen','btn btn-sm btn-outline-secondary',()=>run(term,'unpublish','Termin aus der veröffentlichten Reihe zurücknehmen? Das ist nur möglich, solange keine Einladungen oder Anmeldungen bestehen. Ungespeicherte Änderungen auf dieser Seite gehen verloren.')));
      bar.append(button('Absagen','btn btn-sm btn-outline-danger',()=>cancelPanel(card,term)));
      bar.append(button('Termin löschen','btn btn-sm btn-danger',()=>run(term,'delete',deleteQuestion(term))));
    }else{
      label.textContent=term.ever_published?'Unveröffentlicht':'Entwurf';bar.append(label);
      if(initial.status==='published')bar.append(button('Veröffentlichen','btn btn-sm btn-outline-success',()=>run(term,'publish','Diesen Termin jetzt veröffentlichen? Ungespeicherte Änderungen auf dieser Seite gehen verloren.')));
      bar.append(button('Termin löschen','btn btn-sm btn-outline-danger',()=>run(term,'delete',deleteQuestion(term))));
    }
    card.append(bar);
  });
}
const observer=new MutationObserver(()=>enhance());observer.observe(document.getElementById('sp-terms'),{childList:true});enhance();
})();
