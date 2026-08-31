#!/usr/bin/env python3
"""Control — visual console UI"""

import json
import time
import os
import importlib.util
from pathlib import Path
from flask import Flask, Response, request, jsonify

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic as _anthropic
except ImportError:
    _anthropic = None

STATE_FILE = Path.home() / ".streamfader" / "state.json"
PORT  = 5570
MODEL = os.environ.get("CTRL_MODEL", "claude-sonnet-4-6")

# Load build_system_prompt from ctrl script without importing the whole CLI
_ctrl_path = Path(__file__).resolve().parent / "ctrl"
if _ctrl_path.exists():
    _spec = importlib.util.spec_from_file_location("_ctrl", _ctrl_path)
    _ctrl = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_ctrl)
    _build_prompt = _ctrl.build_system_prompt
else:
    _build_prompt = lambda s: "You are a helpful AI assistant."

app = Flask(__name__)

# ── State ─────────────────────────────────────────────────────────────────────

def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {
            "mode": "BUILD", "intensity": 0.5, "depth": 0.5,
            "certainty": 0.5, "risk": 0.5, "stance": "GUESS",
            "scope": 0.5, "bandwidth": 0.5, "filter": "PARAMETRIC",
            "room": 0.3, "decay": 0.3, "voice": "STUDIO",
        }

def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE_FILE)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML

@app.route("/stream")
def stream():
    def generate():
        last = {}
        while True:
            state = read_state()
            if state != last:
                last = state.copy()
                yield f"data: {json.dumps(state)}\n\n"
            time.sleep(0.05)
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.route("/set", methods=["POST"])
def set_state():
    data = request.get_json()
    state = read_state()
    state.update(data)
    write_state(state)
    return jsonify({"ok": True})

@app.route("/run", methods=["POST"])
def run_task():
    data    = request.get_json() or {}
    task    = data.get("task", "").strip()
    if not task:
        return jsonify({"error": "No task provided"}), 400
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    def generate():
        if not _anthropic:
            yield f"data: {json.dumps({'error': 'anthropic not installed — pip install anthropic'})}\n\n"
            return
        if not api_key:
            yield f"data: {json.dumps({'error': 'ANTHROPIC_API_KEY not set. Add it to .env or Railway env vars.'})}\n\n"
            return
        state  = read_state()
        system = _build_prompt(state)
        try:
            client = _anthropic.Anthropic(api_key=api_key)
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": task}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/health")
def health():
    return jsonify({"ok": True, "model": MODEL,
                    "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY"))})


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Control</title>
<link href="https://fonts.googleapis.com/css2?family=Abril+Fatface&family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#EDF4EF;font-family:'Inter',sans-serif;color:#0F2419;min-height:100vh;display:flex;flex-direction:column;user-select:none;overflow:hidden;}

