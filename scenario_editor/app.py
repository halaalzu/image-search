"""
OpenMATB Scenario Editor
========================
Run:  streamlit run scenario_editor/app.py
      (from the project root, or just double-click run_editor.bat)
"""

from __future__ import annotations
import copy
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import json

# ── Paths ─────────────────────────────────────────────────────────────────────
# OPENMATB_ROOT lets packaged launcher point the editor at the sibling MATB bundle.
ROOT = Path(os.getenv("OPENMATB_ROOT", Path(__file__).resolve().parent.parent)).resolve()
SCENARIOS_DIR = ROOT / "includes" / "scenarios"
sys.path.insert(0, str(ROOT))

# Load report options JSON (used to populate report dropdowns)
REPORT_OPTIONS_FILE = ROOT / "includes" / "report_options.json"
try:
    REPORT_OPTIONS = json.loads(REPORT_OPTIONS_FILE.read_text(encoding="utf-8")).get("reports", [])
    if not isinstance(REPORT_OPTIONS, list):
        REPORT_OPTIONS = [str(REPORT_OPTIONS)]
except Exception:
    REPORT_OPTIONS = ["REPORT"]


def get_report_choices(current_value: str | None = None) -> list[str]:
    """Return report dropdown choices with REPORT always available as fallback."""
    choices: list[str] = []
    for item in REPORT_OPTIONS:
        text = str(item).strip()
        if text and text not in choices:
            choices.append(text)
    if "REPORT" not in choices:
        choices.insert(0, "REPORT")
    # If caller provided a current value not in the predefined list,
    # keep it selectable (insert at front) so editors don't lose unknown texts.
    if current_value is not None and current_value not in choices:
        choices.insert(0, current_value)
    return choices

# Anchor date for Plotly's date-based x-axis (we show MM:SS ticks)
BASE_DT = datetime(2000, 1, 1)

# ── Visual constants ──────────────────────────────────────────────────────────
SECTION_BG = {
    "AUTO":       "rgba(46,204,113,0.13)",
    "UNRELIABLE": "rgba(243,156,18,0.17)",
    "MANUAL":     "rgba(149,165,166,0.13)",
}
SECTION_FG = {
    "AUTO":       "rgba(46,204,113,0.8)",
    "UNRELIABLE": "rgba(243,156,18,0.8)",
    "MANUAL":     "rgba(149,165,166,0.8)",
}
# Event colors by type only — mode is shown via section background, not event color
TYPE_COLOR: dict[str, str] = {
    "sysmon": "#27ae60",
    "comms":  "#2980b9",
    "report": "#9b59b6",
    "pause":  "#e67e22",
}
SELECTED_COLOR = "#f1c40f"  # bright yellow for selected event

# Track order top→bottom in the figure
# (px.timeline y-axis is bottom→top, so we reverse for category_orders)
TRACKS_TOP_DOWN = ["Visual", "Pause", "Sysmon", "Comms", "Report"]
TRACKS_BOTTOM_UP = list(reversed(TRACKS_TOP_DOWN))

GAUGES = ["scales-1", "scales-2", "scales-3", "scales-4", "lights-1", "lights-2"]
SIDE_OPTIONS = ["-1 (left)", "0 (center)", "1 (right)"]
SIDE_MAP = {"-1 (left)": "-1", "0 (center)": "0", "1 (right)": "1"}
SIDE_REVERSE = {"-1": 0, "0": 1, "1": 2}

DEFAULT_CFG = dict(
    alerttimeout=7.0, maxresponsedelay=14.0, audio_dur=11.0, report_dur=7.0,
    fill_opacity=0.78, show_start_bar=False, show_end_bar=False,
)

# ── Time helpers ──────────────────────────────────────────────────────────────

def hms_to_sec(s: str) -> int:
    parts = s.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0])


def sec_to_hms(sec) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def dt(sec) -> datetime:
    return BASE_DT + timedelta(seconds=float(sec))

# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_file(path: Path) -> list[dict]:
    """Read a scenario .txt and return a list of event dicts."""
    events: list[dict] = []
    idx = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            events.append({"_idx": idx, "_type": "comment", "_raw": raw})
            idx += 1
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:
            continue
        try:
            time_sec = hms_to_sec(parts[0])
        except Exception:
            continue
        events.append({
            "_idx":     idx,
            "_type":    "event",
            "time_sec": time_sec,
            "plugin":   parts[1].lower(),
            "command":  parts[2] if len(parts) > 2 else "",
            "value":    parts[3] if len(parts) > 3 else None,
        })
        idx += 1
    return events


def events_to_text(events: list[dict]) -> str:
    """Serialize event list back to scenario file text (sorted by time)."""
    ev = sorted(
        [e for e in events if e.get("_type") == "event"],
        key=lambda x: x["time_sec"],
    )
    lines = ["# Generated by OpenMATB Scenario Editor"]
    for e in ev:
        parts = [sec_to_hms(e["time_sec"]), e["plugin"], e["command"]]
        if e.get("value") is not None:
            parts.append(str(e["value"]))
        lines.append(";".join(parts))
    return "\n".join(lines) + "\n"


def next_idx(events: list[dict]) -> int:
    return max((e["_idx"] for e in events), default=-1) + 1

# ── Automation section detection ──────────────────────────────────────────────

