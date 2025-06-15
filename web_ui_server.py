from flask import Flask, render_template_string, jsonify, request, url_for
import json, os, requests, time, sys

# ------------------------------ CONFIG ----------------------------------
from config_dialog import read_config, write_config
config = read_config() or {}
role   = config.get("role", "FLIGHT")

ROLES = ['FLIGHT','CAPCOM','FAO','BME','CPOO','SCIENCE','EVA']

# Build HTML option tags for roles once
options = "".join(f"<option value='{r}'>{r}</option>" for r in ROLES)

# Load loops for the selected role
def load_loops(r):
    path = os.path.join('LOOPS', f'loops_{r.upper()}.txt')
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print('Loop load error', e)
        return []

LOOPS = load_loops(role)

# ------------------------------ BOT POOL ---------------------------------
BOTS = [
    {"name": "BOT1", "port": 6001},
    {"name": "BOT2", "port": 6002},
    {"name": "BOT3", "port": 6003},
]

bot_pool   = {b['name']: {**b, 'assigned': None, 'last_used': 0} for b in BOTS}
loop_states = {l['name']: (0, None) for l in LOOPS}

def refresh_state_from_role():
    global LOOPS, loop_states
    LOOPS = load_loops(role)
    loop_states = {l['name']: (0, None) for l in LOOPS}

def find_idle_bot():
    idle = [n for n, d in bot_pool.items() if d['assigned'] is None]
    if not idle:
        return None
    idle.sort(key=lambda n: bot_pool[n]['last_used'])
    return idle[0]

# ------------------------------ FLASK APP --------------------------------
app = Flask(__name__)

