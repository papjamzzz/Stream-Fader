#!/usr/bin/env python3
"""
Mode Via MIDI — nanoKONTROL2 bridge
Track 1: Fader=intensity  Knob=depth    S=EXPLORE  M=FIX      R=BUILD
Track 2: Fader=certainty  Knob=risk     S=OPTIONS  M=GUESS    R=DECIDE
"""

import json
import sys
import time
import argparse
from pathlib import Path

try:
    import mido
except ImportError:
    sys.exit("[nano] mido not installed. Run: pip3 install mido python-rtmidi")

STATE_FILE  = Path.home() / ".streamfader" / "state.json"
CONFIG_FILE = Path.home() / ".streamfader" / "nano_config.json"

# ── Profiles ──────────────────────────────────────────────────────────────────

PROFILES = {
    "EXPLORE": {"mode": "EXPLORE", "intensity": 0.2, "depth": 0.8},
    "FIX":     {"mode": "FIX",     "intensity": 0.8, "depth": 0.5},
    "BUILD":   {"mode": "BUILD",   "intensity": 0.7, "depth": 0.6},
}

# nanoKONTROL2 default Scene 1 — Tracks 1 & 2
DEFAULT_CONFIG = {
    "port_hint": "nanokontrol",
    "mapping": {
        # Track 1
        "intensity": {"type": "cc_continuous",    "control": 0},   # Fader 1
        "depth":     {"type": "cc_continuous",    "control": 16},  # Knob 1
        "EXPLORE":   {"type": "cc_mode_button",   "control": 32},  # S1
        "FIX":       {"type": "cc_mode_button",   "control": 48},  # M1
        "BUILD":     {"type": "cc_mode_button",   "control": 64},  # R1
        # Track 2
        "certainty":  {"type": "cc_continuous",    "control": 1},   # Fader 2
        "risk":       {"type": "cc_continuous",    "control": 17},  # Knob 2
        "OPTIONS":    {"type": "cc_stance_button", "control": 33},  # S2
        "GUESS":      {"type": "cc_stance_button", "control": 49},  # M2
        "DECIDE":     {"type": "cc_stance_button", "control": 65},  # R2
        # Track 3
        "scope":      {"type": "cc_continuous",    "control": 2},   # Fader 3
        "bandwidth":  {"type": "cc_continuous",    "control": 18},  # Knob 3
        "HIGHPASS":   {"type": "cc_filter_button", "control": 34},  # S3
        "PARAMETRIC": {"type": "cc_filter_button", "control": 50},  # M3
        "LOWPASS":    {"type": "cc_filter_button", "control": 66},  # R3
        # Track 4
        "room":       {"type": "cc_continuous",    "control": 3},   # Fader 4
        "decay":      {"type": "cc_continuous",    "control": 19},  # Knob 4
        "ANECHOIC":   {"type": "cc_voice_button",  "control": 35},  # S4
        "STUDIO":     {"type": "cc_voice_button",  "control": 51},  # M4
        "HALL":       {"type": "cc_voice_button",  "control": 67},  # R4
    },
}


# ── State ─────────────────────────────────────────────────────────────────────

def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return PROFILES["BUILD"].copy()


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE_FILE)


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


# ── Port detection ────────────────────────────────────────────────────────────

def find_port(hint: str):
    ports = mido.get_input_names()
    return next((p for p in ports if hint.lower() in p.lower()), None)


def find_output_port(hint: str):
    ports = mido.get_output_names()
    return next((p for p in ports if hint.lower() in p.lower()), None)


# ── Display ───────────────────────────────────────────────────────────────────

def _bar(v: float, width: int = 14) -> str:
    filled = round(v * width)
    return "█" * filled + "░" * (width - filled)


def render_state(state: dict, event: str = "") -> None:
    mode      = state.get("mode", "?")
    intensity = state.get("intensity", 0.0)
    depth     = state.get("depth", 0.0)
    evt       = f"  ← {event}" if event else ""
    line = (
        f"  [{mode:<7}]  "
        f"I [{_bar(intensity)}] {intensity:.2f}  "
        f"D [{_bar(depth)}] {depth:.2f}"
        f"{evt}"
    )
    print(f"\r{line:<72}", end="", flush=True)