def compute_sections(events: list[dict]) -> list[dict]:
    """
    Scan automaticsolver / automationlabel events and return a list of
    {'start': sec, 'end': sec, 'mode': 'AUTO'|'UNRELIABLE'|'MANUAL'}.
    """
    ev = [e for e in events if e.get("_type") == "event"]
    max_sec = max((e["time_sec"] for e in ev), default=360) + 60

    changes: dict[int, dict] = {}
    for e in ev:
        if e["plugin"] not in ("sysmon", "communications"):
            continue
        t = e["time_sec"]
        if e["command"] == "automaticsolver":
            val = str(e.get("value", "false")).strip().lower()
            changes.setdefault(t, {})["solver"] = val in ("true", "1")
        elif e["command"] == "automationlabel":
            changes.setdefault(t, {})["label"] = str(e.get("value", "")).strip().upper()

    solver, label = False, "MANUAL"
    sections: list[dict] = []
    prev_t = 0

    for t in sorted(changes):
        if t > prev_t:
            sections.append({"start": prev_t, "end": t, "mode": _mode(solver, label)})
        if "solver" in changes[t]:
            solver = changes[t]["solver"]
        if "label" in changes[t]:
            label = changes[t]["label"]
        prev_t = t

    sections.append({"start": prev_t, "end": max_sec, "mode": _mode(solver, label)})
    return sections


def _mode(solver: bool, label: str) -> str:
    if solver:
        return "AUTO"
    if label == "AUTO":
        return "UNRELIABLE"
    return "MANUAL"


def mode_at(sections: list[dict], t: int) -> str:
    for s in sections:
        if s["start"] <= t < s["end"]:
            return s["mode"]
    return sections[-1]["mode"] if sections else "MANUAL"


def default_event_mode_from_section(section_mode: str) -> str:
    """Event defaults: MANUAL in manual windows, AUTO otherwise."""
    return "MANUAL" if section_mode == "MANUAL" else "AUTO"


def event_mode_for_event(e: dict, sections: list[dict]) -> str:
    """Effective per-event mode with optional event-level override."""
    override = str(e.get("mode_override", "")).strip().upper()
    if override in ("AUTO", "MANUAL"):
        return override
    return default_event_mode_from_section(mode_at(sections, e["time_sec"]))

# ── Event classification ──────────────────────────────────────────────────────

def classify(e: dict) -> str | None:
    """Return 'sysmon' | 'comms' | 'report' | 'pause' | None."""
    if e.get("_type") != "event":
        return None
    p, cmd = e["plugin"], e["command"]
    v = str(e.get("value") or "").strip().lower()
    if cmd == "pause":
        return "pause"
    if p == "sysmon" and "failure" in cmd and v in ("true", "1"):
        return "sysmon"
    if p == "communications" and cmd == "radioprompt":
        return "comms"
    # Any sysmon 'report' command should be treated as a report event,
    # whether it carries a text value or not.
    if p == "sysmon" and cmd == "report":
        return "report"
    return None


def gauge_of(cmd: str) -> str:
    """'scales-1-failure' → 'scales-1'"""
    return cmd.rsplit("-", 1)[0] if "-failure" in cmd else cmd


def ev_label(e: dict, kind: str) -> str:
    if kind == "sysmon":
        g = gauge_of(e["command"])
        pfx = "Scale" if "scales" in g else "Light"
        num = g.split("-")[-1]
        return f"{pfx} {num}"
    if kind == "comms":
        return f"Comm / {e.get('value', '?')}"
    if kind == "pause":
        task = e.get("plugin", "?").capitalize()
        action = "Pause" if str(e.get("value", "")).lower() in ("true", "1") else "Resume"
        return f"{action} {task}"
    return "Report"


def ev_duration(kind: str, cfg: dict) -> float:
    if kind == "sysmon":
        return cfg["alerttimeout"]
    if kind == "comms":
        return cfg["audio_dur"] + cfg["maxresponsedelay"]
    if kind == "pause":
        return 1.0  # Show pause events as 1 second on timeline
    return cfg["report_dur"]


def ev_color(kind: str, selected: bool) -> str:
    if selected:
        return SELECTED_COLOR
    return TYPE_COLOR.get(kind, "#95a5a6")

# ── Figure builder ────────────────────────────────────────────────────────────

