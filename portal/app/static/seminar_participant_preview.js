(()=>{
  function badge(text,muted=false){
    const span=document.createElement('span');
    span.className=muted?'badge text-bg-light border text-secondary':'badge text-bg-light border';
    span.textContent=text;
    return span;
  }
  async function load(card){
    const status=card.querySelector('[data-participant-preview-status]');
    const list=card.querySelector('[data-participant-preview-list]');
    try{
      const response=await fetch(card.dataset.url,{headers:{Accept:'text/html'}});
      if(!response.ok)throw new Error('Teilnehmerliste nicht verfügbar');
      const doc=new DOMParser().parseFromString(await response.text(),'text/html');
      const names=[];const seen=new Set();
      doc.querySelectorAll('.sem-table tbody tr').forEach(row=>{
        const state=(row.querySelector('td[data-label="Stand"]')?.textContent||'').trim();
        if(!state.startsWith('Angemeldet'))return;
        const name=(row.querySelector('td[data-label="Name"] strong')?.textContent||'').trim();
        if(name&&!seen.has(name)){seen.add(name);names.push(name);}
      });
      status.textContent=names.length===1?'1 Person angemeldet':`${names.length} Personen angemeldet`;
      list.replaceChildren(...names.slice(0,8).map(name=>badge(name)));
      if(names.length>8)list.append(badge(`+${names.length-8} weitere`,true));
      if(!names.length)status.textContent='Noch keine bestätigten Anmeldungen.';
    }catch(_error){
      status.textContent='Schnellansicht derzeit nicht verfügbar.';
      list.replaceChildren();
    }
  }
  document.querySelectorAll('[data-participant-preview]').forEach(load);
})();