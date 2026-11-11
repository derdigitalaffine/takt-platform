/* Real geodesic math with a lightweight renderer: edit history must preserve full geometry. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const events={},sources={},layers={};
const map={isStyleLoaded:()=>true,addSource:(id,s)=>sources[id]={...s,setData(data){this.data=data;}},getSource:id=>sources[id],
 addLayer:l=>layers[l.id]=l,getLayer:id=>layers[id],on:(name,fn)=>(events[name]??=[]).push(fn),
 getCanvas:()=>({style:{}}),doubleClickZoom:{enable(){},disable(){}},dragPan:{enable(){},disable(){}},
 project:p=>({x:p[0]*10000,y:p[1]*10000}),unproject:p=>({toArray:()=>p.map(v=>v/10000)}),queryRenderedFeatures:()=>[],getZoom:()=>12};
const context={console,Math,Date,setTimeout,document:{addEventListener(){},createElement:()=>({})},
 maplibregl:{Marker:class{setLngLat(){return this;}addTo(){return this;}remove(){}}}};
context.window=context;vm.createContext(context);
for(const file of ['map-core.js','map-draw.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static',file),'utf8'),context);
const draw=context.MapDraw.create(map);
draw.start('circle');draw.addPoint([7,49]);draw.addPoint([7.01,49]);
let circle=draw.features()[0];assert.equal(circle.properties.shape,'circle');assert.equal(circle.geometry.coordinates[0].length,97);
assert.ok(circle.properties.radius_m>720&&circle.properties.radius_m<740);
assert.ok(context.MapDraw.measure(circle).area>1600000);
draw.update(circle.id,{name:'Zone'});draw.duplicate(circle.id);assert.equal(draw.features().length,2);
draw.undo();assert.equal(draw.features().length,1);draw.redo();assert.equal(draw.features().length,2);
draw.remove(circle.id);assert.equal(draw.features().length,1);draw.undo();assert.equal(draw.features().length,2);
draw.start('rectangle');draw.addPoint([7,49]);draw.addPoint([7.01,49.01]);
assert.equal(draw.features()[2].geometry.coordinates[0].length,5);
draw.start('text');draw.addPoint([7.1,49]);assert.equal(draw.features()[3].properties.name,'Beschriftung');
draw.resetHistory();assert.equal(draw.canUndo(),false);
draw.start('polygon');draw.addPoint([7,49]);draw.addPoint([7.01,49]);draw.undo();draw.cancel();assert.equal(draw.features().length,4);
assert.equal(context.MapDraw.validFeature({geometry:{type:'Point',coordinates:[Infinity,49]}}),false);
assert.equal(context.MapDraw.validFeature({geometry:{type:'Polygon',coordinates:[[[0,0],[1,0],[1,1]]]}}),false);
assert.equal(context.MapDraw.validFeature(circle),true);
draw.start('line');draw.addPoint([8,50]);draw.addPoint([8.01,50]);draw.finish();
draw.setSnapping(true);draw.start('point');
events.click[0]({lngLat:{lng:8.005,lat:50.0004},point:{x:80050,y:500004}});
const point=draw.features().at(-1);
assert.equal(point.geometry.coordinates[1],50);
assert.ok(draw.bufferPoint(point.id,125));
assert.equal(draw.features().at(-1).properties.radius_m,125);
assert.equal(draw.bufferPoint(point.id,-1),null);
console.log('MapDraw: circle/rectangle/text, geodesic measurements, history and import validation passed.');
