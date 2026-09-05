#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
efterkontroll.py - bygger en sida dar varje kapad artefakt visas i 3D
FORE och EFTER omkorningen, sida vid sida, med beslutsknappar.

Forberedelse (en gang):
  git archive --format=zip HEAD~1 -o C:\\soldata\\fore.zip   (committen FORE omkorningen)
  Expand-Archive C:\\soldata\\fore.zip C:\\soldata\\fore
  I ett PowerShell-fonster:  cd C:\\soldata\\fore ;  py -m http.server 8001
  I ett annat:               cd <repot>          ;  py -m http.server 8002

Bygg sidan (fran repotroten):
  py verktyg\\efterkontroll.py --artefakter verktyg\\artefakter.json
Oppna: http://localhost:8002/efterkontroll.html

Beslut sparas i webblasaren, knappen Exportera ger efterkontroll.json.
"""
import argparse, json, math

# ---- SWEREF99 TM <-> WGS84 (samma som linjedetektor) ----------------
_a = 6378137.0; _f = 1 / 298.257222101
_e2 = _f * (2 - _f); _n = _f / (2 - _f)
_ah = _a / (1 + _n) * (1 + _n * _n / 4 + _n ** 4 / 64)
_k0 = 0.9996; _FE = 500000.0; _lon0 = math.radians(15.0)

def till_sweref(lat, lon):
    A = _e2; B = (5*_e2**2 - _e2**3)/6
    C = (104*_e2**3 - 45*_e2**4)/120; D = 1237*_e2**4/1260
    b1 = _n/2 - 2*_n**2/3 + 5*_n**3/16 + 41*_n**4/180
    b2 = 13*_n**2/48 - 3*_n**3/5 + 557*_n**4/1440
    b3 = 61*_n**3/240 - 103*_n**4/140
    b4 = 49561*_n**4/161280
    phi = math.radians(lat); si = math.sin(phi)
    ps = phi - si*math.cos(phi)*(A + B*si*si + C*si**4 + D*si**6)
    dl = math.radians(lon) - _lon0
    xi = math.atan2(math.tan(ps), math.cos(dl))
    eta = math.atanh(math.cos(ps) * math.sin(dl))
    N = xi; E = eta
    for j, bj in enumerate((b1, b2, b3, b4), 1):
        N += bj * math.sin(2*j*xi) * math.cosh(2*j*eta)
        E += bj * math.cos(2*j*xi) * math.sinh(2*j*eta)
    return _k0*_ah*E + _FE, _k0*_ah*N

def till_wgs84(E, N):
    lat, lon = 59.3, 18.0
    for _ in range(12):
        E2, N2 = till_sweref(lat, lon)
        lat += (N - N2) / 111320.0
        lon += (E - E2) / (111320.0 * math.cos(math.radians(lat)))
    return lat, lon

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--artefakter', default='verktyg/artefakter.json')
    ap.add_argument('--fore', default='http://localhost:8001/')
    ap.add_argument('--efter', default='http://localhost:8002/')
    ap.add_argument('--ut', default='efterkontroll.html')
    a = ap.parse_args()
    d = json.load(open(a.artefakter, encoding='utf-8'))
    poster = []
    for i, x in enumerate(d.get('artefakter', [])):
        la, lo = till_wgs84(float(x['E']), float(x['N']))
        poster.append(dict(i=i, namn=x.get('namn', '?'), E=int(x['E']), N=int(x['N']),
                           r=x.get('r'), minh=x.get('minh'),
                           notering=x.get('notering', ''),
                           lat=round(la, 6), lon=round(lo, 6)))
    html = (MALL.replace('__DATA__', json.dumps(poster, ensure_ascii=False))
                .replace('__FORE__', a.fore).replace('__EFTER__', a.efter))
    open(a.ut, 'w', encoding='utf-8').write(html)
    print(f'{len(poster)} artefakter -> {a.ut}')

MALL = """<!DOCTYPE html><html lang="sv"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Efterkontroll: fore / efter</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--ram:#d8d3c8;--bg:#f6f4ef;--ink:#2a2a26}
html,body{height:100%;margin:0;font:14px/1.4 system-ui,sans-serif;color:var(--ink);background:var(--bg)}
header{display:flex;gap:14px;align-items:center;padding:7px 12px;border-bottom:1px solid var(--ram);background:#fff}
header b{font-size:15px} #stat{color:#666}
button{font:inherit;padding:5px 12px;border:1px solid var(--ram);border-radius:7px;background:#fff;cursor:pointer}
#layout{display:grid;height:calc(100% - 46px);grid-template-columns:300px 1fr 1fr;
  grid-template-rows:3fr 2fr;gap:6px;padding:6px;box-sizing:border-box}
#lista{grid-row:1/3;overflow-y:auto;background:#fff;border:1px solid var(--ram);border-radius:8px}
.rad{padding:7px 10px;border-bottom:1px solid #eee;cursor:pointer;display:flex;gap:8px;align-items:baseline}
.rad:hover{background:#f4f1ea} .rad.vald{background:#ece7db} .rad.klar{opacity:.45}
.rad .nr{color:#999;font-variant-numeric:tabular-nums;min-width:2.2em}
.rad .namn{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rad .flagga{margin-left:auto}
.panel{position:relative;background:#fff;border:1px solid var(--ram);border-radius:8px;overflow:hidden;min-height:0}
.panel .titel{position:absolute;top:6px;left:8px;z-index:800;background:rgba(255,255,255,.92);
  padding:2px 9px;border-radius:6px;font-size:12px;font-weight:700}
.fore .titel{color:#a52a1d} .efter .titel{color:#2c6238}
#map{height:100%} iframe{width:100%;height:100%;border:0}
#pbeslut{padding:12px;overflow-y:auto}
#info{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;background:#f6f4ef;border-radius:7px;padding:9px;margin:8px 0}
#komm{width:100%;box-sizing:border-box;font:inherit;padding:7px;border:1px solid var(--ram);border-radius:7px;min-height:48px}
.knappar{display:flex;gap:8px;margin-top:10px}
.knappar button{flex:1;padding:10px 6px;font-weight:600;border-width:2px}
#bOk{border-color:#3f8a4f;color:#2c6238} #bNej{border-color:#d43a2a;color:#a52a1d} #bVanta{border-color:#e08a12;color:#a5650a}
.genv{color:#888;font-size:12px;margin-top:8px}
</style></head><body>
<header><b>Efterkontroll</b><span id="stat"></span><span style="flex:1"></span>
<button id="bExport">Exportera beslut</button></header>
<div id="layout">
  <aside id="lista"></aside>
  <div class="panel fore" style="grid-column:2;grid-row:1"><div class="titel">FORE (port 8001)</div><iframe id="ifFore"></iframe></div>
  <div class="panel efter" style="grid-column:3;grid-row:1"><div class="titel">EFTER (port 8002)</div><iframe id="ifEfter"></iframe></div>
  <div class="panel" style="grid-column:2;grid-row:2"><div class="titel">Karta</div><div id="map"></div></div>
  <div class="panel" id="pbeslut" style="grid-column:3;grid-row:2">
    <b id="rubrik">Valj en artefakt</b>
    <div id="info"></div>
    <textarea id="komm" placeholder="Kommentar"></textarea>
    <div class="knappar">
      <button id="bOk">&#10003; OK nu</button>
      <button id="bNej">&#10007; Inte OK</button>
      <button id="bVanta">&#9208; Avvakta</button>
    </div>
    <div class="genv">1 OK &middot; 2 inte OK &middot; 3 avvakta &middot; n nasta oavgjorda &middot; Bada vyerna: dra = snurra, hjul = zooma</div>
  </div>
</div>
<script>
"use strict";
const POSTER=__DATA__;
const FORE='__FORE__', EFTER='__EFTER__', IFV=Date.now();
let beslut={};
try{beslut=JSON.parse(localStorage.getItem('efterkontroll_v1')||'{}');}catch(_){}
function spara(){try{localStorage.setItem('efterkontroll_v1',JSON.stringify(beslut));}catch(e){alert(e);}}
let vald=null;
const map=L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(map);
const mark={};
function farg(p){const b=beslut[p.i];return !b?'#d43a2a':b.beslut==='ok'?'#3f8a4f':b.beslut==='nej'?'#a52a1d':'#e08a12';}
function ritaMark(){
  for(const p of POSTER){
    if(mark[p.i])map.removeLayer(mark[p.i]);
    const v=vald&&vald.i===p.i;
    mark[p.i]=L.circleMarker([p.lat,p.lon],{radius:v?10:6,weight:v?4:2,color:farg(p),fillOpacity:beslut[p.i]?.15:.5})
      .on('click',()=>valj(p)).addTo(map);
  }
}
function badge(p){const b=beslut[p.i];return !b?'':{ok:'&#10003;',nej:'&#10007;',avvakta:'&#9208;'}[b.beslut];}
function ritaLista(){
  const el=document.getElementById('lista');el.innerHTML='';
  for(const p of POSTER){
    const b=beslut[p.i];
    const d=document.createElement('div');
    d.className='rad'+(vald&&vald.i===p.i?' vald':'')+(b&&b.beslut!=='avvakta'?' klar':'');
    d.innerHTML='<span class="nr">'+(p.i+1)+'</span><span class="namn">'+p.namn+'</span><span class="flagga">'+badge(p)+'</span>';
    d.onclick=()=>valj(p);el.appendChild(d);
  }
  const n={ok:0,nej:0,avvakta:0};for(const k in beslut)n[beslut[k].beslut]++;
  document.getElementById('stat').textContent=POSTER.length+' artefakter  ·  '+n.ok+' OK  ·  '+n.nej+' inte OK  ·  '+n.avvakta+' avvakta';
}
function valj(p){
  vald=p;map.setView([p.lat,p.lon],17);
  const h='?g='+IFV+'#3d='+p.E+','+p.N+','+p.lat+','+p.lon;
  document.getElementById('ifFore').src=FORE+h;
  document.getElementById('ifEfter').src=EFTER+h;
  document.getElementById('rubrik').textContent=(p.i+1)+'. '+p.namn;
  document.getElementById('info').textContent='E '+p.E+'  N '+p.N+'  r '+p.r+' m  minh '+p.minh+' m\\n'+(p.notering||'');
  document.getElementById('komm').value=beslut[p.i]?beslut[p.i].kommentar||'':'';
  ritaMark();ritaLista();
}
function narmsta(){
  let bast=null,bd=1e18;
  for(const p of POSTER){if(beslut[p.i]||p===vald)continue;
    const d=(p.E-vald.E)**2+(p.N-vald.N)**2;if(d<bd){bd=d;bast=p;}}
  return bast;
}
function bestam(typ){
  if(!vald)return;
  beslut[vald.i]={beslut:typ,kommentar:document.getElementById('komm').value.trim(),tid:new Date().toISOString(),
    namn:vald.namn,E:vald.E,N:vald.N,r:vald.r,minh:vald.minh};
  spara();const n=narmsta();if(n)valj(n);else{ritaMark();ritaLista();document.getElementById('rubrik').textContent='Alla avgjorda.';}
}
document.getElementById('bOk').onclick=()=>bestam('ok');
document.getElementById('bNej').onclick=()=>bestam('nej');
document.getElementById('bVanta').onclick=()=>bestam('avvakta');
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;
  if(e.key==='1')bestam('ok');else if(e.key==='2')bestam('nej');else if(e.key==='3')bestam('avvakta');
  else if(e.key==='n'&&vald){const x=narmsta();if(x)valj(x);}
});
document.getElementById('bExport').onclick=()=>{
  const ut={exporterad:new Date().toISOString(),ok:[],inte_ok:[],avvakta:[]};
  for(const k in beslut){const b=beslut[k];(b.beslut==='ok'?ut.ok:b.beslut==='nej'?ut.inte_ok:ut.avvakta).push(b);}
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify(ut,null,1)],{type:'application/json'}));
  a.download='efterkontroll.json';a.click();
};
ritaMark();ritaLista();
const start=POSTER.find(p=>!beslut[p.i]);
if(start)valj(start);else map.setView([59.31,18.06],12);
</script></body></html>"""

if __name__ == '__main__':
    main()
