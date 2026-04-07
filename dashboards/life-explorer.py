#!/usr/bin/env python3
"""Generate the Life Explorer HTML dashboard from pre-collected data."""
import json

with open("/tmp/explorer_data.json") as f:
    data = json.load(f)

BT = chr(96)  # backtick — avoid Python string escaping issues

# Prepare JS data (keep GPS compact)
js_gps = json.dumps([[round(p["lat"],6), round(p["lon"],6), p["time"][:16]] for p in data["gps"]])
js_places = json.dumps(data["places"])
js_activities = json.dumps(data["activities"][:1000])
js_daily = json.dumps(data["daily"])

html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Life Explorer</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root{{--bg:#0d1117;--sf:#161b22;--bd:#30363d;--tx:#e6edf3;--dm:#8b949e;--ac:#58a6ff;--gn:#3fb950;--pp:#bc8cff;--or:#f0883e;--rd:#f85149}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--tx);font-family:-apple-system,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.top-bar{{display:flex;align-items:center;gap:16px;padding:10px 20px;border-bottom:1px solid var(--bd);flex-shrink:0}}
.top-bar h1{{font-size:16px}}
.top-bar input[type=date]{{background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;font-size:13px}}
.top-bar select{{background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;font-size:13px}}
.top-bar .btn{{background:var(--ac);color:#000;border:none;border-radius:6px;padding:5px 14px;font-size:12px;font-weight:600;cursor:pointer}}
.main{{flex:1;display:flex;overflow:hidden}}
#sidebar{{width:380px;overflow-y:auto;border-right:1px solid var(--bd);display:flex;flex-direction:column}}
#map-wrap{{flex:1;position:relative}}
#map{{width:100%;height:100%}}
.cal-section{{padding:12px 16px}}
.cal-section h3{{font-size:13px;color:var(--ac);margin-bottom:8px}}
#calendar{{display:flex;flex-wrap:wrap;gap:2px}}
.cal-day{{width:14px;height:14px;border-radius:2px;cursor:pointer;position:relative}}
.cal-day:hover{{outline:1px solid var(--tx)}}
.cal-day .tip{{display:none;position:absolute;bottom:18px;left:-30px;background:var(--sf);border:1px solid var(--bd);border-radius:6px;padding:6px 10px;font-size:11px;white-space:nowrap;z-index:100;pointer-events:none}}
.cal-day:hover .tip{{display:block}}
.cal-months{{display:flex;gap:0;margin-bottom:4px;font-size:10px;color:var(--dm)}}
.cal-months span{{width:50px;text-align:center}}
.stats-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;padding:8px 16px}}
.stat-sm{{background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:8px;text-align:center}}
.stat-sm .v{{font-size:18px;font-weight:700}}
.stat-sm .l{{font-size:9px;color:var(--dm);text-transform:uppercase}}
#day-detail{{padding:12px 16px;border-top:1px solid var(--bd)}}
#day-detail h3{{font-size:13px;color:var(--pp);margin-bottom:6px}}
#day-chart{{height:150px}}
.place-mini{{padding:8px 16px;border-top:1px solid var(--bd)}}
.place-mini h3{{font-size:13px;color:var(--ac);margin-bottom:6px}}
#place-list{{list-style:none;max-height:200px;overflow-y:auto}}
#place-list li{{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:11px;cursor:pointer;border-bottom:1px solid var(--bd)}}
#place-list li:hover{{color:var(--ac)}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.leaflet-container{{background:var(--bg)!important}}
::-webkit-scrollbar{{width:5px}}
::-webkit-scrollbar-thumb{{background:var(--bd);border-radius:3px}}
</style>
</head>
<body>
<div class="top-bar">
  <h1>Life Explorer</h1>
  <input type="date" id="date-from" value="2025-07-01">
  <span style="color:var(--dm)">~</span>
  <input type="date" id="date-to" value="2026-04-07">
  <select id="cal-metric">
    <option value="steps">걸음수</option>
    <option value="sleep_h">수면시간</option>
    <option value="stress">스트레스</option>
    <option value="dist_km">이동거리</option>
    <option value="visits">방문수</option>
  </select>
  <button class="btn" onclick="applyFilter()">적용</button>
  <button class="btn" style="background:var(--gn)" onclick="showToday()">오늘</button>
</div>
<div class="main">
<div id="sidebar">
  <div class="stats-row" id="period-stats"></div>
  <div class="cal-section">
    <h3>Life Calendar</h3>
    <div id="calendar"></div>
  </div>
  <div id="day-detail">
    <h3 id="day-title">날짜를 선택하세요</h3>
    <div id="day-chart"></div>
    <div id="day-info" style="font-size:12px;margin-top:6px"></div>
  </div>
  <div class="place-mini">
    <h3>자주 방문</h3>
    <ul id="place-list"></ul>
  </div>
</div>
<div id="map-wrap"><div id="map"></div></div>
</div>

<script>
const GPS = {js_gps};
const PLACES = {js_places};
const ACTS = {js_activities};
const DAILY = {js_daily};

const map = L.map("map").setView([37.45,126.89],12);
L.tileLayer("https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png",{{maxZoom:19}}).addTo(map);

let trailLayer=null, heatLayer=null, actLayer=null, markerLayer=null;
const tColors = {{INFERRED_HOME:"#bc8cff",INFERRED_WORK:"#58a6ff",UNKNOWN:"#3fb950"}};
const aColors = {{WALKING:"#3fb950",IN_VEHICLE:"#f0883e",CYCLING:"#d29922",RUNNING:"#f85149",IN_RAIL_VEHICLE:"#58a6ff"}};

function updateMap(from, to) {{
  if(trailLayer) map.removeLayer(trailLayer);
  if(heatLayer) map.removeLayer(heatLayer);
  if(actLayer) map.removeLayer(actLayer);
  if(markerLayer) map.removeLayer(markerLayer);

  const pts = GPS.filter(p => p[2] >= from && p[2] <= to);
  if(!pts.length) return;

  const ll = pts.map(p=>[p[0],p[1]]);
  trailLayer = L.polyline(ll,{{color:"#58a6ff",weight:2,opacity:0.5}}).addTo(map);
  heatLayer = L.heatLayer(ll.map(p=>[p[0],p[1],0.4]),{{radius:12,blur:18,maxZoom:14}}).addTo(map);
  map.fitBounds(trailLayer.getBounds().pad(0.1));

  // Activity segments
  actLayer = L.layerGroup();
  ACTS.filter(a=>a.time>=from && a.time<=to).forEach(a => {{
    if(!a.slat) return;
    const c = aColors[a.type]||"#8b949e";
    L.polyline([[a.slat,a.slon],[a.elat,a.elon]],{{color:c,weight:3,opacity:0.7}}).addTo(actLayer)
      .bindPopup(a.type+"<br>"+Math.round(a.dur)+"분 · "+Math.round(a.dist)+"m");
  }});
  actLayer.addTo(map);

  // Markers
  markerLayer = L.layerGroup();
  PLACES.forEach(p => {{
    const c = tColors[p.type]||"#3fb950";
    const sz = Math.min(18, 8+p.visits/10);
    const icon = L.divIcon({{className:"",
      html:"<div style='width:"+sz+"px;height:"+sz+"px;background:"+c+";border-radius:50%;border:2px solid #fff;box-shadow:0 0 6px "+c+"'></div>",
      iconSize:[sz,sz],iconAnchor:[sz/2,sz/2]}});
    L.marker([p.lat,p.lon],{{icon}}).addTo(markerLayer)
      .bindPopup("<b>#"+p.rank+" "+p.name+"</b><br>"+p.visits+"회 방문<br>평균 "+Math.round(p.avg_min)+"분");
  }});
  markerLayer.addTo(map);
}}

// Calendar
function renderCalendar(metric) {{
  const cal = document.getElementById("calendar");
  const days = Object.keys(DAILY).sort();
  if(!days.length) return;

  const vals = days.map(d => DAILY[d][metric]||0);
  const maxVal = Math.max(...vals.filter(v=>v>0)) || 1;

  const colorScale = {{
    steps: v => {{const r=v/maxVal; return r>0.7?"#3fb950":r>0.4?"#2ea043":r>0.1?"#1a7f37":"#0d1117"}},
    sleep_h: v => {{const r=v/maxVal; return r>0.7?"#bc8cff":r>0.4?"#8b5cf6":r>0.1?"#6d28d9":"#0d1117"}},
    stress: v => {{const r=v/maxVal; return r>0.7?"#f85149":r>0.4?"#f0883e":r>0.1?"#d29922":"#0d1117"}},
    dist_km: v => {{const r=v/maxVal; return r>0.7?"#58a6ff":r>0.4?"#388bfd":r>0.1?"#1f6feb":"#0d1117"}},
    visits: v => {{const r=v/maxVal; return r>0.7?"#f0883e":r>0.4?"#db6d28":r>0.1?"#9e6a03":"#0d1117"}},
  }};
  const getColor = colorScale[metric] || colorScale.steps;

  let html = "";
  days.forEach((d,i) => {{
    const v = DAILY[d][metric]||0;
    const c = v > 0 ? getColor(v) : "#161b22";
    const label = d.slice(5)+" | "+metric+": "+v;
    html += "<div class='cal-day' style='background:"+c+"' onclick='selectDay(\""+d+"\")'><div class='tip'>"+label+"</div></div>";
  }});
  cal.innerHTML = html;
}}

function selectDay(dateStr) {{
  document.getElementById("day-title").textContent = dateStr;
  const d = DAILY[dateStr] || {{}};
  document.getElementById("day-info").innerHTML =
    "걸음: <b>"+((d.steps||0).toLocaleString())+"</b> · "+
    "수면: <b>"+(d.sleep_h||0)+"h</b> · "+
    "스트레스: <b>"+(d.stress||0)+"</b> · "+
    "이동: <b>"+(d.dist_km||0)+"km</b> · "+
    "방문: <b>"+(d.visits||0)+"</b>";

  // Show that day on map
  updateMap(dateStr+"T00:00", dateStr+"T23:59");

  // Day chart
  const metrics = ["steps","sleep_h","stress","dist_km","visits"];
  const vals = metrics.map(m => d[m]||0);
  const maxes = metrics.map(m => {{
    const all = Object.values(DAILY).map(v=>v[m]||0);
    return Math.max(...all)||1;
  }});
  const pcts = vals.map((v,i) => Math.round(v/maxes[i]*100));
  Plotly.newPlot("day-chart",[{{
    type:"bar", x:pcts, y:["걸음","수면","스트레스","이동","방문"], orientation:"h",
    marker:{{color:["#3fb950","#bc8cff","#f85149","#58a6ff","#f0883e"]}},
    text:vals.map((v,i)=>i===0?v.toLocaleString():v), textposition:"inside",
    textfont:{{color:"#fff",size:11}}
  }}],{{
    paper_bgcolor:"transparent",plot_bgcolor:"transparent",font:{{color:"#e6edf3",size:10}},
    margin:{{t:0,r:10,b:5,l:55}},xaxis:{{visible:false,range:[0,100]}},
    yaxis:{{gridcolor:"#30363d"}}
  }},{{responsive:true,displayModeBar:false}});
}}

function updateStats(from, to) {{
  const days = Object.keys(DAILY).filter(d => d >= from && d <= to).sort();
  if(!days.length) {{ document.getElementById("period-stats").innerHTML=""; return; }}
  const sum = (m) => days.reduce((s,d) => s+(DAILY[d][m]||0), 0);
  const avg = (m) => days.length ? Math.round(sum(m)/days.length*10)/10 : 0;
  const el = document.getElementById("period-stats");
  el.innerHTML =
    "<div class='stat-sm'><div class='v' style='color:var(--gn)'>"+avg("steps").toLocaleString()+"</div><div class='l'>평균 걸음/일</div></div>"+
    "<div class='stat-sm'><div class='v' style='color:var(--pp)'>"+avg("sleep_h")+"</div><div class='l'>평균 수면h</div></div>"+
    "<div class='stat-sm'><div class='v' style='color:var(--rd)'>"+avg("stress")+"</div><div class='l'>평균 스트레스</div></div>";
}}

function applyFilter() {{
  const from = document.getElementById("date-from").value;
  const to = document.getElementById("date-to").value;
  updateMap(from+"T00:00", to+"T23:59");
  updateStats(from, to);
}}

function showToday() {{
  const today = new Date().toISOString().slice(0,10);
  document.getElementById("date-from").value = today;
  document.getElementById("date-to").value = today;
  selectDay(today);
  updateStats(today, today);
}}

// Place list
const pl = document.getElementById("place-list");
PLACES.forEach(p => {{
  const c = tColors[p.type]||"#3fb950";
  const li = document.createElement("li");
  li.innerHTML = "<span class='dot' style='background:"+c+"'></span><span style='flex:1'>"+p.name+"</span><span style='color:var(--gn)'>"+p.visits+"</span>";
  li.onclick = () => map.setView([p.lat,p.lon],15);
  pl.appendChild(li);
}});

// Init
renderCalendar("steps");
document.getElementById("cal-metric").onchange = e => renderCalendar(e.target.value);
applyFilter();
</script>
</body>
</html>'''

out = "/mnt/c/Users/upica/Downloads/home-iot-life-explorer.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK: {out} ({len(html)//1024}KB)")
