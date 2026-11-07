'''
This program was written by C. Greyston Brady for Anti-Fab Industries LLC on October 16, 2026
If you need to contact her sent an email to <grace@antifab.org>
Copyright © 2026 Anti-Fab Industries, LLC
License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
'''
'''
Based on a similar file by the FreeCAD team called legacy_dynapath_post.py
'''


import os
from dataclasses import dataclass, field, replace
from functools import reduce
from itertools import chain

import FreeCAD
import Path
import Path.Base.Util as PathUtils   # adjust: location of getPathWithPlacement / findParentJob varies by build
from Path.Post.Processor import PostProcessor
import Path.Post.Utils as PostUtils

from builtins import open as pyopen

Path.Log.setLevel(Path.Log.Level.INFO, Path.Log.thisModule())

translate = FreeCAD.Qt.translate

debug = True
if debug:
    Path.Log.setLevel(Path.Log.Level.DEBUG, Path.Log.thisModule())
    Path.Log.trackModule(Path.Log.thisModule())
else:
    Path.Log.setLevel(Path.Log.Level.INFO, Path.Log.thisModule())

translate = FreeCAD.Qt.translate

# class Generic(PostProcessor):
#     def __init__(self, job):
#         super().__init__(
#             job,
#             tooltip=translate("CAM", "Generic post processor"),
#             tooltipargs=["arg1", "arg2"],
#             units="kg",
#         )
#         self.middleware = pipeline(*PASSES)
#         self.linearized = []     # [(partname, [Item])], pre-middleware

#     def export(self):
#         self.linearized = [(name, linearize(ops)) for name, ops in self._buildPostList()]
#         return [(name, emit(self.middleware(items))) for name, items in self.linearized]

    # tooltip, tooltipArgs, units properties: unchanged from the template

# ---- module-level entry point -----------------------------------------------

from dataclasses import dataclass, field
from itertools import count

try:
    import FreeCAD
    from FreeCAD import Units
except ImportError:           # lets you import/test outside FreeCAD
    FreeCAD = Units = None

# ---------- configuration ----------
UNIT_FORMAT = "mm"                    # or "in"
PARAM_ORDER = "XYZABCIJKRQPHDLFST"    # edit to match what Dynapath wants
N_START, N_STEP = 1, 1

LENGTH_WORDS = "XYZIJKRQ"
MOTION = {"G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"}
ARCS = {"G2", "G02", "G3", "G03"}

DRILL_CYCLES = {"G73", "G81", "G82", "G83"}
PECK_CYCLES = {"G73", "G83", "G82"}
NATIVE_DRILL = True                   # False -> expand cycles to G0/G1 moves
PECK_CLEARANCE = 0.5                  # D20 "Q": clearance above previous peck depth

PREAMBLE  = "G17\nG90\nG80\nG40\n"        # ;G90.1 needed for simulation only
POSTAMBLE = "M09\nM05\nG80\nG40\nG17\nG90\nM30\n"
COMMENTS = True                           # emit (begin preamble)/(begin postamble)
UNIT_CODE = {"mm": "G71", "in": "G70"}[UNIT_FORMAT]
PROGRAM_TERMINATOR = "END"                   # paste ctx.program_terminator value here; "" = none

FEED_FORMAT = {"mm": "mm/min", "in": "in/min"}[UNIT_FORMAT]

SUPPRESS = {"G54", "G98", "G99"}      

def to_feed(value):
    q = Units.Quantity(value, FreeCAD.Units.Velocity)
    return float(q.getValueAs(FEED_FORMAT))

def parse_line(line):
    """'G0 X1 Y2' -> Cmd('G0', {'X': 1.0, 'Y': 2.0}); comments pass through."""
    line = line.strip()
    if line.startswith("("):
        return Cmd(line)
    name, *words = line.split()
    return Cmd(name, {w[0]: float(w[1:]) for w in words})

def emit_preamble():
    cmds = []
    cmds += [parse_line(l) for l in PREAMBLE.splitlines()]
    cmds.append(Cmd(UNIT_CODE))
    return cmds

def emit_postamble():
    cmds = []
    cmds += [parse_line(l) for l in POSTAMBLE.splitlines()]
    return cmds

def header_name(filename):
    if filename and filename != "-":
        return filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return "UNTITLED"

# ---------- command object ----------
@dataclass
class Cmd:
    name: str
    parameters: dict = field(default_factory=dict)

    @property
    def is_comment(self):
        return self.name.startswith("(")


# ---------- helpers ----------
def to_units(value):
    q = Units.Quantity(value, FreeCAD.Units.Length)
    return float(q.getValueAs(UNIT_FORMAT))


def new_state():
    return {"position": (0.0, 0.0, 0.0), "absolute": True}


# ---------- stage 0: expansion ----------
def ramp_spindle(cmd, threshold=1000, step=500, dwell=2.0):
    for s in range(threshold, int(cmd.parameters["S"]), step):
        yield Cmd(cmd.name, {"S": s})
        yield Cmd("G4", {"X": dwell})
    yield cmd