# ── LED feedback ──────────────────────────────────────────────────────────────

BUTTON_FIELD = {
    "cc_mode_button":   "mode",
    "cc_stance_button": "stance",
    "cc_filter_button": "filter",
    "cc_voice_button":  "voice",
}

def build_led_map(mapping: dict) -> dict:
    """Returns {field: {value: control_number}} from the config mapping."""
    led = {}
    for key, val in mapping.items():
        field = BUTTON_FIELD.get(val["type"])
        if field:
            led.setdefault(field, {})[key] = val["control"]
    return led


def send_leds(out_port, state: dict, led_map: dict) -> None:
    for field, options in led_map.items():
        active = state.get(field, "")
        for val, control in options.items():
            out_port.send(mido.Message(
                "control_change", channel=0,
                control=control,
                value=127 if val == active else 0,
            ))


def clear_leds(out_port, led_map: dict) -> None:
    for options in led_map.values():
        for control in options.values():
            out_port.send(mido.Message("control_change", channel=0, control=control, value=0))


# ── Bridge ────────────────────────────────────────────────────────────────────

def run_bridge(cfg: dict) -> None:
    hint = cfg.get("port_hint", "nanokontrol")
    port_name = find_port(hint)

    if not port_name:
        ports = mido.get_input_names()
        print(f"[nano] nanoKONTROL2 not found.")
        print(f"  Hint searched: '{hint}'")
        print(f"  Available ports: {ports or ['(none)']}")
        print(f"  Is it plugged in? Try: mvm nano --scan to list ports.")
        sys.exit(1)

    out_name = find_output_port(hint)

    mapping = cfg.get("mapping", DEFAULT_CONFIG["mapping"])
    led_map = build_led_map(mapping)

    # Build fast lookup tables
    cc_continuous     = {}  # control → field name
    cc_mode_buttons   = {}  # control → EXPLORE | FIX | BUILD
    cc_stance_buttons = {}  # control → OPTIONS | GUESS | DECIDE
    cc_filter_buttons = {}  # control → HIGHPASS | PARAMETRIC | LOWPASS
    cc_voice_buttons  = {}  # control → ANECHOIC | STUDIO | HALL

    for key, val in mapping.items():
        t = val["type"]
        if t == "cc_continuous":
            cc_continuous[val["control"]] = key
        elif t in ("cc_button", "cc_mode_button"):
            cc_mode_buttons[val["control"]] = key
        elif t == "cc_stance_button":
            cc_stance_buttons[val["control"]] = key
        elif t == "cc_filter_button":
            cc_filter_buttons[val["control"]] = key
        elif t == "cc_voice_button":
            cc_voice_buttons[val["control"]] = key

    state = read_state()

    led_note = f"LEDs → {out_name}" if out_name else "LEDs → not found (External LED mode required)"
    print("┌────────────────────────────────────────────────────────┐")
    print("│   Control  ·  nanoKONTROL2                            │")
    print(f"│   Port: {port_name:<48}│")
    print(f"│   {led_note:<55}│")
    print("│   T1: Fader=intensity  Knob=depth     S/M/R=mode      │")
    print("│   T2: Fader=certainty  Knob=risk      S/M/R=stance    │")
    print("│   T3: Fader=scope      Knob=bandwidth S/M/R=filter    │")
    print("│   T4: Fader=room       Knob=decay     S/M/R=voice     │")
    print("│   Ctrl+C to stop                                       │")
    print("└────────────────────────────────────────────────────────┘")
    print()
    render_state(state, "ready")
    print()

    import contextlib

    @contextlib.contextmanager
    def open_output_maybe(name):
        if name:
            with mido.open_output(name) as p:
                yield p
        else:
            yield None

    with mido.open_input(port_name) as port, open_output_maybe(out_name) as out_port:

        # Sync LEDs to current state on startup
        if out_port:
            send_leds(out_port, state, led_map)

        try:
            for msg in port:

                changed = False
                event   = ""

                if msg.type == "control_change":

                    # Fader or Knob — continuous value
                    if msg.control in cc_continuous:
                        target        = cc_continuous[msg.control]
                        value         = round(msg.value / 127, 3)
                        state[target] = value
                        event         = f"{target}={value:.2f}"
                        changed       = True

                    # Mode button — loads profile, preserves all live knob/fader values
                    elif msg.control in cc_mode_buttons and msg.value > 0:
                        profile_name = cc_mode_buttons[msg.control]
                        profile      = PROFILES[profile_name].copy()
                        for field in ("intensity","depth","certainty","risk","stance",
                                      "scope","bandwidth","filter","room","decay","voice"):
                            if field in state:
                                profile[field] = state[field]
                        state   = profile
                        event   = profile_name
                        changed = True

                    # Stance button
                    elif msg.control in cc_stance_buttons and msg.value > 0:
                        state["stance"] = cc_stance_buttons[msg.control]
                        event   = f"stance={state['stance']}"
                        changed = True

                    # Filter button (scope/EQ)
                    elif msg.control in cc_filter_buttons and msg.value > 0:
                        state["filter"] = cc_filter_buttons[msg.control]
                        event   = f"filter={state['filter']}"
                        changed = True

                    # Voice button (room/reverb)
                    elif msg.control in cc_voice_buttons and msg.value > 0:
                        state["voice"] = cc_voice_buttons[msg.control]
                        event   = f"voice={state['voice']}"
                        changed = True

                if changed:
                    write_state(state)
                    render_state(state, event)
                    if out_port:
                        send_leds(out_port, state, led_map)

        except KeyboardInterrupt:
            if out_port:
                clear_leds(out_port, led_map)
            print("\n\n[nano] Stopped.")


