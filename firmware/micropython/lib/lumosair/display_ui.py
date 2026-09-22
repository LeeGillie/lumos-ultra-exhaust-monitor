"""Screen layout for the box display (320x240 landscape).

Two sources feed it:
  * the node's own channels (always available), and
  * a status broadcast from the PC app (CFM, overall state, fan level, headline),
    which is what makes the box useful at a glance while you're at the laser.

Everything is redrawn only when the value changes, so the SPI traffic stays low.
"""

from . import st7789 as C

_SEV_COLOR = {
    "ok": C.GREEN, "info": C.BLUE, "advice": C.AMBER,
    "warning": C.ORANGE, "critical": C.RED, "stale": C.GREY,
}
_SEV_TEXT = {
    "ok": "ALL GOOD", "info": "INFO", "advice": "ADVICE",
    "warning": "CHECK", "critical": "PROBLEM", "stale": "NO PC LINK",
}


class Screen:
    def __init__(self, tft, node_id):
        self.tft = tft
        self.node_id = node_id
        self._last = {}
        self._rows = []

    # ---------- helpers ----------
    def _changed(self, key, value):
        if self._last.get(key) == value:
            return False
        self._last[key] = value
        return True

    def splash(self, line2=""):
        t = self.tft
        t.fill(C.DARK)
        t.text("LumosAir", 12, 16, C.WHITE, C.DARK, 3)
        t.text(self.node_id + " node", 12, 52, C.BLUE, C.DARK, 2)
        if line2:
            t.text(line2[:34], 12, 86, C.GREY, C.DARK, 1)
        self._last.clear()

    def layout(self):
        """Paint the static furniture once."""
        t = self.tft
        t.fill(C.DARK)
        t.fill_rect(0, 0, t.width, 26, C.PANEL)
        t.text(self.node_id.upper(), 8, 9, C.WHITE, C.PANEL, 1)
        t.fill_rect(0, 116, t.width, 1, C.PANEL)
        t.fill_rect(0, 150, t.width, 1, C.PANEL)
        t.text("AIRFLOW", 10, 34, C.GREY, C.DARK, 1)
        t.text("FAN", 210, 34, C.GREY, C.DARK, 1)
        self._last.clear()

    # ---------- live values ----------
    def status(self, severity, ip=None, rssi=None):
        t = self.tft
        color = _SEV_COLOR.get(severity, C.GREY)
        if self._changed("sev", severity):
            t.fill_rect(0, 0, t.width, 26, color)
            t.text(self.node_id.upper(), 8, 9, C.BLACK, color, 1)
            label = _SEV_TEXT.get(severity, severity.upper())
            t.text(label, t.width - 8 - 8 * len(label), 9, C.BLACK, color, 1)
        if ip and self._changed("ip", ip):
            t.text(ip[-15:], 96, 9, C.BLACK, color, 1)
        if rssi is not None and self._changed("rssi", rssi):
            pass

    def flow(self, cfm, source):
        """Big CFM readout from the PC; shows '--' when there's no link."""
        t = self.tft
        s = "---" if cfm is None else "%3d" % int(round(cfm))
        if self._changed("cfm", s):
            t.seg7(s, 10, 48, digit_w=32, digit_h=56, thick=7,
                   color=C.WHITE if cfm is not None else C.GREY, bg=C.DARK)
        if self._changed("src", source):
            t.text((source or "")[:20], 12, 108, C.GREY, C.DARK, 1)
        if self._changed("cfmunit", True):
            t.text("CFM", 150, 84, C.GREY, C.DARK, 1)

    def fan(self, level, mode, recommended):
        t = self.tft
        # Fixed width, right-aligned. seg7 only clears as wide as the string it is
        # given, so dropping from "10" to "7" left the old second digit standing and
        # the screen read 70. flow() is safe for the same reason: it uses "%3d".
        s = " -" if level is None else "%2d" % level
        if self._changed("fan", s):
            t.seg7(s, 212, 48, digit_w=30, digit_h=52, thick=7, color=C.BLUE, bg=C.DARK)
        line = "%s%s" % ((mode or "").upper(),
                         "" if recommended is None else "  rec %d" % recommended)
        if self._changed("fanmode", line):
            t.fill_rect(200, 104, t.width - 200, 10, C.DARK)
            t.text(line[:14], 206, 104, C.GREY, C.DARK, 1)

    def headline(self, text, severity="ok"):
        t = self.tft
        text = (text or "")[:38]
        if self._changed("head", text + severity):
            t.fill_rect(0, 122, t.width, 26, C.DARK)
            t.text(text, 8, 126, _SEV_COLOR.get(severity, C.GREY), C.DARK, 1)

    def channels(self, rows):
        """rows: list of (name, pascals, ok). Two columns under the divider."""
        t = self.tft
        if self._changed("chcount", len(rows)):
            t.fill_rect(0, 156, t.width, t.height - 156, C.DARK)
            self._rows = []
        for i, (name, pa, ok) in enumerate(rows[:8]):
            col, row = i % 2, i // 2
            x = 8 + col * 160
            y = 158 + row * 21
            txt = "%-7s %s" % (name[:7], "  --  " if not ok else "%6.1f" % pa)
            if self._changed("ch%d" % i, txt):
                t.text(txt, x, y, C.WHITE if ok else C.ORANGE, C.DARK, 1)
            # small bar, scaled to 500 Pa
            if ok:
                w = int(min(1.0, abs(pa) / 500.0) * 40)
                if self._changed("bar%d" % i, w):
                    t.fill_rect(x + 112, y + 2, 40, 5, C.PANEL)
                    if w:
                        t.fill_rect(x + 112, y + 2, w, 5, C.BLUE)
