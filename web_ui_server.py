from flask import Flask, render_template_string, jsonify, request
import json, os, requests, time, sys

# --------------------------------- configuration ---------------------------------
from config_dialog import read_config, write_config
config = read_config() or {}
role = config.get("role", "FLIGHT")
def load_loops(r):
    lf = os.path.join("LOOPS", f"loops_{r.upper()}.txt")
    try:
        with open(lf, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {lf}: {e}")
        return []

LOOPS = load_loops(role)

# --------------------------------- bot pool ---------------------------------
BOTS = [
    {"name": "BOT1", "port": 6001},
    {"name": "BOT2", "port": 6002},
    {"name": "BOT3", "port": 6003},
]

bot_pool = {b['name']: {'port': b['port'], 'assigned': None, 'last_used': 0} for b in BOTS}
loop_states = {loop['name']: (0, None) for loop in LOOPS}  # state, bot

def update_config(new_cfg):
    global config, role, LOOPS, loop_states
    config = new_cfg
    role = config.get("role", "FLIGHT")
    LOOPS = load_loops(role)
    loop_states = {loop['name']: (0, None) for loop in LOOPS}

def find_idle_bot():
    idle = [(n, d) for n, d in bot_pool.items() if d['assigned'] is None]
    if not idle:
        return None
    idle.sort(key=lambda x: x[1]['last_used'])
    return idle[0][0]

# --------------------------------- flask ---------------------------------
app = Flask(__name__)

TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Voice Loops</title>
  <style>
    :root {
      --bg:#1e1e1e; --panel:#2b2b2b; --txt:#ddd; --accent-listen:#325c8d; --accent-talk:#3c6d2d; --danger:#b41b1b;
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:sans-serif;background:var(--bg);color:var(--txt);}
    #controls{display:flex;align-items:center;padding:10px;background:var(--panel)}
    select,button{margin-right:10px;padding:6px 10px;background:#3a3a3a;border:none;border-radius:4px;color:var(--txt)}
    select:hover,button:hover{background:#4a4a4a;cursor:pointer}
    #waveCanvas{width:150px;height:40px;border:1px solid #444;border-radius:4px;margin-left:auto}

    #grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;padding:18px;grid-auto-rows:220px}
    .card{position:relative;background:var(--panel);border-radius:12px;box-shadow:0 0 6px rgba(0,0,0,.6);height:100%%;overflow:hidden}
    .card.off{background:var(--panel)}
    .card.listen{background:var(--accent-listen)}
    .card.talk{background:var(--accent-talk)}

    .loop-name{position:absolute;top:50%%;left:50%%;transform:translate(-50%%,-50%%);text-align:center;font-weight:600;line-height:1.2;padding:0 4px}
    .privileges{position:absolute;top:8px;left:10px;font-size:1rem}
    .count{position:absolute;top:8px;right:10px;font-size:.9rem}

    .vol-slider{position:absolute;bottom:10px;left:10px;width:55%%}
    .off-btn{position:absolute;bottom:6px;right:10px;padding:4px 10px;background:var(--danger);border:none;border-radius:4px;color:#fff;font-weight:600}
    .off-btn:hover{filter:brightness(1.1);cursor:pointer}

    #logo{position:fixed;bottom:10px;right:10px;height:60px;opacity:.6}
  </style>
</head>
<body>
  <div id="controls">
    <label>Input:<select id="inDevice"></select></label>
    <label>Output:<select id="outDevice"></select></label>
    <button id="delayBtn">Delay</button>
    <canvas id="waveCanvas"></canvas>
  </div>
  <div id="grid"></div>
  <img id="logo" src="{{ url_for('static', filename='logo2.png') }}" alt="logo">
<script>
let LOOPS=[], delayEnabled=false;

// ------------------- util -------------------
const primaryPort={{port}};
function getBot(idx){return {{bots}}[idx %% {{bots}}.length];}

// ------------------- init -------------------
async function init(){
  const cfg=await (await fetch('/api/config')).json(); LOOPS=cfg.loops;
  await enumerateDevices(); startAudioMonitor(); buildGrid(); setDelayHandler(); await refresh(); setInterval(refresh,1000);
}

// ------------------- grid -------------------
function buildGrid(){
  const grid=document.getElementById('grid'); grid.innerHTML='';
  LOOPS.forEach((loop,idx)=>{
    const card=document.createElement('div'); card.className='card off'; card.dataset.loop=loop.name;
    const priv=`<span class='privileges'>${loop.can_listen?'🎧':''}${loop.can_talk?'🎤':''}</span>`;
    card.innerHTML=`${priv}<span class='count'>👥0</span><div class='loop-name'>${loop.name}</div><input type='range' min='0' max='1' step='0.01' value='0.5' class='vol-slider'><button class='off-btn'>OFF</button>`;

    card.addEventListener('click',e=>{if(e.target===card) act('toggle',loop.name);});
    card.querySelector('.off-btn').addEventListener('click',e=>{e.stopPropagation(); act('off',loop.name);});
    const slider=card.querySelector('.vol-slider');
    const bot=getBot(idx);
    slider.addEventListener('input',e=>{e.stopPropagation(); fetch(`http://127.0.0.1:${bot.port}/set_volume`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volume:e.target.value})});});

    grid.append(card);
  });
}

// ------------------- UI Actions -------------------
async function act(action,loop){await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,loop})}); await refresh();}
function setDelayHandler(){const btn=document.getElementById('delayBtn'); btn.onclick=async()=>{delayEnabled=!delayEnabled;btn.style.background=delayEnabled?'#43d843':'#c22c2c'; await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delay',enabled:delayEnabled})});};}

// ------------------- polling -------------------
async function refresh(){const res=await fetch('/api/status'); const info=await res.json(); LOOPS.forEach(loop=>{const card=document.querySelector(`[data-loop="${loop.name}"]`); if(!card)return; card.querySelector('.count').textContent=`👥${info.user_counts[loop.name]||0}`; card.classList.remove('off','listen','talk'); const st=info.states[loop.name]||0; card.classList.add(st===1?'listen':st===2?'talk':'off');});}

// ------------------- devices -------------------
async function enumerateDevices(){try{const devs=await navigator.mediaDevices.enumerateDevices(); const inSel=document.getElementById('inDevice'),outSel=document.getElementById('outDevice'); devs.filter(d=>d.kind==='audioinput').forEach((d,i)=>inSel.add(new Option(d.label||`Mic ${i}`,d.deviceId))); devs.filter(d=>d.kind==='audiooutput').forEach((d,i)=>outSel.add(new Option(d.label||`Spkr ${i}`,d.deviceId))); inSel.onchange=()=>changeDev('in',inSel.value); outSel.onchange=()=>changeDev('out',outSel.value);}catch(e){console.error(e);}}
function changeDev(type,id){fetch(`http://127.0.0.1:${primaryPort}/device_${type}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:id})});}

// ------------------- waveform -------------------
async function startAudioMonitor(){try{const stream=await navigator.mediaDevices.getUserMedia({audio:true}); const ctxA=new(window.AudioContext||window.webkitAudioContext)(); const src=ctxA.createMediaStreamSource(stream); const analyser=ctxA.createAnalyser(); analyser.fftSize=256; src.connect(analyser); const data=new Uint8Array(analyser.fftSize); const ctx=document.getElementById('waveCanvas').getContext('2d'); (function draw(){requestAnimationFrame(draw); analyser.getByteTimeDomainData(data); ctx.clearRect(0,0,150,40); ctx.beginPath(); for(let i=0;i<data.length;i++){const x=i*150/data.length; const y=(data[i]/128)*20; i?ctx.lineTo(x,y):ctx.moveTo(x,y);} ctx.strokeStyle='#4a4a4a'; ctx.stroke();})();}catch(e){console.error(e);}}

// ------------------- start -------------------
document.addEventListener('DOMContentLoaded',init);
</script>
</body>
</html>
"""

CONFIG_TEMPLATE = r"""
<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>Setup</title>
  <style>
    body{font-family:sans-serif;background:#1e1e1e;color:#ddd;padding:40px}
    input,select{margin:5px 0;padding:6px 8px;background:#2b2b2b;border:none;color:#ddd;border-radius:4px;width:100%%}
    button{padding:8px 14px;margin-top:10px;background:#3c6d2d;border:none;color:#fff;border-radius:4px}
  </style>
</head>
<body>
  <h2>Mission Control Config</h2>
  <label>Server <input id='srv'></label>
  <label>Port <input id='prt' type='number'></label>
  <label>Bot Base <input id='bot'></label>
  <label>Role
    <select id='role'>
      %s
    </select>
  </label>
  <button id='save'>Save</button>
  <script>
    async function load(){
      const cfg=await (await fetch('/api/get_config')).json();
      document.getElementById('srv').value=cfg.server||'';
      document.getElementById('prt').value=cfg.port||'';
      document.getElementById('bot').value=cfg.bot_base||'';
      document.getElementById('role').value=cfg.role||'FLIGHT';
    }
    async function save(){
      const cfg={server:srv.value,port:parseInt(prt.value),bot_base:bot.value,role:role.value};
      await fetch('/api/save_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
      location.href='/';
    }
    document.getElementById('save').onclick=save;
    document.addEventListener('DOMContentLoaded',load);
  </script>
</body>
</html>
""" % ("".join(f"<option value='{r}'>{r}</option>" for r in ['FLIGHT','CAPCOM','FAO','BME','CPOO','SCIENCE','EVA']))

# --------------------------------- routes ---------------------------------
@app.route('/')
def index():
    rendered = TEMPLATE.replace('{{port}}', str(BOTS[0]['port'])) \
                       .replace('{{bots}}', json.dumps(BOTS))
    return render_template_string(rendered)

@app.route('/config')
def config_page():
    return render_template_string(CONFIG_TEMPLATE)

@app.route('/api/get_config')
def get_config_api():
    return jsonify(config)

@app.route('/api/save_config', methods=['POST'])
def save_config_api():
    data = request.get_json(force=True)
    write_config(data['server'], int(data['port']), data['bot_base'], data['role'])
    update_config(data)
    return '', 204

@app.route('/api/config')
def config_api():
    return jsonify(loops=LOOPS)

@app.route('/api/status')
def status_api():
    counts = {l['name']: 0 for l in LOOPS}
    states = {name: st for name, (st, _) in loop_states.items()}
    for bot in BOTS:
        try:
            res = requests.get(f"http://127.0.0.1:{bot['port']}/status", timeout=0.5).json()
            counts.update(res.get('user_counts', {}))
            for ln, st in res.get('states', {}).items():
                states[ln] = st
        except Exception:
            pass
    return jsonify(user_counts=counts, states=states)

@app.route('/api/command', methods=['POST'])
def command_api():
    data = request.get_json(force=True)
    act = data.get('action')
    loop = data.get('loop')
    if act == 'delay':
        for b in bot_pool.values():
            path = 'delay_on' if data.get('enabled') else 'delay_off'
            try:
                requests.post(f"http://127.0.0.1:{b['port']}/{path}")
            except:
                pass
        return '', 204

    old_state, old_bot = loop_states.get(loop, (0, None))
    if act == 'off':
        if old_bot:
            p = bot_pool[old_bot]['port']
            requests.post(f"http://127.0.0.1:{p}/leave")
            requests.post(f"http://127.0.0.1:{p}/mute")
            bot_pool[old_bot]['assigned'] = None
            bot_pool[old_bot]['last_used'] = time.time()
        loop_states[loop] = (0, None)
        return '', 204

    cfg = next((l for l in LOOPS if l['name'] == loop), {})
    new_state = 1 if old_state == 0 else (2 if old_state == 1 and cfg.get('can_talk') else 1)
    if not cfg.get('can_listen'):
        return '', 204

    assigned = old_bot or find_idle_bot()
    if not assigned:
        return '', 204
    port = bot_pool[assigned]['port']

    if new_state == 1:
        requests.post(f"http://127.0.0.1:{port}/join", json={'loop': loop})
        requests.post(f"http://127.0.0.1:{port}/mute")
    elif new_state == 2:
        for other, (st, ob) in loop_states.items():
            if st == 2 and ob:
                op = bot_pool[ob]['port']
                requests.post(f"http://127.0.0.1:{op}/mute")
                loop_states[other] = (1, ob)
        requests.post(f"http://127.0.0.1:{port}/join", json={'loop': loop})
        requests.post(f"http://127.0.0.1:{port}/talk")

    bot_pool[assigned]['assigned'] = loop
    bot_pool[assigned]['last_used'] = time.time()
    loop_states[loop] = (new_state, assigned)
    return '', 204

# --------------------------------- main ---------------------------------
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-only', action='store_true')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    app.run(debug=True, port=args.port)