def drill_moves(cmd, clearance=0.5):
    """Fallback: expand a canned cycle into plain G0/G1 moves (raw FreeCAD units)."""
    p = cmd.parameters
    z, r, f, q = p["Z"], p["R"], p.get("F"), p.get("Q")
    xy = {k: p[k] for k in "XY" if k in p}
    feed = lambda zz: Cmd("G1", {"Z": zz, **({"F": f} if f else {})})

    yield Cmd("G0", xy)
    yield Cmd("G0", {"Z": r})
    if cmd.name in PECK_CYCLES and q:
        depth = r
        while depth > z + 1e-9:
            depth = max(depth - q, z)
            yield feed(depth)
            if depth > z + 1e-9:
                if cmd.name == "G83":                       # full retract each peck
                    yield Cmd("G0", {"Z": r})
                yield Cmd("G0", {"Z": depth + clearance})   # G73: small chip-break lift
    else:
        yield feed(z)
        if cmd.name == "G82" and "P" in p:                  # dwell at bottom
            yield Cmd("G4", {"P": p["P"]})
    yield Cmd("G0", {"Z": r})

def expand(cmd):
    match cmd:
        case Cmd(name=n) if n in SUPPRESS:
            pass
        case Cmd(name="M3" | "M4", parameters={"S": s}) if s > 2000:
            yield from ramp_spindle(cmd)
        case Cmd(name=n, parameters={"Z": _, "R": _}) if n in DRILL_CYCLES and not NATIVE_DRILL:
            yield from drill_moves(cmd)
        case _:
            yield cmd


# ---------- stage 1: per-gcode logic (stateful) ----------
def remap_drill(name, p):
    p = dict(p)
    if name in PECK_CYCLES:
        if "Q" in p:
            p["K"] = p.pop("Q")        # FreeCAD Q (peck increment) -> D20 K
        p["Q"] = PECK_CLEARANCE        # D20 Q is the clearance, not the peck
        if name == "G82" and "P" in p:
            p["L"] = p.pop("P")
            p.pop("Q")
    return p


def track_drill(params, state):
    pos = list(state["position"])
    for i, ax in enumerate("XY"):
        if ax in params:
            pos[i] = params[ax] if state["absolute"] else pos[i] + params[ax]
    if "R" in params and state["absolute"]:
        pos[2] = params["R"]           # cycle ends retracted at R
    state["position"] = tuple(pos)


def transform_params(name, params, state):
    params = dict(params)

    # convert every length word once, so stage 2 is pure formatting
    for k in LENGTH_WORDS:
        if k in params:
            params[k] = to_units(params[k])

    if "F" in params:
        params["F"] = to_feed(params["F"])

    match name:
        case "G90":
            state["absolute"] = True
        case "G91":
            state["absolute"] = False
        
        case n if n in ARCS:
            # FreeCAD emits IJK as incremental offsets from the arc start;
            # under G90 the D20 reads them as absolute, so add the start position.
            if state["absolute"]:
                for axis, prev in zip("IJK", state["position"]):
                    if axis in params:
                        params[axis] += prev
        case n if n in DRILL_CYCLES and NATIVE_DRILL:
            params = remap_drill(name, params)
            track_drill(params, state)
        case _:
            pass

    # track the endpoint AFTER the arc fix, since the fix needs the start point
    if name in MOTION:
        pos = list(state["position"])
        for i, axis in enumerate("XYZ"):
            if axis in params:
                pos[i] = params[axis] if state["absolute"] else pos[i] + params[axis]
        state["position"] = tuple(pos)

    return params


# ---------- stage 2: per-key formatting + ordering ----------
def fmt_value(key, value):
    match key:
        case "X" | "Y" | "Z" | "I" | "J" | "K" | "R" | "Q":
            return f"{value:.3f}"
        case "F" | "S" | "T" | "H" | "D":
            return f"{value:.0f}"
        case _:
            return str(value)


def order_params(params):
    rank = lambda kv: (PARAM_ORDER.find(kv[0]) if kv[0] in PARAM_ORDER else 99, kv[0])
    return dict(sorted(params.items(), key=rank))


def format_params(params):
    return {k: fmt_value(k, v) for k, v in order_params(params).items()}


# ---------- rendering ----------
def render(n, cmd):
    if cmd.is_comment:
        text = cmd.name.strip("()").strip()
        body = f"(T){text}$"
    else:
        body = "".join([cmd.name, *(f"{k}{v}" for k, v in cmd.parameters.items())])
    return f"N{n:04d}{body}"


# ---------- entry point ----------
def export(objectslist, filename, argstring):
    cmdList = emit_preamble()

    # Construct linear list of commands
    for obj in objectslist:
        cmdList.extend(Cmd(c.Name, dict(c.Parameters)) for c in obj.Path.Commands)

    cmdList.extend(emit_postamble())

    # Stage 0: expand in place
    cmdList[:] = [o for c in cmdList for o in expand(c)]

    # Stages 1 + 2
    state = new_state()
    for cmd in cmdList:
        if cmd.is_comment:
            continue
        cmd.parameters = format_params(transform_params(cmd.name, cmd.parameters, state))

    # Render: unnumbered filename header, numbered body, unnumbered terminator
    lines = [f"({header_name(filename)})"]
    lines += [render(n, c) for n, c in zip(count(N_START, N_STEP), cmdList)]
    if PROGRAM_TERMINATOR:
        lines.append(PROGRAM_TERMINATOR)

    # print to debug
    for line in lines:
        print(line)

        gcode = ""
    gcode = "\n".join(lines) + "\n"

    if FreeCAD.GuiUp:
        dia = PostUtils.GCodeEditorDialog()
        dia.editor.setText(gcode)
        result = dia.exec_()
        if result:
            final = dia.editor.toPlainText()
        else:
            final = gcode
    else:
        final = gcode

    gfile = pyopen(filename, "w")
    gfile.write(final)
    gfile.close()

    return "\n".join(lines) + "\n"