def build_figure(
    events: list[dict],
    sections: list[dict],
    cfg: dict,
    selected_idx: int | None,
) -> go.Figure:
    ev_only = [e for e in events if e.get("_type") == "event"]
    max_sec = max((e["time_sec"] for e in ev_only), default=360)

    # Build a map of pause durations: for each pause event, find matching resume
    pause_durations = {}  # key: (task, pause_time) -> duration in seconds
    for e in ev_only:
        if classify(e) == "pause":
            task = e["plugin"]
            is_pause = str(e.get("value", "")).lower() in ("true", "1")
            if is_pause:
                # Find matching resume event
                for future_e in ev_only:
                    if (classify(future_e) == "pause" 
                        and future_e["plugin"] == task
                        and future_e["time_sec"] > e["time_sec"]
                        and str(future_e.get("value", "")).lower() in ("false", "0")):
                        pause_durations[(task, e["time_sec"])] = future_e["time_sec"] - e["time_sec"]
                        break

    rows: list[dict] = []
    # Also collect positions for optional start/end markers
    start_xs: list = []; start_ys: list = []; start_cs: list = []
    end_xs:   list = []; end_ys:   list = []; end_cs:   list = []

    for e in ev_only:
        kind = classify(e)
        if kind is None:
            continue
        mode = event_mode_for_event(e, sections)
        
        # Special handling for pause events: use calculated duration or default
        if kind == "pause":
            is_pause = str(e.get("value", "")).lower() in ("true", "1")
            if is_pause:  # Only show pause events, skip resume
                dur = pause_durations.get((e["plugin"], e["time_sec"]), 60.0)  # default 60s
            else:
                continue  # Skip resume events
        else:
            dur = ev_duration(kind, cfg)
        
        sel  = e["_idx"] == selected_idx
        col  = ev_color(kind, sel)
        lbl  = ev_label(e, kind)
        if kind == "pause":
            edit_track = "Pause"
        else:
            edit_track = {"sysmon": "Sysmon", "comms": "Comms", "report": "Report"}[kind]
        dur_clamped = max(dur, 0.5)

        # For pause events, only show on Pause track (not Visual)
        tracks_to_show = ("Pause",) if kind == "pause" else ("Visual", edit_track)
        
        for track in tracks_to_show:
            rows.append({
                "Track":  track,
                "Start":  dt(e["time_sec"]),
                "Finish": dt(e["time_sec"] + dur_clamped),
                "Color":  col,
                "Label":  lbl,
                "idx":    e["_idx"],
                "Mode":   mode,
                "Kind":   kind,
                "Time":   sec_to_hms(e["time_sec"]),
                "Dur":    f"{dur:.0f}s",
            })
            # Don't add start/end markers for pause events
            if kind != "pause":
                start_xs.append(dt(e["time_sec"]))
                start_ys.append(track)
                start_cs.append(col)
                end_xs.append(dt(e["time_sec"] + dur_clamped))
                end_ys.append(track)
                end_cs.append(col)

    if not rows:
        fig = go.Figure()
        fig.update_layout(
            height=320, paper_bgcolor="#0f0f1a",
            plot_bgcolor="#0f0f1a", font_color="#aaa",
            annotations=[dict(text="No displayable events in this file.",
                              x=0.5, y=0.5, showarrow=False,
                              font=dict(size=16, color="#666"))],
        )
        return fig

    df = pd.DataFrame(rows)

    fig = px.timeline(
        df,
        x_start="Start", x_end="Finish",
        y="Track", color="Color",
        color_discrete_map="identity",
        custom_data=["idx", "Label", "Mode", "Kind", "Time", "Dur"],
        hover_name="Label",
        hover_data={
            "Color": False, "Track": False, "Start": False, "Finish": False,
            "idx": False, "Kind": False, "Label": False,
            "Mode": True, "Time": True, "Dur": True,
        },
        category_orders={"Track": TRACKS_BOTTOM_UP},
    )

    # Apply fill opacity — controlled by sidebar slider
    fill_opacity = cfg.get("fill_opacity", 0.78)
    fig.update_traces(
        marker_opacity=fill_opacity,
        marker_line_color="rgba(255,255,255,0.45)",
        marker_line_width=1.8,
        selector=dict(type="bar"),
    )

    # Automation background bands
    for s in sections:
        if s["end"] <= 0:
            continue
        fig.add_vrect(
            x0=dt(max(0, s["start"])),
            x1=dt(min(s["end"], max_sec + 30)),
            fillcolor=SECTION_BG[s["mode"]],
            opacity=1, layer="below", line_width=0,
            annotation_text=s["mode"],
            annotation_position="top left",
            annotation_font_color=SECTION_FG[s["mode"]],
            annotation_font_size=9,
        )

    # Optional start / end vertical bar markers
    marker_kw = dict(symbol="line-ns", size=36, line=dict(width=3))
    if cfg.get("show_start_bar") and start_xs:
        fig.add_trace(go.Scatter(
            x=start_xs, y=start_ys, mode="markers",
            marker={**marker_kw, "color": start_cs,
                    "line": {"width": 3, "color": start_cs}},
            showlegend=False, hoverinfo="skip",
        ))
    if cfg.get("show_end_bar") and end_xs:
        fig.add_trace(go.Scatter(
            x=end_xs, y=end_ys, mode="markers",
            marker={**marker_kw, "color": end_cs,
                    "line": {"width": 3, "color": end_cs}},
            showlegend=False, hoverinfo="skip",
        ))

    # Horizontal separator between Visual and editing lanes
    fig.add_hline(
        y=2.5,
        line_color="rgba(255,255,255,0.15)", line_width=1, line_dash="dot",
    )

    # Set smart tick spacing based on scenario duration
    if max_sec <= 120:
        tick_step = 15  # Every 15 seconds for short scenarios
    elif max_sec <= 300:
        tick_step = 30  # Every 30 seconds for medium scenarios
    else:
        tick_step = 60  # Every 60 seconds for long scenarios
    
    tick_vals = [dt(t) for t in range(0, int(max_sec) + tick_step, tick_step)]
    tick_text = [sec_to_hms(t) for t in range(0, int(max_sec) + tick_step, tick_step)]

    fig.update_xaxes(
        tickvals=tick_vals, 
        ticktext=tick_text, 
        title=dict(text="Time (MM:SS)", font=dict(size=11, color="#888")),
        gridcolor="rgba(255,255,255,0.07)", 
        zeroline=False,
        range=[dt(-3), dt(max_sec + 10)],
        tickfont=dict(size=10),
    )
    fig.update_yaxes(
        title="", gridcolor="rgba(255,255,255,0.07)",
        tickfont=dict(size=12, color="#ccc"),
    )
    fig.update_layout(
        height=340,
        margin=dict(l=5, r=10, t=15, b=30),
        paper_bgcolor="#0f0f1a",
        plot_bgcolor="#0f0f1a",
        font_color="#ddd",
        showlegend=False,
        clickmode="event+select",
    )
    return fig

