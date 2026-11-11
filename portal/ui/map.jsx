import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal} from 'react-dom';
import {MantineProvider, createTheme, Stack, Group, Button, Text, Paper, Badge, SimpleGrid,
  TextInput, NumberInput, NativeSelect, Switch, Divider, Alert, ActionIcon} from '@mantine/core';
import './map.css';

const host=document.getElementById('map-workbench-nav');
const actions=document.getElementById('map-workbench-actions');
const theme=createTheme({fontFamily:getComputedStyle(document.body).fontFamily,primaryColor:'blue',defaultRadius:'md',
  fontSizes:{sm:'.8125rem',md:'.875rem'},components:{Button:{defaultProps:{size:'sm'}},TextInput:{defaultProps:{size:'sm'}},NativeSelect:{defaultProps:{size:'sm'}}}});
const tools=[['line','Strecke','route'],['polygon','Fläche','draw-polygon'],['rectangle','Rechteck','vector-square'],['circle','Kreis / Radius','circle'],['point','Punkt','location-dot'],['text','Text','font']];
const icon=name=><i className={`fa-solid fa-${name}`} aria-hidden="true"/>;
function App(){
  const [api,setApi]=useState(window.MapWorkspace),[state,setState]=useState(null);
  const [view,setView]=useState(JSON.parse(document.getElementById('map-bundle').textContent).plan?'plan':'layers'),[scheme,setScheme]=useState(document.documentElement.dataset.bsTheme||'light');
  const [snap,setSnap]=useState(false),[scale,setScale]=useState('auto'),[radius,setRadius]=useState(100),[error,setError]=useState('');
  useEffect(()=>{
    const update=()=>{if(window.MapWorkspace){setApi(window.MapWorkspace);setState(window.MapWorkspace.snapshot());}};
    update();window.addEventListener('map-workbench-ready',update);window.addEventListener('map-workbench-change',update);
    const observer=new MutationObserver(()=>setScheme(document.documentElement.dataset.bsTheme||'light'));
    observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-bs-theme']});
    return()=>{observer.disconnect();window.removeEventListener('map-workbench-ready',update);window.removeEventListener('map-workbench-change',update);};
  },[]);
  useEffect(()=>{
    document.getElementById('map-shell').classList.toggle('plan-open',view==='plan');
    document.getElementById('map-layer-pane').hidden=view!=='layers';
    document.getElementById('map-parcel-pane').hidden=view!=='parcels';
    api?.map.resize();
    const detail=document.querySelector('#parcel-browser .parcel-search');if(detail)detail.open=view==='parcels';
    if(view!=='tools'&&api?.draw.mode())api.draw.cancel();
  },[view,api]);
  const act=fn=>{setError('');try{Promise.resolve(fn()).catch(e=>setError(e.message));setState(api.snapshot());}catch(e){setError(e.message||'Die Aktion ist gerade nicht möglich.');}};
  if(!state)return <p className="small text-secondary" role="status">Kartenwerkzeuge werden geladen …</p>;
  const selected=state.features.find(f=>f.id===state.selected);
  const plan=state.plan;
  return <MantineProvider theme={theme} forceColorScheme={scheme} cssVariablesSelector="#map-workbench" withGlobalClasses={false}>
    <Stack gap="sm" className="map-workspace">
      {state.dirty&&<Badge variant="light" color="orange">Ungespeichert</Badge>}
      <nav className="map-workspace-nav" aria-label="Kartenbereiche">
        {[['layers','Ebenen','layer-group'],['tools','Messen & Zeichnen','ruler-combined'],['parcels','Flurstücke','vector-square'],...(plan?[['plan','Plan & Recht','scale-balanced']]:[])].map(([key,label,i])=><Button key={key} variant={view===key?'light':'subtle'} leftSection={icon(i)} aria-pressed={view===key} onClick={()=>setView(key)}>{label}</Button>)}
      </nav>
      {error&&<Alert color="red" role="alert">{error}</Alert>}
      {plan&&view!=='plan'&&<Paper withBorder p="xs"><Text size="xs" c="dimmed">Planbezug</Text><Button variant="subtle" className="map-plan-shortcut" onClick={()=>setView('plan')}>{plan.title}</Button></Paper>}
      {view==='tools'&&<>
        <Text size="sm" c="dimmed">Werkzeug wählen und Punkte in der Karte setzen. Die Messwerte erscheinen direkt beim Zeichnen.</Text>
        <SimpleGrid cols={2} spacing="xs">{tools.map(([key,label,i])=><Button key={key} variant={state.sketch?.mode===key?'filled':'light'} leftSection={icon(i)} disabled={state.features.length>=500} onClick={()=>act(()=>api.start(key))}>{label}</Button>)}</SimpleGrid>
        {state.sketch&&<Paper withBorder p="sm"><Text size="sm" role="status">{state.sketch.text||'Punkt in der Karte setzen'}</Text><Group gap="xs" mt="xs"><Button disabled={state.sketch.count<state.sketch.min} onClick={()=>act(()=>api.draw.finish())}>Fertig</Button><Button variant="subtle" onClick={()=>act(()=>api.draw.cancel())}>Abbrechen</Button></Group></Paper>}
        <Switch label="An Punkten und Grenzen einrasten" description="Zeichnungen, gesammelte Flurstücke und Geltungsbereich" checked={snap} onChange={e=>{setSnap(e.currentTarget.checked);api.draw.setSnapping(e.currentTarget.checked);}}/>
        <Group gap="xs"><Button variant="default" leftSection={icon('rotate-left')} disabled={!state.canUndo} onClick={()=>act(()=>api.draw.undo())}>Rückgängig</Button><Button variant="default" disabled={!state.canRedo} onClick={()=>act(()=>api.draw.redo())}>Wiederholen</Button></Group>
        <Divider label={`${state.features.length} Zeichnungen`}/>
        {state.features.length===0&&<Text size="sm" c="dimmed">Noch keine Zeichnungen. Ein Klick auf eine fertige Zeichnung wählt sie aus. Bei Flächen und Linien können Sie anschließend die Stützpunkte verschieben.</Text>}
        <div className="map-object-list">{state.features.map((f,index)=><Paper key={f.id} withBorder p="sm" className={selected?.id===f.id?'map-object-selected':''}>
          <Group justify="space-between" wrap="nowrap"><Button variant="subtle" className="map-object-name" onClick={()=>act(()=>{api.draw.select(f.id);api.draw.zoomTo(f.id);})}>{f.properties.name||`${tools.find(t=>t[0]===(f.properties.shape||f.properties.kind))?.[1]||'Zeichnung'} ${index+1}`}</Button><ActionIcon variant="subtle" aria-label={`Zeichnung ${index+1} löschen`} color="red" onClick={()=>act(()=>api.draw.remove(f.id))}>{icon('trash-can')}</ActionIcon></Group>
          <Text size="xs" c="dimmed">{window.MapDraw.describe(f)}</Text>
        </Paper>)}</div>
        {selected&&<Paper withBorder p="sm"><Stack gap="xs"><Text fw={650} size="sm">Ausgewählte Zeichnung</Text>
          <TextInput label="Bezeichnung auf der Karte" maxLength={200} value={selected.properties.name||''} onChange={e=>act(()=>api.draw.update(selected.id,{name:e.currentTarget.value}))}/>
          <label className="map-color-label">Farbe<input type="color" aria-label="Zeichenfarbe" value={selected.properties.color||'#d62828'} onChange={e=>act(()=>api.draw.update(selected.id,{color:e.currentTarget.value}))}/></label>
          <Button variant="light" disabled={state.features.length>=500} onClick={()=>act(()=>api.draw.duplicate(selected.id))}>Zeichnung kopieren</Button>
          {selected.geometry.type==='Point'&&<Group align="end" grow><NumberInput label="Umkreis in Metern" min={1} max={1000000} value={radius} onChange={setRadius}/><Button variant="default" disabled={state.features.length>=500||!(Number(radius)>=1&&Number(radius)<=1000000)} onClick={()=>act(()=>api.draw.bufferPoint(selected.id,Number(radius)))}>Umkreis zeichnen</Button></Group>}
        </Stack></Paper>}
        <Group gap="xs"><Button variant="default" disabled={!state.features.length} onClick={()=>act(()=>api.download())}>GeoJSON exportieren</Button><Button variant="subtle" onClick={()=>api.click('draw-import')}>GeoJSON importieren</Button></Group>
        {!state.canSave&&<Text size="xs" c="dimmed">Sie arbeiten lokal in diesem Browser. Zum dauerhaften Speichern bitte anmelden oder die Zeichnungen herunterladen.</Text>}
      </>}
      {view==='plan'&&plan&&<Stack gap="sm"><Text fw={700}>{plan.title}</Text>{plan.version&&<Text size="sm">{plan.version}</Text>}<Text size="sm" c="dimmed">{plan.valid_from?`Gültig ab ${plan.valid_from}`:''}{plan.valid_until?` · bis ${plan.valid_until}`:''}</Text>
        <Button component="a" href={plan.url} leftSection={icon('scale-balanced')}>Rechtstext öffnen</Button>
        {plan.pdf&&<><Button component="a" href={plan.pdf} target="_blank" rel="noopener" variant="light">PDF-Plan öffnen</Button><iframe className="map-plan-pdf" src={plan.pdf} title={plan.pdf_label||'PDF-Plan'}/></>}
        {plan.geometry&&<Text size="xs" c="dimmed">Der violette Umriss zeigt den hinterlegten Geltungsbereich. Die PDF wird als Dokument angezeigt.</Text>}
      </Stack>}
    </Stack>
    {createPortal(<Stack gap="xs" className="map-workspace map-output-actions">
      <Divider/>
      <Group grow>{state.canSave&&<Button leftSection={icon('floppy-disk')} onClick={()=>api.click('open-save-map')}>Karte speichern</Button>}<Button variant="default" onClick={()=>api.click('btn-link')}>Ausschnitt teilen</Button></Group>
      {state.canSave&&<Button component="a" href="/maps" variant="subtle" size="xs">Meine Karten</Button>}
      <NativeSelect label="Druckmaßstab" value={scale} onChange={e=>setScale(e.currentTarget.value)} data={[{value:'auto',label:'Aktueller Ausschnitt'},...['500','1000','2500','5000','10000','25000'].map(v=>({value:v,label:`1 : ${Number(v).toLocaleString('de-DE')}`}))]}/>
      <Group grow><Button variant="light" leftSection={icon('print')} onClick={()=>act(()=>window.MapPrint.open(api,scale))}>Drucken / PDF</Button><Button variant="subtle" onClick={()=>api.click('btn-export')}>PNG</Button></Group>
    </Stack>,actions)}
  </MantineProvider>;
}
if(host)createRoot(host).render(<App/>);