/* HEADER */
.hdr{padding:7px 28px;border-bottom:1px solid rgba(6,78,59,.08);background:#fff;display:flex;align-items:center;gap:16px;flex-shrink:0;}
.hdr-badge{font-size:10px;font-weight:700;letter-spacing:.14em;padding:3px 10px 3px 8px;border-radius:3px;border-left:2px solid;transition:all .25s;}
.hdr-vals{margin-left:auto;font-size:8.5px;color:rgba(6,78,59,.35);letter-spacing:.08em;font-variant-numeric:tabular-nums;}

/* HERO BANNER */
.hero{position:relative;flex-shrink:0;height:160px;overflow:hidden;border-bottom:1px solid rgba(6,78,59,.1);}
.hero svg{position:absolute;inset:0;width:100%;height:100%;}
.hero-left{position:absolute;left:32px;top:50%;transform:translateY(-52%);pointer-events:none;z-index:1;}
.hero-brand{font-family:'Abril Fatface',serif;font-size:92px;color:#1A0A2E;line-height:1;letter-spacing:-.01em;}
.hero-tagline{font-size:8px;font-weight:600;letter-spacing:.32em;color:rgba(26,10,46,.38);text-transform:uppercase;margin-top:5px;}

/* GEAR ANIMATIONS */
@keyframes spin-cw  {to{transform:rotate( 360deg);}}
@keyframes spin-ccw {to{transform:rotate(-360deg);}}
.gear-cw  {animation:spin-cw  12s linear infinite;transform-origin:0 0;}
.gear-ccw {animation:spin-ccw  8s linear infinite;transform-origin:0 0;}
.gear-sm  {animation:spin-cw   5s linear infinite;transform-origin:0 0;}

/* CONSOLE */
.console{flex:1;display:flex;justify-content:center;align-items:stretch;padding:20px 20px 14px;gap:3px;}

/* STRIP */
.strip{flex:1;max-width:210px;background:#fff;border:1px solid rgba(6,78,59,.1);border-radius:8px;padding:16px 14px 14px;display:flex;flex-direction:column;align-items:center;gap:12px;position:relative;box-shadow:0 2px 12px rgba(6,78,59,.06);}
.strip-top{position:absolute;top:0;left:50%;transform:translateX(-50%);height:3px;width:48px;border-radius:0 0 3px 3px;}
.strip.t1 .strip-top{background:#064E3B;}
.strip.t2 .strip-top{background:#065F46;}
.strip.t3 .strip-top{background:#047857;}
.strip.t4 .strip-top{background:#059669;}
.strip-id{font-size:7.5px;font-weight:700;letter-spacing:.2em;color:rgba(6,78,59,.3);text-transform:uppercase;margin-top:4px;}

/* KNOB */
.knob-wrap{display:flex;flex-direction:column;align-items:center;gap:5px;width:100%;}
.knob{width:48px;height:48px;border-radius:50%;background:radial-gradient(circle at 36% 30%,#e8f2ec,#d0e4d8);border:1.5px solid rgba(6,78,59,.18);position:relative;cursor:grab;transition:border-color .15s,box-shadow .15s;}
.knob:hover{border-color:rgba(6,78,59,.35);box-shadow:0 2px 8px rgba(6,78,59,.12);}
.knob:active{cursor:grabbing;}
.knob-dot{position:absolute;width:3px;height:13px;background:#064E3B;border-radius:2px;top:5px;left:50%;transform-origin:50% 19px;transform:translateX(-50%) rotate(0deg);transition:none;}
.knob-meta{display:flex;justify-content:space-between;width:100%;padding:0 2px;}
.knob-lbl{font-size:7px;color:rgba(6,78,59,.4);letter-spacing:.1em;text-transform:uppercase;}
.knob-val{font-size:7px;font-weight:600;color:rgba(6,78,59,.6);font-variant-numeric:tabular-nums;}

/* FADER */
.fader-section{display:flex;flex-direction:column;align-items:center;gap:5px;flex:1;}
.fader-lbl{font-size:7px;color:rgba(6,78,59,.4);letter-spacing:.1em;text-transform:uppercase;}
.fader-track{width:14px;height:120px;background:#E8F2EC;border:1px solid rgba(6,78,59,.15);border-radius:7px;position:relative;cursor:pointer;}
.fader-fill{position:absolute;bottom:0;left:0;right:0;border-radius:7px;pointer-events:none;}
.fader-thumb{position:absolute;width:40px;height:18px;border-radius:4px;left:50%;transform:translateX(-50%);background:linear-gradient(180deg,#fff,#e8f0ec);border:1px solid rgba(6,78,59,.2);box-shadow:0 2px 8px rgba(6,78,59,.15);cursor:grab;z-index:2;}
.fader-thumb:active{cursor:grabbing;}
.fader-thumb::before,.fader-thumb::after{content:'';position:absolute;left:18%;right:18%;height:1px;background:rgba(6,78,59,.15);}
.fader-thumb::before{top:calc(50% - 2px);}
.fader-thumb::after{top:calc(50% + 2px);}
.fader-val{font-size:7px;font-weight:600;color:rgba(6,78,59,.5);font-variant-numeric:tabular-nums;}

/* ALL FADERS SAME GREEN SYSTEM */
.fader-fill{background:linear-gradient(0deg,#A7F3D0,#064E3B);}

/* BUTTONS */
.btns{display:flex;flex-direction:column;gap:5px;width:100%;}
.btn{height:27px;border-radius:3px;border:1px solid rgba(6,78,59,.15);background:#fff;color:rgba(6,78,59,.4);font-size:7.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;transition:all .12s;display:flex;align-items:center;justify-content:center;}
.btn:hover{border-color:rgba(6,78,59,.35);color:rgba(6,78,59,.75);background:#F0FAF4;}
.btn.active{background:#064E3B;color:#fff;border-color:#064E3B;box-shadow:0 2px 10px rgba(6,78,59,.25);}

/* TASK PANEL */
.task-panel{background:#fff;border-top:1px solid rgba(6,78,59,.1);padding:10px 28px 12px;flex-shrink:0;}
.task-row{display:flex;gap:10px;align-items:center;}
.task-input{flex:1;height:34px;border:1.5px solid rgba(6,78,59,.18);border-radius:5px;background:#F8FDF9;padding:0 13px;font-family:'Inter',sans-serif;font-size:12px;color:#0F2419;outline:none;transition:border-color .15s,box-shadow .15s;}
.task-input:focus{border-color:#064E3B;box-shadow:0 0 0 3px rgba(6,78,59,.08);}
.task-input::placeholder{color:rgba(6,78,59,.28);}
.task-hint{font-size:7.5px;color:rgba(6,78,59,.28);letter-spacing:.1em;text-transform:uppercase;white-space:nowrap;}
.run-btn{height:34px;padding:0 22px;background:#064E3B;color:#fff;border:none;border-radius:5px;font-family:'Inter',sans-serif;font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;cursor:pointer;transition:background .12s,opacity .12s;white-space:nowrap;}
.run-btn:hover{background:#065F46;}
.run-btn:disabled{opacity:.4;cursor:not-allowed;}
.response-wrap{overflow:hidden;max-height:0;transition:max-height .3s ease;}
.response-wrap.open{max-height:200px;}
.response-box{margin-top:8px;padding:11px 14px;background:#F2FAF5;border:1px solid rgba(6,78,59,.12);border-radius:5px;font-size:11.5px;line-height:1.65;color:#0F2419;font-family:'Inter',sans-serif;white-space:pre-wrap;max-height:180px;overflow-y:auto;}
.response-box .err{color:#B91C1C;}

/* STATUS BAR */
.statusbar{padding:9px 28px;border-top:1px solid rgba(6,78,59,.08);background:#fff;display:flex;gap:24px;font-size:8px;letter-spacing:.1em;color:rgba(6,78,59,.3);flex-shrink:0;}
.sb-item em{font-style:normal;color:rgba(6,78,59,.7);font-weight:600;}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-badge" id="hdr-badge">—</div>
  <div class="hdr-vals" id="hdr-vals">—</div>
</div>

<div class="hero">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 160" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#FFFCE0"/>
        <stop offset="100%" stop-color="#FFE033"/>
      </linearGradient>
    </defs>
    <!-- SKY -->
    <rect width="1200" height="160" fill="url(#sky)"/>

    <!-- ── GEARS (center, floats in sky) ── -->
    <g transform="translate(588,70)"><g class="gear-cw">
      <circle r="36" fill="#1A0A2E"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(45)"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(90)"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(135)"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(180)"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(225)"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(270)"/>
      <rect x="-7" y="-48" width="14" height="14" rx="2" fill="#1A0A2E" transform="rotate(315)"/>
      <circle r="13" fill="#FFE033"/><circle r="4" fill="#1A0A2E"/>
    </g></g>

    <g transform="translate(651,96)"><g class="gear-ccw">
      <circle r="25" fill="#1A0A2E"/>
      <rect x="-6" y="-33" width="12" height="10" rx="2" fill="#1A0A2E"/>
      <rect x="-6" y="-33" width="12" height="10" rx="2" fill="#1A0A2E" transform="rotate(60)"/>
      <rect x="-6" y="-33" width="12" height="10" rx="2" fill="#1A0A2E" transform="rotate(120)"/>
      <rect x="-6" y="-33" width="12" height="10" rx="2" fill="#1A0A2E" transform="rotate(180)"/>
      <rect x="-6" y="-33" width="12" height="10" rx="2" fill="#1A0A2E" transform="rotate(240)"/>
      <rect x="-6" y="-33" width="12" height="10" rx="2" fill="#1A0A2E" transform="rotate(300)"/>
      <circle r="9" fill="#FFE033"/><circle r="3" fill="#1A0A2E"/>
    </g></g>

    <g transform="translate(693,118)"><g class="gear-sm">
      <circle r="16" fill="#1A0A2E"/>
      <rect x="-5" y="-22" width="10" height="8" rx="2" fill="#1A0A2E"/>
      <rect x="-5" y="-22" width="10" height="8" rx="2" fill="#1A0A2E" transform="rotate(60)"/>
      <rect x="-5" y="-22" width="10" height="8" rx="2" fill="#1A0A2E" transform="rotate(120)"/>
      <rect x="-5" y="-22" width="10" height="8" rx="2" fill="#1A0A2E" transform="rotate(180)"/>
      <rect x="-5" y="-22" width="10" height="8" rx="2" fill="#1A0A2E" transform="rotate(240)"/>
      <rect x="-5" y="-22" width="10" height="8" rx="2" fill="#1A0A2E" transform="rotate(300)"/>
      <circle r="5" fill="#FFE033"/><circle r="2" fill="#1A0A2E"/>
    </g></g>

    <!-- Operator figure reaching up toward gears -->
    <g transform="translate(516,142)" stroke="#1A0A2E" stroke-linecap="round" fill="none">
      <circle cx="0" cy="-32" r="8" fill="#1A0A2E" stroke="none"/>
      <line x1="0" y1="-24" x2="0" y2="-7" stroke-width="3"/>
      <line x1="0" y1="-19" x2="-11" y2="-9" stroke-width="2.5"/>
      <line x1="0" y1="-19" x2="18" y2="-40" stroke-width="2.5"/>
      <line x1="0" y1="-7" x2="-7" y2="9" stroke-width="2.5"/>
      <line x1="0" y1="-7" x2="7" y2="9" stroke-width="2.5"/>
    </g>

    <!-- ── BUILDINGS RIGHT ── -->
    <!-- Topiary trees (transition zone) -->
    <rect x="733" y="135" width="5" height="25" fill="#1A0A2E"/>
    <circle cx="736" cy="125" r="13" fill="#1A0A2E"/>
    <circle cx="736" cy="110" r="9" fill="#1A0A2E"/>
    <circle cx="736" cy="99"  r="6" fill="#1A0A2E"/>
    <circle cx="736" cy="91"  r="3" fill="#1A0A2E"/>
    <rect x="757" y="138" width="4" height="22" fill="#1A0A2E"/>
    <circle cx="759" cy="128" r="10" fill="#1A0A2E"/>
    <circle cx="759" cy="116" r="7"  fill="#1A0A2E"/>
    <circle cx="759" cy="107" r="4"  fill="#1A0A2E"/>

    <!-- Short building with battlements -->
    <rect x="775" y="100" width="58" height="60" fill="#1A0A2E"/>
    <rect x="779" y="85"  width="13" height="17" fill="#1A0A2E"/>
    <rect x="805" y="85"  width="13" height="17" fill="#1A0A2E"/>

    <!-- Tall pointed tower -->
    <polygon points="845,160 845,22 861,4 878,22 878,160" fill="#1A0A2E"/>
    <circle cx="861" cy="42" r="8" fill="#FFE033" opacity="0.5"/>
    <circle cx="861" cy="64" r="5" fill="#FFE033" opacity="0.28"/>

    <!-- Wide dome building -->
    <rect x="883" y="70" width="78" height="90" fill="#1A0A2E"/>
    <ellipse cx="922" cy="70" rx="39" ry="19" fill="#1A0A2E"/>
    <circle cx="922" cy="52" r="10" fill="#FFE033" opacity="0.42"/>

    <!-- Short squat building -->
    <rect x="965" y="108" width="44" height="52" fill="#1A0A2E"/>

    <!-- Very tall thin spire -->
    <polygon points="1015,160 1015,12 1028,0 1041,12 1041,160" fill="#1A0A2E"/>
    <circle cx="1028" cy="30" r="7" fill="#FFE033" opacity="0.48"/>

    <!-- Cluster building -->
    <rect x="1045" y="74" width="54" height="86" fill="#1A0A2E"/>
    <rect x="1049" y="58" width="13" height="18" fill="#1A0A2E"/>
    <rect x="1072" y="58" width="13" height="18" fill="#1A0A2E"/>

    <!-- Far right buildings -->
    <rect x="1104" y="92"  width="48" height="68" fill="#1A0A2E"/>
    <polygon points="1104,92 1128,72 1152,92" fill="#1A0A2E"/>
    <rect x="1157" y="114" width="43" height="46" fill="#1A0A2E"/>

    <!-- ── SUN (top right, rising behind spire) ── -->
    <g transform="translate(1118,30)">
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(45)"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(90)"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(135)"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(180)"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(225)"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(270)"/>
      <polygon points="0,-48 -6,-33 6,-33" fill="#FFB300" transform="rotate(315)"/>
      <circle r="28" fill="#FFB300"/>
      <circle cx="-8" cy="-3" r="4"   fill="#1A0A2E"/>
      <circle cx=" 8" cy="-3" r="4"   fill="#1A0A2E"/>
      <circle cx="-8" cy="-3" r="1.5" fill="#FFE033" opacity=".6"/>
      <circle cx=" 8" cy="-3" r="1.5" fill="#FFE033" opacity=".6"/>
      <path d="M-9,8 Q0,18 9,8" stroke="#1A0A2E" stroke-width="2.5" fill="none" stroke-linecap="round"/>
    </g>

    <!-- ── GROUND WAVE (drawn last, covers building bases) ── -->
    <path d="M0,148 Q150,134 350,148 Q550,162 750,144 Q950,128 1200,148 L1200,160 L0,160 Z" fill="#1A0A2E"/>
  </svg>

  <div class="hero-left">
    <div class="hero-brand">control</div>
    <div class="hero-tagline">you hold the dial</div>
  </div>
</div>

<div class="console">

  <!-- T1: MODE / DRIVE -->
  <div class="strip t1">
    <div class="strip-top"></div>
    <div class="strip-id">T1 · MODE / DRIVE</div>

    <div class="knob-wrap">
      <div class="knob" id="knob-depth">
        <div class="knob-dot" id="kd-depth"></div>
      </div>
      <div class="knob-meta">
        <span class="knob-lbl">depth</span>
        <span class="knob-val" id="kv-depth">0.50</span>
      </div>
    </div>

    <div class="fader-section">
      <div class="fader-lbl">intensity</div>
      <div class="fader-track" id="ft-intensity">
        <div class="fader-fill" id="ff-intensity"></div>
        <div class="fader-thumb" id="fth-intensity"></div>
      </div>
      <div class="fader-val" id="fv-intensity">0.50</div>
    </div>

    <div class="btns">
      <div class="btn" data-field="mode" data-val="EXPLORE" onclick="set('mode','EXPLORE')"><span>EXPLORE</span></div>
      <div class="btn" data-field="mode" data-val="FIX"     onclick="set('mode','FIX')"><span>FIX</span></div>
      <div class="btn" data-field="mode" data-val="BUILD"   onclick="set('mode','BUILD')"><span>BUILD</span></div>
    </div>
  </div>

  <!-- T2: CONFIDENCE / DYNAMICS -->
  <div class="strip t2">
    <div class="strip-top"></div>
    <div class="strip-id">T2 · CONFIDENCE</div>

    <div class="knob-wrap">
      <div class="knob" id="knob-risk">
        <div class="knob-dot" id="kd-risk"></div>
      </div>
      <div class="knob-meta">
        <span class="knob-lbl">risk</span>
        <span class="knob-val" id="kv-risk">0.50</span>
      </div>
    </div>

    <div class="fader-section">
      <div class="fader-lbl">certainty</div>
      <div class="fader-track" id="ft-certainty">
        <div class="fader-fill" id="ff-certainty"></div>
        <div class="fader-thumb" id="fth-certainty"></div>
      </div>
      <div class="fader-val" id="fv-certainty">0.50</div>
    </div>

    <div class="btns">
      <div class="btn" data-field="stance" data-val="OPTIONS" onclick="set('stance','OPTIONS')"><span>OPTIONS</span></div>
      <div class="btn" data-field="stance" data-val="GUESS"   onclick="set('stance','GUESS')"><span>GUESS</span></div>
      <div class="btn" data-field="stance" data-val="DECIDE"  onclick="set('stance','DECIDE')"><span>DECIDE</span></div>
    </div>
  </div>

  <!-- T3: EQ / SCOPE -->
  <div class="strip t3">
    <div class="strip-top"></div>
    <div class="strip-id">T3 · EQ / SCOPE</div>

    <div class="knob-wrap">
      <div class="knob" id="knob-bandwidth">
        <div class="knob-dot" id="kd-bandwidth"></div>
      </div>
      <div class="knob-meta">
        <span class="knob-lbl">bandwidth</span>
        <span class="knob-val" id="kv-bandwidth">0.50</span>
      </div>
    </div>

    <div class="fader-section">
      <div class="fader-lbl">scope</div>
      <div class="fader-track" id="ft-scope">
        <div class="fader-fill" id="ff-scope"></div>
        <div class="fader-thumb" id="fth-scope"></div>
      </div>
      <div class="fader-val" id="fv-scope">0.50</div>
    </div>

    <div class="btns">
      <div class="btn" data-field="filter" data-val="HIGHPASS"   onclick="set('filter','HIGHPASS')"><span>HIGHPASS</span></div>
      <div class="btn" data-field="filter" data-val="PARAMETRIC" onclick="set('filter','PARAMETRIC')"><span>PARAMETRIC</span></div>
      <div class="btn" data-field="filter" data-val="LOWPASS"    onclick="set('filter','LOWPASS')"><span>LOWPASS</span></div>
    </div>
  </div>

  <!-- T4: ROOM / VOICE -->
  <div class="strip t4">
    <div class="strip-top"></div>
    <div class="strip-id">T4 · ROOM / VOICE</div>

    <div class="knob-wrap">
      <div class="knob" id="knob-decay">
        <div class="knob-dot" id="kd-decay"></div>
      </div>
      <div class="knob-meta">
        <span class="knob-lbl">decay</span>
        <span class="knob-val" id="kv-decay">0.30</span>
      </div>
    </div>

    <div class="fader-section">
      <div class="fader-lbl">room</div>
      <div class="fader-track" id="ft-room">
        <div class="fader-fill" id="ff-room"></div>
        <div class="fader-thumb" id="fth-room"></div>
      </div>
      <div class="fader-val" id="fv-room">0.30</div>
    </div>

    <div class="btns">
      <div class="btn" data-field="voice" data-val="ANECHOIC" onclick="set('voice','ANECHOIC')"><span>ANECHOIC</span></div>
      <div class="btn" data-field="voice" data-val="STUDIO"   onclick="set('voice','STUDIO')"><span>STUDIO</span></div>
      <div class="btn" data-field="voice" data-val="HALL"     onclick="set('voice','HALL')"><span>HALL</span></div>
    </div>
  </div>

</div>

<div class="task-panel">
  <div class="task-row">
    <input class="task-input" id="task-input" type="text" placeholder="what should claude do?">
    <span class="task-hint">⌘↵ run</span>
    <button class="run-btn" id="run-btn">Run</button>
  </div>
  <div class="response-wrap" id="response-wrap">
    <div class="response-box" id="response-box"></div>
  </div>
</div>

<div class="statusbar">
  <span class="sb-item">MODE <em id="sb-mode">—</em></span>
  <span class="sb-item">STANCE <em id="sb-stance">—</em></span>
  <span class="sb-item">FILTER <em id="sb-filter">—</em></span>
  <span class="sb-item">VOICE <em id="sb-voice">—</em></span>
  <span style="margin-left:auto" id="sb-time">—</span>
</div>

<script>
const TRACK_H = 120, THUMB_H = 18, RANGE = TRACK_H - THUMB_H;

const FADERS = {
  intensity: {fill:'ff-intensity', thumb:'fth-intensity', val:'fv-intensity', track:'ft-intensity'},
  certainty: {fill:'ff-certainty', thumb:'fth-certainty', val:'fv-certainty', track:'ft-certainty'},
  scope:     {fill:'ff-scope',     thumb:'fth-scope',     val:'fv-scope',     track:'ft-scope'},
  room:      {fill:'ff-room',      thumb:'fth-room',      val:'fv-room',      track:'ft-room'},
};
const KNOBS = {
  depth:     {dot:'kd-depth',     val:'kv-depth'},
  risk:      {dot:'kd-risk',      val:'kv-risk'},
  bandwidth: {dot:'kd-bandwidth', val:'kv-bandwidth'},
  decay:     {dot:'kd-decay',     val:'kv-decay'},
};
const BADGE_COLORS = {EXPLORE:'#0369A1', FIX:'#B45309', BUILD:'#064E3B'};

let isDragging = false;

function setFader(field, v) {
  const f = FADERS[field]; if (!f) return;
  document.getElementById(f.fill).style.height  = (v*100)+'%';
  document.getElementById(f.thumb).style.bottom = (v*RANGE)+'px';
  document.getElementById(f.val).textContent    = v.toFixed(2);
}
function setKnob(field, v) {
  const k = KNOBS[field]; if (!k) return;
  const deg = -135 + v*270;
  document.getElementById(k.dot).style.transform = `translateX(-50%) rotate(${deg}deg)`;
  document.getElementById(k.val).textContent = v.toFixed(2);
}
function setButtons(field, active) {
  document.querySelectorAll(`.btn[data-field="${field}"]`).forEach(b => {
    b.classList.toggle('active', b.dataset.val === active);
  });
}
function applyState(s) {
  setFader('intensity', s.intensity ?? 0.5);
  setFader('certainty', s.certainty ?? 0.5);
  setFader('scope',     s.scope     ?? 0.5);
  setFader('room',      s.room      ?? 0.3);
  setKnob('depth',     s.depth     ?? 0.5);
  setKnob('risk',      s.risk      ?? 0.5);
  setKnob('bandwidth', s.bandwidth ?? 0.5);
  setKnob('decay',     s.decay     ?? 0.3);
  setButtons('mode',   s.mode);
  setButtons('stance', s.stance);
  setButtons('filter', s.filter);
  setButtons('voice',  s.voice);
  const col = BADGE_COLORS[s.mode] || '#555';
  const badge = document.getElementById('hdr-badge');
  badge.textContent = s.mode || '—';
  badge.style.color = col;
  badge.style.background = col+'18';
  badge.style.borderLeftColor = col;
  document.getElementById('hdr-vals').textContent =
    `I ${(s.intensity??0).toFixed(2)}  D ${(s.depth??0).toFixed(2)}  C ${(s.certainty??0).toFixed(2)}  R ${(s.risk??0).toFixed(2)}`;
  document.getElementById('sb-mode').textContent   = s.mode   || '—';
  document.getElementById('sb-stance').textContent = s.stance || '—';
  document.getElementById('sb-filter').textContent = s.filter || '—';
  document.getElementById('sb-voice').textContent  = s.voice  || '—';
  document.getElementById('sb-time').textContent   = new Date().toLocaleTimeString();
}
async function set(field, value) {
  await fetch('/set', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({[field]: value})});
}

const es = new EventSource('/stream');
es.onmessage = e => { if (!isDragging) applyState(JSON.parse(e.data)); };
es.onerror   = () => { document.getElementById('hdr-vals').textContent = 'reconnecting...'; };

// Each drag gets its own isolated mousemove+mouseup pair — no shared state contention
function bindDrag(el, getStartVal, onMove, onDrop) {
  el.addEventListener('mousedown', e => {
    e.preventDefault();
    isDragging    = true;
    const startY  = e.clientY;
    const startV  = getStartVal();

    function move(e2) { onMove(startY, e2.clientY, startV); }
    function up()   {
      isDragging = false;
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup',   up);
      onDrop();
    }
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup',   up);
  });
}

Object.entries(FADERS).forEach(([field, ids]) => {
  const trackEl = document.getElementById(ids.track);
  const thumbEl = document.getElementById(ids.thumb);
  function getV()  { return parseFloat(document.getElementById(ids.val).textContent); }
  function move(sy, cy, sv) { setFader(field, Math.max(0, Math.min(1, sv + (sy-cy)/RANGE))); }
  function drop()  { set(field, Math.round(getV()*1000)/1000); }
  bindDrag(trackEl, getV, move, drop);
  bindDrag(thumbEl, getV, move, drop);
});

Object.entries(KNOBS).forEach(([field, ids]) => {
  const knobEl = document.getElementById('knob-'+field);
  function getV()  { return parseFloat(document.getElementById(ids.val).textContent); }
  function move(sy, cy, sv) { setKnob(field, Math.max(0, Math.min(1, sv + (sy-cy)/120))); }
  function drop()  { set(field, Math.round(getV()*1000)/1000); }
  bindDrag(knobEl, getV, move, drop);
});

// ── TASK RUN ─────────────────────────────────────────────────────────────────
const taskInput = document.getElementById('task-input');
const runBtn    = document.getElementById('run-btn');
const respWrap  = document.getElementById('response-wrap');
const respBox   = document.getElementById('response-box');

async function runTask() {
  const task = taskInput.value.trim();
  if (!task || runBtn.disabled) return;
  runBtn.disabled = true;
  runBtn.textContent = '···';
  respBox.textContent = '';
  respWrap.classList.add('open');
  try {
    const res = await fetch('/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task}),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const d = JSON.parse(line.slice(6));
        if (d.text)  { respBox.textContent += d.text; respBox.scrollTop = respBox.scrollHeight; }
        if (d.error) { respBox.innerHTML = '<span class="err">Error: ' + d.error + '</span>'; }
        if (d.done)  { runBtn.disabled = false; runBtn.textContent = 'Run'; }
      }
    }
  } catch(e) {
    respBox.innerHTML = '<span class="err">' + e.message + '</span>';
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = 'Run';
  }
}

runBtn.addEventListener('click', runTask);
taskInput.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') runTask();
});
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"┌──────────────────────────────────────────────┐")
    print(f"│   Control  ·  visual console                 │")
    print(f"│   http://127.0.0.1:{PORT}                      │")
    print(f"│   Open on iPad: http://<your-mac-ip>:{PORT}   │")
    print(f"│   Ctrl+C to stop                             │")
    print(f"└──────────────────────────────────────────────┘")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