# ── Detail editor ─────────────────────────────────────────────────────────────

def detail_editor(events: list[dict], sel_idx: int, cfg: dict) -> list[dict] | None:
    """
    Render the detail editor for the selected event.
    Returns a new events list if changes were made, else None.
    """
    e = next((x for x in events if x["_idx"] == sel_idx), None)
    if e is None:
        return None
    kind = classify(e)
    if kind is None:
        return None

    lbl   = ev_label(e, kind)
    sections = compute_sections(events)
    mode  = event_mode_for_event(e, sections)
    color = ev_color(kind, False)

    mode_badge_bg = {"AUTO": "rgba(46,204,113,0.18)", "UNRELIABLE": "rgba(243,156,18,0.22)",
                     "MANUAL": "rgba(149,165,166,0.18)"}
    mode_badge_fg = SECTION_FG[mode]

    st.markdown(
        f'<div style="border-left:4px solid {color}; padding:6px 12px; '
        f'background:rgba(255,255,255,0.04); border-radius:4px; display:flex; '
        f'align-items:center; gap:12px;">'
        f'<b style="font-size:1.05em">✏️ {lbl}</b>'
        f'<span style="font-size:0.82em; color:#aaa">{sec_to_hms(e["time_sec"])} · {kind}</span>'
        f'<span style="background:{mode_badge_bg[mode]};color:{mode_badge_fg};'
        f'padding:1px 8px;border-radius:10px;font-size:0.78em">{mode}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ── Row 1: event-specific fields ──────────────────────────────────────────
    col_t, col_a, col_b, col_del = st.columns([2, 3, 2, 1])

    with col_t:
        new_time = st.text_input(
            "Time (H:MM:SS)", value=sec_to_hms(e["time_sec"]),
            key=f"ed_time_{sel_idx}",
        )

    result = copy.deepcopy(events)
    target = next(x for x in result if x["_idx"] == sel_idx)

    if kind == "sysmon":
        current_gauge = gauge_of(e["command"])
        gauge_idx = GAUGES.index(current_gauge) if current_gauge in GAUGES else 0
        with col_a:
            new_gauge = st.selectbox("Gauge", GAUGES, index=gauge_idx, key=f"ed_gauge_{sel_idx}")
        if "scales" in new_gauge:
            side_ev = next(
                (x for x in events
                 if x.get("_type") == "event"
                 and x["plugin"] == "sysmon"
                 and x["command"] == f"{current_gauge}-side"
                 and x["time_sec"] == e["time_sec"]),
                None,
            )
            cur_side_val = str(side_ev["value"]) if side_ev else "-1"
            cur_side_idx = SIDE_REVERSE.get(cur_side_val, 0)
            with col_b:
                side_sel = st.selectbox(
                    "Side", SIDE_OPTIONS, index=cur_side_idx, key=f"ed_side_{sel_idx}",
                )
            new_side = SIDE_MAP[side_sel]
        else:
            new_side = None

    elif kind == "comms":
        cur_type = str(e.get("value", "own")).lower()
        with col_a:
            new_ptype = st.selectbox(
                "Prompt type", ["own", "other"],
                index=0 if cur_type == "own" else 1,
                key=f"ed_ptype_{sel_idx}",
            )

    elif kind == "report":
        cur_val = str(e.get("value") or "")
        reports = get_report_choices(cur_val)
        if "Custom..." not in reports:
            reports.append("Custom...")
        if cur_val in reports:
            cur_idx = reports.index(cur_val)
        elif cur_val:
            cur_idx = reports.index("Custom...")
        else:
            cur_idx = reports.index("REPORT") if "REPORT" in reports else 0
        with col_a:
            new_report = st.selectbox("Report text", reports, index=cur_idx, key=f"ed_report_{sel_idx}")
        with col_b:
            if new_report == "Custom...":
                custom_report = col_b.text_input("Custom report text", value=(cur_val if cur_val not in reports else ""), key=f"ed_report_custom_{sel_idx}")
            else:
                custom_report = ""

    with col_t:
        apply  = st.button("✔ Apply", key=f"ed_apply_{sel_idx}",  type="primary",  use_container_width=True)
    with col_del:
        delete = st.button("🗑",       key=f"ed_delete_{sel_idx}", type="secondary", use_container_width=True)

    # ── Row 2: event mode override ─────────────────────────────────────────────
    st.markdown(
        '<div style="margin-top:6px; padding:6px 10px; background:rgba(255,255,255,0.03); '
        'border-radius:4px; border:1px solid rgba(255,255,255,0.07);">'
        '<span style="font-size:0.8em; color:#888;">🤖 Event mode override</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    ov_c1, ov_c2, ov_c3, ov_c4 = st.columns([2, 3, 2, 2])
    section_mode = mode_at(sections, e["time_sec"])
    default_mode = default_event_mode_from_section(section_mode)
    is_overridden = str(e.get("mode_override", "")).strip().upper() in EVENT_MODES
    ov_c1.markdown(
        f'<div style="padding-top:8px;font-size:0.82em;color:#aaa">'
        f'Default: <b>{default_mode}</b> ({section_mode} window)<br>'
        f'Current: <b style="color:{mode_badge_fg}">{mode}</b></div>',
        unsafe_allow_html=True,
    )
    new_mode_ov = ov_c2.selectbox(
        "Event mode", EVENT_MODES,
        index=EVENT_MODES.index(mode) if mode in EVENT_MODES else EVENT_MODES.index(default_mode),
        key=f"ed_mode_{sel_idx}",
        label_visibility="collapsed",
    )
    apply_mode = ov_c3.button(
        "Apply override", key=f"ed_mode_apply_{sel_idx}",
        use_container_width=True,
        help="Sets this event to AUTO or MANUAL only",
    )
    clear_mode = ov_c4.button(
        "Clear override", key=f"ed_mode_clear_{sel_idx}",
        use_container_width=True,
        disabled=not is_overridden,
        help="Revert this event to section-default mode",
    )

    # ── Handlers ──────────────────────────────────────────────────────────────
    if apply:
        try:
            new_t = hms_to_sec(new_time)
        except Exception:
            st.error("Invalid time — use H:MM:SS")
            return None

        target["time_sec"] = new_t

        if kind == "sysmon":
            old_gauge = gauge_of(e["command"])
            target["command"] = f"{new_gauge}-failure"
            target["value"]   = "True"
            if "scales" in new_gauge:
                side_ev_result = next(
                    (x for x in result
                     if x.get("_type") == "event"
                     and x["plugin"] == "sysmon"
                     and x["command"] == f"{old_gauge}-side"),
                    None,
                )
                if side_ev_result:
                    side_ev_result["time_sec"] = new_t
                    side_ev_result["command"]  = f"{new_gauge}-side"
                    side_ev_result["value"]    = new_side
                else:
                    result.append({
                        "_idx": next_idx(result), "_type": "event",
                        "time_sec": new_t, "plugin": "sysmon",
                        "command": f"{new_gauge}-side", "value": new_side,
                    })
            else:
                result = [
                    x for x in result
                    if not (
                        x.get("_type") == "event"
                        and x["plugin"] == "sysmon"
                        and x["command"] == f"{old_gauge}-side"
                        and x["time_sec"] == e["time_sec"]
                    )
                ]

        elif kind == "comms":
            target["value"] = new_ptype
        elif kind == "report":
            # If user entered custom text, prefer it; otherwise use selected choice
            if 'custom_report' in locals() and custom_report and str(custom_report).strip():
                target["value"] = str(custom_report).strip()
            else:
                target["value"] = new_report if new_report != "Custom..." else "REPORT"

        return result

    if delete:
        result = [x for x in result if x["_idx"] != sel_idx]
        if kind == "sysmon":
            g = gauge_of(e["command"])
            if "scales" in g:
                result = [
                    x for x in result
                    if not (
                        x.get("_type") == "event"
                        and x["plugin"] == "sysmon"
                        and x["command"] == f"{g}-side"
                        and x["time_sec"] == e["time_sec"]
                    )
                ]
        st.session_state.selected_idx = None
        return result

    if apply_mode:
        result = copy.deepcopy(events)
        target = next((x for x in result if x.get("_idx") == sel_idx), None)
        if target is None:
            return None
        target["mode_override"] = new_mode_ov
        return result

    if clear_mode:
        result = copy.deepcopy(events)
        target = next((x for x in result if x.get("_idx") == sel_idx), None)
        if target is None:
            return None
        target.pop("mode_override", None)
        return result

    return None

# ── Task pause form ───────────────────────────────────────────────────────────

def add_pause_form(events: list[dict]) -> list[dict] | None:
    """
    Form to pause/unpause individual tasks (track, sysmon, communications).
    Creates events like: 0:02:00;track;pause;True
    """
    with st.form(key="add_pause", clear_on_submit=True):
        st.markdown(
            '<div style="padding-bottom:8px; font-size:0.9em; color:#aaa">'
            '<b>⏸️ Pause or Resume a Task</b></div>',
            unsafe_allow_html=True,
        )
        
        time_str = st.text_input(
            "Start time (H:MM:SS)",
            value="0:02:00",
            help="When the pause/resume should occur",
        )
        
        task = st.selectbox(
            "Select task",
            ["track", "sysmon", "communications"],
            help="Which task to pause or resume",
        )
        
        action = st.radio(
            "Action",
            ["Pause", "Resume"],
            horizontal=True,
            help="Pause stops the task, Resume starts it again",
        )
        
        duration_str = st.text_input(
            "Duration (seconds) — optional",
            value="",
            placeholder="e.g., 60 or 120",
            help="If set, automatically creates a resume event after this many seconds",
        )
        
        st.markdown(
            '<div style="font-size:0.75em; color:#666; padding-top:4px;margin-bottom:8px">'
            '💡 Tip: Set a duration to automatically resume — creates both pause and resume events'
            '</div>',
            unsafe_allow_html=True,
        )
        
        submitted = st.form_submit_button("➕ Add pause/resume", type="primary", use_container_width=True)
        if not submitted:
            return None

        try:
            start_t = hms_to_sec(time_str)
        except Exception:
            st.error("Bad start time — use H:MM:SS")
            return None

        result = copy.deepcopy(events)
        nidx = next_idx(result)
        
        # Add pause/resume event
        pause_value = "True" if action == "Pause" else "False"
        result.append({
            "_idx": nidx, "_type": "event",
            "time_sec": start_t, "plugin": task,
            "command": "pause", "value": pause_value,
        })
        
        # If duration specified, add resume event
        if duration_str.strip():
            try:
                duration = float(duration_str.strip())
                resume_t = start_t + duration
                result.append({
                    "_idx": nidx + 1, "_type": "event",
                    "time_sec": resume_t, "plugin": task,
                    "command": "pause", "value": "False",
                })
            except ValueError:
                st.error("Invalid duration — use a number in seconds")
                return None

        return result

# ── Add-event forms ───────────────────────────────────────────────────────────

def add_event_form(events: list[dict], kind: str) -> list[dict] | None:
    with st.form(key=f"add_{kind}", clear_on_submit=True):
        cols = st.columns([2, 2, 2])
        time_str = cols[0].text_input("Time (H:MM:SS)", value="0:04:00")

        if kind == "sysmon":
            gauge    = cols[1].selectbox("Gauge", GAUGES)
            side_sel = cols[2].selectbox("Side (scales)", SIDE_OPTIONS)
            side_val = SIDE_MAP[side_sel]
        elif kind == "comms":
            ptype = cols[1].selectbox("Type", ["own", "other"])
        elif kind == "report":
                # Let user pick a predefined report text from includes/report_options.json
                reports = get_report_choices()
                # Offer a Custom option and an adjacent text field to type free text
                if "Custom..." not in reports:
                    reports.append("Custom...")
                rpt_idx = reports.index("REPORT") if "REPORT" in reports else 0
                # Use middle column for the dropdown
                report_sel = cols[1].selectbox("Report text", reports, index=rpt_idx, key="add_report_sel")
                if report_sel == "Custom...":
                    report_text = cols[2].text_input("Custom report text", value="", key="add_report_custom")
                else:
                    report_text = str(report_sel)

        submitted = st.form_submit_button(f"➕ Add {kind}")
        if not submitted:
            return None

        try:
            t = hms_to_sec(time_str)
        except Exception:
            st.error("Bad time — use H:MM:SS")
            return None

        result = copy.deepcopy(events)
        nidx   = next_idx(result)

        if kind == "sysmon":
            result.append({
                "_idx": nidx, "_type": "event",
                "time_sec": t, "plugin": "sysmon",
                "command": f"{gauge}-failure", "value": "True",
            })
            if "scales" in gauge:
                result.append({
                    "_idx": nidx + 1, "_type": "event",
                    "time_sec": t, "plugin": "sysmon",
                    "command": f"{gauge}-side", "value": side_val,
                })
        elif kind == "comms":
            result.append({
                "_idx": nidx, "_type": "event",
                "time_sec": t, "plugin": "communications",
                "command": "radioprompt", "value": ptype,
            })
        elif kind == "report":
            result.append({
                "_idx": nidx, "_type": "event",
                "time_sec": t, "plugin": "sysmon",
                "command": "report", "value": str(report_text),
            })

        return result

# ── Automation section manager ────────────────────────────────────────────────

MODES = ["AUTO", "UNRELIABLE", "MANUAL"]
EVENT_MODES = ["AUTO", "MANUAL"]
MODE_COLORS = {"AUTO": "#27ae60", "UNRELIABLE": "#e67e22", "MANUAL": "#95a5a6"}


def _build_transitions(events: list[dict]) -> list[dict]:
    """
    Return sorted list of transition dicts:
      {'time': int, 'mode': str, 'implicit': bool}

    An 'implicit' row at t=0 means the scenario starts MANUAL with no explicit
    events — shown as editable but its time is locked to 0.
    """
    changes: dict[int, dict] = {}
    for e in events:
        if e.get("_type") != "event":
            continue
        if e["plugin"] not in ("sysmon", "communications"):
            continue
        t = e["time_sec"]
        if e["command"] == "automaticsolver":
            changes.setdefault(t, {})["solver"] = (
                str(e.get("value", "false")).strip().lower() in ("true", "1")
            )
        elif e["command"] == "automationlabel":
            changes.setdefault(t, {})["label"] = str(e.get("value", "")).strip().upper()

    solver, label = False, "MANUAL"
    transitions: list[dict] = []
    for t in sorted(changes):
        if "solver" in changes[t]:
            solver = changes[t]["solver"]
        if "label" in changes[t]:
            label = changes[t]["label"]
        transitions.append({"time": t, "mode": _mode(solver, label), "implicit": False})

    # Always show a row for the initial state
    if not transitions or transitions[0]["time"] > 0:
        transitions.insert(0, {"time": 0, "mode": "MANUAL", "implicit": True})

    return transitions


def _apply_transition(events: list[dict], old_t: int, new_t: int, mode: str) -> list[dict]:
    """Remove old transition events and insert new ones."""
    result = [
        e for e in events
        if not (
            e.get("_type") == "event"
            and e["plugin"] in ("sysmon", "communications")
            and e["command"] in ("automaticsolver", "automationlabel")
            and e["time_sec"] == old_t
        )
    ]
    nidx      = next_idx(result)
    solver_v  = "True"  if mode == "AUTO"       else "False"
    label_v   = "AUTO"  if mode != "MANUAL"     else "MANUAL"
    for plugin in ("sysmon", "communications"):
        result.append({"_idx": nidx,     "_type": "event", "time_sec": new_t,
                        "plugin": plugin, "command": "automaticsolver", "value": solver_v})
        result.append({"_idx": nidx + 1, "_type": "event", "time_sec": new_t,
                        "plugin": plugin, "command": "automationlabel",  "value": label_v})
        nidx += 2
    return result


def _delete_transition(events: list[dict], t: int) -> list[dict]:
    return [
        e for e in events
        if not (
            e.get("_type") == "event"
            and e["plugin"] in ("sysmon", "communications")
            and e["command"] in ("automaticsolver", "automationlabel")
            and e["time_sec"] == t
        )
    ]


def section_manager_ui(events: list[dict]) -> list[dict] | None:
    """
    Editable table of automation transition rows.
    Each row: [time input] [mode pill/dropdown] [✔ Update] [🗑 Delete]
    Returns updated events list if anything changed, else None.
    """
    transitions = _build_transitions(events)

    # Column headers
    h0, h1, h2, h3 = st.columns([2, 3, 1, 1])
    h0.markdown("<span style='color:#888;font-size:0.8em'>START TIME</span>",
                unsafe_allow_html=True)
    h1.markdown("<span style='color:#888;font-size:0.8em'>MODE</span>",
                unsafe_allow_html=True)

    result = None

    for i, tr in enumerate(transitions):
        is_implicit = tr["implicit"]
        key         = f"sec_{i}_{tr['time']}"

        c_time, c_mode, c_upd, c_del = st.columns([2, 3, 1, 1])

        new_time_str = c_time.text_input(
            "time", value=sec_to_hms(tr["time"]),
            key=f"{key}_t",
            disabled=is_implicit,
            label_visibility="collapsed",
        )
        new_mode = c_mode.selectbox(
            "mode", MODES,
            index=MODES.index(tr["mode"]),
            key=f"{key}_m",
            label_visibility="collapsed",
        )

        col = MODE_COLORS[tr["mode"]]
        c_mode.markdown(
            f'<div style="height:2px;background:{col};border-radius:1px;margin-top:-6px"></div>',
            unsafe_allow_html=True,
        )

        upd = c_upd.button("✔", key=f"{key}_upd", help="Apply", use_container_width=True)
        can_delete = not is_implicit and len(transitions) > 1
        dlt = c_del.button("🗑", key=f"{key}_del", help="Delete",
                           use_container_width=True, disabled=not can_delete)

        if upd:
            try:
                new_t = 0 if is_implicit else hms_to_sec(new_time_str)
            except Exception:
                st.error("Bad time — use H:MM:SS")
                return None
            result = _apply_transition(copy.deepcopy(events), tr["time"], new_t, new_mode)
            break

        if dlt and can_delete:
            result = _delete_transition(copy.deepcopy(events), tr["time"])
            break

    # Compact inline row to add a brand-new transition
    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.07);margin:6px 0">',
        unsafe_allow_html=True,
    )
    ca, cb, cc, _ = st.columns([2, 3, 1, 1])
    ca.markdown("<span style='color:#555;font-size:0.78em'>new</span>",
                unsafe_allow_html=True)
    add_t    = ca.text_input("new_t", value="0:02:00", key="sec_new_t",
                             label_visibility="collapsed")
    add_mode = cb.selectbox("new_m", MODES, key="sec_new_m",
                            label_visibility="collapsed")
    if cc.button("➕", key="sec_new_add", use_container_width=True, help="Add transition"):
        try:
            t = hms_to_sec(add_t)
            result = _apply_transition(copy.deepcopy(events), t, t, add_mode)
        except Exception:
            st.error("Bad time — use H:MM:SS")

    return result

