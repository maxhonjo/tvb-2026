"""
The UI talks to the backend through five methods on `LoggerUI`. They are
stubs right now 

  get_os() -> str
      Shown on the OS line. Called once at startup. Return the OS string
      (e.g. "Windows 11", "Ubuntu 24.04"). Return "" / "—" if unknown.

  get_compatibility() -> dict[str, bool]
      Called once at startup. Keys are exactly: "Process", "Key", "Location".
      True  -> switch is active and clickable.
      False -> switch is disabled and the row shows an "unsupported" marker;
               start_logging / stop_logging are NEVER called for that key.
      Example: {"Process": True, "Key": False, "Location": True}

  start_logging(kind: str) -> None
      Called when the user flips a switch ON.
      `kind` is one of "Process", "Key", "Location".

  stop_logging(kind: str) -> None
      Called when the user flips a switch OFF. Same `kind` values.

  open_log() -> None
      Called by the "view log →" link. Open the log file / viewer / window.

───────────────────────────────────────────────────────────────────────────
NOTES
  • The UI owns toggle state and visual feedback. start/stop_logging should
    just do the work; they don't need to report success back. If a logger can
    fail to start, tell UI side and we'll add an error path.
  • Keys are the canonical identifiers everywhere — match them exactly.
═══════════════════════════════════════════════════════════════════════════
"""

import math
import tkinter as tk


# ── Theme ────────────────────────────────────────────────────────────────
BG        = "#0d0e10"   # window background (near-black, faint cool tint)
FG        = "#e8e8ea"   # primary text
MUTED     = "#6e7076"   # secondary text
CARD      = "#17181b"   # row background
ON        = "#4cc38a"   # active accent (calmer, desaturated green)
ON_HOVER  = "#57cf96"
ON_DIM    = "#2c6f52"   # pulse low-point
OFF       = "#3a3b40"   # switch track, inactive
OFF_HOVER = "#484950"
DISABLED  = "#202125"   # switch track, unsupported
KNOB_ON   = "#ffffff"
KNOB_OFF  = "#b7b8bc"
KNOB_DIS  = "#55565c"
DOT_OFF   = "#303136"   # per-row status light, inactive
WARN      = "#c08a4a"   # unsupported marker
FONT      = "TkFixedFont"   # Tk's built-in monospace, present everywhere

# Layout
WIDTH = 400             # fixed width → wider, rectangular window
PAD_X = 22              # side gutter (spacing scale: multiples of ~4)


class Toggle(tk.Canvas):
    """A small pill switch. Calls command(is_on) on click when enabled."""

    W, H = 44, 24

    def __init__(self, master, bg, command, enabled=True):
        super().__init__(master, width=self.W, height=self.H, bg=bg,
                         highlightthickness=0, bd=0)
        self.command = command
        self.enabled = enabled
        self.on = False
        self._hover = False
        self._draw()
        if enabled:
            self.config(cursor="hand2")
            self.bind("<Button-1>", self._click)
            self.bind("<Enter>", lambda e: self._set_hover(True))
            self.bind("<Leave>", lambda e: self._set_hover(False))

    def _pill(self, x0, y0, x1, y1, r, fill):
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=fill, outline=fill)
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=fill, outline=fill)
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)

    def _draw(self):
        self.delete("all")
        r = self.H // 2
        if not self.enabled:
            track, knob = DISABLED, KNOB_DIS
        elif self.on:
            track, knob = (ON_HOVER if self._hover else ON), KNOB_ON
        else:
            track, knob = (OFF_HOVER if self._hover else OFF), KNOB_OFF
        self._pill(1, 1, self.W - 1, self.H - 1, r - 1, track)
        kr, cy = r - 3, self.H // 2
        cx = (self.W - r - 1) if self.on else (r + 1)
        self.create_oval(cx - kr, cy - kr, cx + kr, cy + kr,
                         fill=knob, outline=knob)

    def _set_hover(self, state):
        self._hover = state
        self._draw()

    def _click(self, _event):
        self.on = not self.on
        self._draw()
        if self.command:
            self.command(self.on)

    def set_bg(self, color):
        self.config(bg=color)
        self._draw()


class LoggerUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("logger")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.state    = {"Process": False, "Key": False, "Location": False}
        self.compat   = self.get_compatibility()  # BACKEND: per-feature support
        self.switches = {}
        self.dots     = {}
        self._pulsing = False
        self._build()

    # ── Layout ──────────────────────────────────────────────────────────
    def _build(self):
        os_name = self.get_os()  # BACKEND: provides the OS string
        tk.Label(self, text="OS", fg=MUTED, bg=BG, font=(FONT, 9)).pack(
            anchor="w", padx=PAD_X, pady=(24, 0)
        )
        tk.Label(self, text=os_name, fg=FG, bg=BG, font=(FONT, 15)).pack(
            anchor="w", padx=PAD_X, pady=(2, 20)
        )

        for name in self.state:
            self._row(name)

        link = tk.Button(
            self, text="view log  →", command=self.open_log,
            fg=MUTED, bg=BG, activebackground=BG, activeforeground=FG,
            font=(FONT, 10), relief="flat", bd=0, cursor="hand2",
        )
        link.pack(anchor="w", padx=PAD_X, pady=(20, 24))
        link.bind("<Enter>", lambda e: link.config(fg=FG, font=(FONT, 10, "underline")))
        link.bind("<Leave>", lambda e: link.config(fg=MUTED, font=(FONT, 10)))

        self._refresh_rec()
        # Fixed width, height snapped to content → clean rectangle, no dead space
        self.update_idletasks()
        self.geometry(f"{WIDTH}x{self.winfo_reqheight()}")

    def _row(self, name):
        supported = self.compat.get(name, True)
        row = tk.Frame(self, bg=CARD)
        row.pack(fill="x", padx=PAD_X, pady=2)

        # Independent per-row status light (glows/pulses only for this logger)
        dot = tk.Label(row, text="●", fg=DOT_OFF, bg=CARD, font=(FONT, 11))
        dot.pack(side="left", padx=(14, 0), pady=13)
        self.dots[name] = dot

        tk.Label(
            row, text=name.lower(), fg=FG if supported else MUTED, bg=CARD,
            font=(FONT, 12),
        ).pack(side="left", padx=(8, 0), pady=13)

        sw = Toggle(
            row, bg=CARD, enabled=supported,
            command=lambda on, n=name: self._on_toggle(n, on),
        )
        sw.pack(side="right", padx=14, pady=8)
        self.switches[name] = sw

        if not supported:
            tk.Label(
                row, text="unsupported", fg=WARN, bg=CARD, font=(FONT, 8),
            ).pack(side="right", pady=8)

    # ── Interaction ─────────────────────────────────────────────────────
    def _on_toggle(self, name, on):
        self.state[name] = on
        self._refresh_rec()
        if on:
            self.start_logging(name)   # BACKEND: begin logging `name`
        else:
            self.stop_logging(name)    # BACKEND: stop logging `name`

    def _refresh_rec(self):
        active = any(self.state.values())
        self.title("logger ●" if active else "logger")
        if active and not self._pulsing:
            self._pulsing = True
            self._pulse()
        elif not active:
            self._pulsing = False
            for dot in self.dots.values():
                dot.config(fg=DOT_OFF)

    def _pulse(self, step=0):
        if not self._pulsing:
            return
        col = self._lerp(ON_DIM, ON, (math.sin(step / 8 * math.pi) + 1) / 2)
        for name, dot in self.dots.items():
            dot.config(fg=col if self.state[name] else DOT_OFF)
        self.after(80, lambda: self._pulse(step + 1))

    @staticmethod
    def _lerp(a, b, t):
        ai = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
        bi = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(
            round(ai[k] + (bi[k] - ai[k]) * t) for k in range(3)
        )

    # ── Backend stubs (replace these) ───────────────────────────────────
    def get_os(self):
        # BACKEND: return the OS string from your backend.
        return "—"

    def get_compatibility(self):
        # BACKEND: return {feature: bool} for Process / Key / Location.
        # True → usable on this OS; False → switch disabled + "unsupported".
        return {"Process": True, "Key": True, "Location": True}

    def start_logging(self, kind):
        pass  # BACKEND

    def stop_logging(self, kind):
        pass  # BACKEND

    def open_log(self):
        pass  # BACKEND: open / navigate to the log


if __name__ == "__main__":
    LoggerUI().mainloop()