# ------------------------------ TEMPLATES --------------------------------
MAIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MCC Voice Loops</title>
<style>
 :root{--bg:#1e1e1e;--panel:#2b2b2b;--txt:#ddd;--listen:#325c8d;--talk:#3c6d2d;--danger:#b41b1b}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--txt);font-family:sans-serif}
 #controls{display:flex;align-items:center;padding:10px;background:var(--panel)}
 select,button{margin-right:10px;padding:6px 10px;background:#3a3a3a;border:none;border-radius:4px;color:var(--txt)}
 select:hover,button:hover{background:#4a4a4a;cursor:pointer}
 #wave{width:150px;height:40px;margin-left:auto;border:1px solid #444;border-radius:4px}
 #grid{display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:220px;gap:18px;padding:18px}
 .card{position:relative;background:var(--panel);border-radius:12px;box-shadow:0 0 6px #000a;overflow:hidden}
 .listen{background:var(--listen)} .talk{background:var(--talk)}
 .priv{position:absolute;top:8px;left:10px;font-size:1rem}
 .cnt{position:absolute;top:8px;right:10px;font-size:.9rem}
 .name{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;font-weight:600;padding:0 4px}
 .vol{position:absolute;bottom:10px;left:10px;width:55%}
 .off{position:absolute;bottom:6px;right:10px;padding:4px 10px;background:var(--danger);border:none;border-radius:4px;color:#fff;font-weight:600}
 #logo{position:fixed;bottom:10px;right:10px;height:60px;opacity:.6}
</style></head>
<body>
  <div id="controls">
    <label>Input:<select id="inDev"></select></label>
    <label>Output:<select id="outDev"></select></label>
    <button id="delay">Delay</button>
    <canvas id="wave"></canvas>
  </div>
  <div id="grid"></div>
  <img id="logo" src="{{ url_for('static', filename='logo2.png') }}" alt="logo">
<script>
 const LOOPS = {{ loops|tojson }};
 const BOTS  = {{ bots|tojson }};
 const primary = BOTS[0].port;
 let delay=false;
 // ------------- build grid -------------
 function grid(){const g=document.getElementById('grid');g.innerHTML='';LOOPS.forEach((l,i)=>{const c=document.createElement('div');c.dataset.loop=l.name;c.className='card';c.innerHTML=`<span class='priv'>${l.can_listen?'👂':''}${l.can_talk?'🗣️':''}</span><span class='cnt'>👥0</span><div class='name'>${l.name}</div><input type='range' min='0' max='1' step='0.01' value='0.5' class='vol'><button class='off'>OFF</button>`;c.onclick=e=>{if(e.target===c)act('toggle',l.name)};c.querySelector('.off').onclick=e=>{e.stopPropagation();act('off',l.name)};c.querySelector('.vol').oninput=e=>{e.stopPropagation();fetch(`http://127.0.0.1:${BOTS[i% BOTS.length].port}/set_volume`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volume:e.target.value})})};g.append(c);})}
 // ------------- device list -------------
 async function devices(){try{const d=await navigator.mediaDevices.enumerateDevices();const iSel=inDev,oSel=outDev;d.filter(x=>x.kind==='audioinput').forEach((d,i)=>iSel.add(new Option(d.label||`Mic ${i}`,d.deviceId)));d.filter(x=>x.kind==='audiooutput').forEach((d,i)=>oSel.add(new Option(d.label||`Spkr ${i}`,d.deviceId)));iSel.onchange=()=>chg('in',iSel.value);oSel.onchange=()=>chg('out',oSel.value);}catch(e){}}
 function chg(t,id){fetch(`http://127.0.0.1:${primary}/device_${t}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:id})})}
 // ------------- waveform -------------
 async function wave(){try{const s=await navigator.mediaDevices.getUserMedia({audio:true});const ctx=new(window.AudioContext||window.webkitAudioContext)();const src=ctx.createMediaStreamSource(s);const an=ctx.createAnalyser();an.fftSize=256;src.connect(an);const d=new Uint8Array(an.fftSize);const c=document.getElementById('wave').getContext('2d');(function draw(){requestAnimationFrame(draw);an.getByteTimeDomainData(d);c.clearRect(0,0,150,40);c.beginPath();d.forEach((v,i)=>{const x=i*150/d.length,y=(v/128)*20;i?c.lineTo(x,y):c.moveTo(x,y)});c.strokeStyle='#4a4a4a';c.stroke();})();}catch(e){}}
 // ------------- actions -------------
 async function act(a,l){await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a,loop:l})});refresh()}
 const dBtn=document.getElementById('delay');
 dBtn.onclick = async () => {
     delay = !delay;
     dBtn.style.background = delay ? '#43d843' : '#c22c2c';
     await fetch('/api/command', {
         method:'POST',
         headers:{'Content-Type':'application/json'},
         body:JSON.stringify({action:'delay', enabled: delay})
     });
 };
 // ------------- poll -------------
 async function refresh(){const r=await (await fetch('/api/status')).json();LOOPS.forEach(l=>{const c=document.querySelector(`[data-loop="${l.name}"]`);if(!c)return;c.querySelector('.cnt').textContent=`👥${r.user_counts[l.name]||0}`;c.classList.remove('listen','talk');if(r.states[l.name]==1)c.classList.add('listen');if(r.states[l.name]==2)c.classList.add('talk')})}
 // ------------- init -------------
 devices();wave();grid();refresh();setInterval(refresh,1000);
</script></body></html>
"""

CONFIG_HTML = f"""
<!DOCTYPE html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Config</title>
<style>
 body{{background:#1e1e1e;color:#ddd;font-family:sans-serif;padding:40px}}
 input,select{{width:100%;padding:6px 8px;margin:6px 0;background:#2b2b2b;border:none;border-radius:4px;color:#ddd}}
 button{{padding:8px 14px;background:#3c6d2d;border:none;color:#fff;border-radius:4px;margin-top:12px}}
</style></head>
<body>
  <h2>Mission Control Setup</h2>
  <label>Server<input id='srv'></label>
  <label>Port<input id='prt' type='number'></label>
  <label>Bot Base<input id='bot'></label>
  <label>Role <select id='role'>{options}</select></label>
  <button id='save'>Save</button>
<script>
 async function load(){{
   const cfg = await (await fetch('/api/get_config')).json();
   document.getElementById('srv').value  = cfg.server   || '';
   document.getElementById('prt').value  = cfg.port     || '';
   document.getElementById('bot').value  = cfg.bot_base || '';
   document.getElementById('role').value = cfg.role     || 'FLIGHT';
 }}
 async function save(){{
   const cfg = {{
     server:  document.getElementById('srv').value,
     port:    +document.getElementById('prt').value,
     bot_base:document.getElementById('bot').value,
     role:    document.getElementById('role').value
   }};
   await fetch('/api/save_config', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(cfg)}});
   location.href='/'
 }}
 document.addEventListener('DOMContentLoaded',() => {{ load(); document.getElementById('save').onclick = save; }});
</script></body></html>
"""

# ------------------------------ ROUTES -----------------------------------
@app.route('/')
def main_page():
    return render_template_string(MAIN_HTML, loops=LOOPS, bots=BOTS)

@app.route('/config')
def cfg_page():
    return render_template_string(CONFIG_HTML)

@app.route('/api/get_config')
def api_get_config():
    return jsonify(config)

@app.route('/api/save_config', methods=['POST'])
def api_save_config():
    cfg = request.get_json()
    write_config(cfg)
    return '', 204

# ... define /api/waveform, /api/devices, /api/grid, /api/refresh ...

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--config-only', action='store_true')
    args = parser.parse_args()
    if args.config_only:
        print(f"Running in config-only mode – open http://127.0.0.1:{args.port}/config to set up.")
        app.run(port=args.port, debug=True)
    else:
        app.run(port=args.port, debug=True)