# ── Scan ──────────────────────────────────────────────────────────────────────

def run_scan() -> None:
    print("┌────────────────────────────────────────────────────────┐")
    print("│   MODE VIA MIDI  ·  nanoKONTROL2 Scan                 │")
    print("└────────────────────────────────────────────────────────┘")
    print()

    ports = mido.get_input_names()
    print(f"  MIDI input ports ({len(ports)} found):")
    for i, p in enumerate(ports):
        print(f"    [{i}] {p}")
    print()

    if not ports:
        print("  No MIDI ports found. Is the nanoKONTROL2 plugged in?")
        sys.exit(1)

    hint = DEFAULT_CONFIG["port_hint"]
    port_name = find_port(hint)

    if not port_name:
        print(f"  nanoKONTROL2 not auto-detected (searching for '{hint}').")
        idx = input("  Enter port number to use: ").strip()
        port_name = ports[int(idx)]

    print(f"  Listening on: {port_name}")
    print("  Touch every fader, knob, and button on Track 1.")
    print("  Ctrl+C to stop.\n")

    seen = {}

    with mido.open_input(port_name) as port:
        try:
            for msg in port:
                if msg.type in ("clock", "active_sensing"):
                    continue

                key = f"{msg.type}"
                if msg.type == "control_change":
                    key = f"CC  control={msg.control:<3}"
                    if msg.control not in seen:
                        seen[msg.control] = True
                        print(f"  {key}  value={msg.value:<3}  ← new")
                    else:
                        print(f"  {key}  value={msg.value:<3}", end="\r")

                elif msg.type in ("note_on", "note_off"):
                    key = f"{msg.type:<8} note={msg.note:<3} vel={msg.velocity}"
                    print(f"  {key}")

                else:
                    print(f"  {msg}")

        except KeyboardInterrupt:
            print("\n\n  Scan complete.")
            print()
            print("  Default Track 1 mapping to verify:")
            print("    Fader 1  →  CC control=0")
            print("    Knob  1  →  CC control=16")
            print("    S1       →  note_on note=32")
            print("    M1       →  note_on note=48")
            print("    R1       →  note_on note=64")
            print()
            print("  If your numbers match, run:  mvm nano --start")
            print("  If not, edit:  ~/.streamfader/nano_config.json")


# ── Entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mvm nano",
        description="nanoKONTROL2 → StreamFader bridge",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true", help="Start bridge (default)")
    group.add_argument("--scan",  action="store_true", help="List ports and print raw MIDI")
    args = parser.parse_args()

    if args.scan:
        run_scan()
    else:
        cfg = load_config()
        run_bridge(cfg)


if __name__ == "__main__":
    main()
