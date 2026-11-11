/* Print the current renderer at a documented physical size; never claim a requested scale
   if the zoom limit prevented it. Browser print must use 100%, without "fit to page". */
(function(){
  'use strict';
  function capture(api){
    var map=api.map, original=map.getCanvas(), canvas=document.createElement('canvas');
    canvas.width=original.width;canvas.height=original.height;
    var ctx=canvas.getContext('2d'),ratio=original.width/original.clientWidth;
    ctx.drawImage(original,0,0);ctx.font=(12*ratio)+'px system-ui';
    api.draw.features().filter(function(f){return f.properties.name;}).slice(0,150).forEach(function(f){
      var g=f.geometry,p=g.type==='Point'?g.coordinates:g.type==='LineString'?g.coordinates[0]:g.coordinates[0][0];
      var pos=map.project(p),text=f.properties.name.slice(0,200),width=Math.min(ctx.measureText(text).width,220*ratio);
      ctx.fillStyle='#fff';ctx.fillRect(pos.x*ratio-width/2-4*ratio,pos.y*ratio-29*ratio,width+8*ratio,20*ratio);
      ctx.fillStyle='#183153';ctx.fillText(text,pos.x*ratio-width/2,pos.y*ratio-15*ratio,220*ratio);
    });
    return canvas.toDataURL('image/png');
  }
  function ready(map){return new Promise(function(resolve,reject){
    var timeout=setTimeout(function(){map.off('idle',done);reject(new Error('Die Kartenquellen sind noch nicht vollständig geladen. Bitte warten und erneut drucken.'));},12000);
    function done(){clearTimeout(timeout);map.off('idle',done);resolve();}
    map.once('idle',done);map.triggerRepaint();
  });}
  function scaleAtCenter(map,widthMM){var canvas=map.getCanvas(),y=canvas.clientHeight/2;
    var a=map.unproject([0,y]),b=map.unproject([canvas.clientWidth,y]);
    return MapKit.haversine([a.lng,a.lat],[b.lng,b.lat])/(widthMM/1000);
  }
  async function open(api,requested){
    var popup=window.open('','_blank');if(!popup)throw new Error('Bitte das Druckfenster im Browser zulassen.');
    popup.opener=null;popup.document.title='Kartenblatt';popup.document.body.textContent='Kartenblatt wird vorbereitet …';
    var map=api.map,camera={center:map.getCenter(),zoom:map.getZoom(),bearing:map.getBearing(),pitch:map.getPitch()};
    try{
      var canvas=map.getCanvas(),ratio=canvas.clientHeight/canvas.clientWidth,widthMM=Math.min(260,125/ratio);
      map.jumpTo({pitch:0,bearing:0});
      if(requested!=='auto'){var zoom=map.getZoom()+Math.log2(scaleAtCenter(map,widthMM)/Number(requested));map.jumpTo({zoom:Math.max(0,Math.min(22,zoom))});}
      await ready(map);
      if(popup.closed)return;
      var image=capture(api),scale=Math.round(scaleAtCenter(map,widthMM)),esc=MapKit.esc;
      var plan=api.snapshot().plan, title=plan?plan.title:document.title;
      var sources=api.kit.bases.filter(function(l){return l.id===api.kit.baseId;}).concat(api.kit.overlays.filter(function(l){return l.visible;}));
      var rows=api.draw.features().map(function(f,i){return '<tr><td>'+esc(f.properties.name||'Zeichnung '+(i+1))+'</td><td>'+esc(MapDraw.describe(f))+'</td></tr>';}).join('');
      popup.document.open();popup.document.write('<!doctype html><html lang="de"><meta charset="utf-8"><title>Kartenblatt</title><style>@page{size:A4 landscape;margin:12mm}body{font:12px system-ui;color:#172238;margin:0}h1{font-size:20px;margin:0 0 5mm}img{display:block}p{margin:3mm 0}table{border-collapse:collapse;max-width:100%}td{padding:2mm 4mm;border-bottom:1px solid #ddd}tr{break-inside:avoid}.sources{font-size:9px;overflow-wrap:anywhere}.noprint{margin:10px 0}@media print{.noprint{display:none}}</style><body><button class="noprint" type="button" id="print-map">Drucken / als PDF speichern</button><h1 contenteditable="true">'+esc(title)+'</h1><img alt="Karte mit Zeichnungen" style="width:'+widthMM+'mm;height:auto" src="'+image+'"><p>Maßstab an der Kartenmitte ca. 1 : '+scale.toLocaleString('de-DE')+' · '+esc(new Date().toLocaleString('de-DE'))+'</p><p class="sources">Drucken mit 100 % Skalierung, ohne Seitenanpassung. Messungen sind Orientierungshilfen. '+(plan?'Violett: hinterlegter Geltungsbereich. ':'')+'Farben und Beschriftungen entsprechen der Karte; Zeichnungen siehe folgende Liste.</p><div class="sources">'+sources.map(function(l){return '<p><strong>'+esc(l.name)+'</strong>: '+esc((l.attribution||'').replace(/<[^>]*>/g,''))+(l.time?' · Stand '+esc(l.time):'')+'</p>';}).join('')+'</div>'+(rows?'<h2>Zeichnungen und Messwerte</h2><table>'+rows+'</table>':'')+'</body></html>');popup.document.close();
      popup.document.getElementById('print-map').addEventListener('click',function(){popup.print();});
    }catch(error){if(!popup.closed)popup.document.body.textContent='Kartenblatt nicht erstellt: '+error.message;}
    finally{map.jumpTo(camera);}
  }
  window.MapPrint={open:open,capture:capture};
})();