# ── Main app ──────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="OpenMATB Scenario Editor",
        page_icon="✈️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Dark theme polish
    st.markdown("""
    <style>
    html, body, .stApp { background-color: #0f0f1a; color: #dde; }
    .block-container { padding-top: 0.8rem; padding-bottom: 1rem; }
    h1 { color: #a0c4ff; letter-spacing: 1px; }
    h3 { color: #c8d8ff; }
    .stExpander { background: rgba(255,255,255,0.03); border-radius: 6px; }
    div[data-testid="stForm"] { background: rgba(255,255,255,0.03); border-radius: 8px; padding: 8px; }
    </style>
    """, unsafe_allow_html=True)

    # ── Session state defaults ─────────────────────────────────────────────────
    if "events"       not in st.session_state: st.session_state.events       = []
    if "filepath"     not in st.session_state: st.session_state.filepath     = None
    if "selected_idx" not in st.session_state: st.session_state.selected_idx = None
    if "cfg"          not in st.session_state: st.session_state.cfg          = copy.copy(DEFAULT_CFG)

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ✈️ MATB Editor")
        st.markdown("---")

        scenario_files = sorted(SCENARIOS_DIR.glob("*.txt"))
        file_names     = [f.name for f in scenario_files]

        if not file_names:
            st.error("No .txt files found in includes/scenarios/")
            return

        chosen = st.selectbox("Scenario file", file_names)
        if st.button("📂 Load", type="primary", use_container_width=True):
            st.session_state.events       = parse_file(SCENARIOS_DIR / chosen)
            st.session_state.filepath     = SCENARIOS_DIR / chosen
            st.session_state.selected_idx = None
            st.rerun()

        # Auto-load on first run
        if not st.session_state.events and file_names:
            st.session_state.events   = parse_file(SCENARIOS_DIR / file_names[0])
            st.session_state.filepath = SCENARIOS_DIR / file_names[0]

        st.markdown("---")
        st.markdown("**Event display widths** *(visual only)*")
        cfg = st.session_state.cfg
        cfg["alerttimeout"]     = st.number_input("Sysmon timeout (s)",      value=cfg["alerttimeout"],     step=0.5, min_value=0.5)
        cfg["maxresponsedelay"] = st.number_input("Comm response window (s)", value=cfg["maxresponsedelay"], step=0.5, min_value=0.5)
        cfg["audio_dur"]        = st.number_input("Audio duration (s)",       value=cfg["audio_dur"],        step=0.5, min_value=0.5)
        cfg["report_dur"]       = st.number_input("Report duration (s)",      value=cfg["report_dur"],       step=0.5, min_value=0.5)

        st.markdown("---")
        st.markdown("**Visualization**")
        fill_pct = st.slider("Fill opacity", 0, 100, 78, 5, key="viz_fill")
        cfg["fill_opacity"]    = fill_pct / 100.0
        cfg["show_start_bar"]  = st.checkbox("Start bar", value=False, key="viz_start")
        cfg["show_end_bar"]    = st.checkbox("End bar",   value=False, key="viz_end")

        st.markdown("---")
        st.markdown("**Legend**")
        st.markdown(
            '<div style="font-size:0.85em; line-height:2.0">'
            '<span style="color:#27ae60">█</span> Sysmon<br>'
            '<span style="color:#2980b9">█</span> Comm<br>'
            '<span style="color:#9b59b6">█</span> Report<br>'
            '<span style="color:#e67e22">█</span> Pause/Resume<br>'
            '<span style="color:#f1c40f">█</span> Selected<br>'
            '<br>'
            '<span style="background:rgba(46,204,113,0.25);padding:1px 5px;border-radius:3px">'
            '&nbsp;AUTO&nbsp;</span><br>'
            '<span style="background:rgba(243,156,18,0.3);padding:1px 5px;border-radius:3px">'
            '&nbsp;UNRELIABLE&nbsp;</span><br>'
            '<span style="background:rgba(149,165,166,0.25);padding:1px 5px;border-radius:3px">'
            '&nbsp;MANUAL&nbsp;</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("**Save**")
        if st.button("💾 Save", use_container_width=True, type="primary"):
            if st.session_state.filepath:
                st.session_state.filepath.write_text(
                    events_to_text(st.session_state.events), encoding="utf-8"
                )
                st.success(f"Saved → {st.session_state.filepath.name}")

        new_name = st.text_input("Save As (filename, no path needed)")
        if st.button("Save As ▶", use_container_width=True) and new_name.strip():
            fn = new_name.strip()
            if not fn.endswith(".txt"):
                fn += ".txt"
            dest = SCENARIOS_DIR / fn
            dest.write_text(events_to_text(st.session_state.events), encoding="utf-8")
            st.success(f"Saved as {fn}")

    # ── Main area ──────────────────────────────────────────────────────────────
    events   = st.session_state.events
    sel_idx  = st.session_state.selected_idx
    sections = compute_sections(events)

    fp = st.session_state.filepath
    n_ev = len([e for e in events if classify(e)])
    c_title, c_count = st.columns([5, 2])
    c_title.subheader(fp.name if fp else "No file loaded")
    c_count.markdown(
        f"<div style='padding-top:14px; color:#555; font-size:0.82em; text-align:right'>"
        f"{n_ev} displayable events</div>",
        unsafe_allow_html=True,
    )

    # Automation section manager
    with st.expander("🔀 Automation Sections", expanded=True):
        new_ev = section_manager_ui(events)
        if new_ev is not None:
            st.session_state.events = new_ev
            st.rerun()

    # Timeline
    fig = build_figure(events, sections, cfg, sel_idx)
    sel_data = st.plotly_chart(
        fig,
        on_select="rerun",
        key="timeline",
        use_container_width=True,
    )

    # Handle timeline click → select event
    try:
        pts = sel_data.selection.points  # type: ignore[union-attr]
        if pts:
            raw_cd = pts[0].get("customdata")
            if raw_cd:
                new_sel = int(raw_cd[0])
                if new_sel != sel_idx:
                    st.session_state.selected_idx = new_sel
                    st.rerun()
    except Exception:
        pass

    # Clear selection button
    if sel_idx is not None:
        if st.button("✕ Clear selection", key="clear_sel"):
            st.session_state.selected_idx = None
            st.rerun()

    # Add event row
    st.markdown("**Add event**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        with st.expander("➕ Sysmon failure"):
            nev = add_event_form(events, "sysmon")
            if nev is not None:
                st.session_state.events = nev
                st.rerun()
    with c2:
        with st.expander("➕ Comm prompt"):
            nev = add_event_form(events, "comms")
            if nev is not None:
                st.session_state.events = nev
                st.rerun()
    with c3:
        with st.expander("➕ Report"):
            nev = add_event_form(events, "report")
            if nev is not None:
                st.session_state.events = nev
                st.rerun()
    with c4:
        with st.expander("⏸️ Pause/Resume task"):
            nev = add_pause_form(events)
            if nev is not None:
                st.session_state.events = nev
                st.rerun()

    # Detail editor (appears when an event is selected)
    if sel_idx is not None:
        st.markdown("---")
        new_ev = detail_editor(events, sel_idx, cfg)
        if new_ev is not None:
            st.session_state.events = new_ev
            st.rerun()


if __name__ == "__main__":
    main()
