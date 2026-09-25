"""Screen layout for the box display (320x240 landscape).

Built to be read from across the room, so it shows only what you act on:

    +--------------------------------------+
    |  ALL GOOD            (status band)   |  scale-4 word, colour = severity
    +--------------------------------------+
    |   212                  7             |  seven-segment, 100 px tall
    |   CFM                 FAN / SET 8    |  scale 2; SET n in amber when the
    +--------------------------------------+  PC wants the dial moved
    |  Everything within                   |  PC headline, scale 2, two lines
    |  baseline                            |
    |  [##][##][##][##][##]                |  one block per sensor
    +--------------------------------------+

Two sources feed it: the node's own channels (always available) and a status
broadcast from the PC app (CFM, overall state, fan level, headline). Everything
is redrawn only when its value changes, so the SPI traffic stays low.
"""

from . import st7789 as C

_SEV_COLOR = {
    "ok": C.GREEN, "info": C.BLUE, "advice": C.AMBER,
    "warning": C.ORANGE, "critical": C.RED, "stale": C.GREY,
}
# Short enough for scale 4 (32 px per character, 10 across).
_SEV_TEXT = {
    "ok": "ALL GOOD", "info": "INFO", "advice": "ADVICE",
    "warning": "CHECK", "critical": "PROBLEM", "stale": "NO PC",
}

BAND_H = 48
NUM_Y, NUM_H = 58, 100
LABEL_Y = 166
HEAD_Y = 194                     # two scale-2 lines: 194 and 214
HEAD_CHARS = 20                  # 320 px / 16 px per character
STRIP_Y, STRIP_H = 234, 6

CFM_X, CFM_W = 8, 48             # three digits: 8 .. 172
DIVIDER_X = 196                  # keeps "118" and "10" from reading as "11810"
FAN_X, FAN_W = 224, 38           # two digits: 224 .. 310


def wrap(text, width=HEAD_CHARS, lines=2):
    """Word-wrap into at most `lines` lines; a word longer than a line is cut."""
    # The 8x8 font is ASCII only; the app shortens long messages with "…".
    text = "".join(c for c in (text or "").replace("…", "...") if " " <= c <= "~")
    out, cur = [], ""
    for word in text.split():
        word = word[:width]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    out = out[:lines]
    return out + [""] * (lines - len(out))


class Screen:
    def __init__(self, tft, node_id):
        self.tft = tft
        self.node_id = node_id
        self._last = {}

    # ---------- helpers ----------
    def _changed(self, key, value):
        if self._last.get(key) == value:
            return False
        self._last[key] = value
        return True

    def _line(self, s, x, y, fg, bg, scale, clear_to=None):
        """Text that blanks the rest of its row, so a shorter string leaves nothing behind."""
        t = self.tft
        w = (t.text(s, x, y, fg, bg, scale) or 0) if s else 0
        end = t.width if clear_to is None else clear_to
        t.fill_rect(x + w, y, end - x - w, 8 * scale, bg)

    def splash(self, line2=""):
        t = self.tft
        t.fill(C.DARK)
        t.text("LumosAir", 16, 40, C.WHITE, C.DARK, 4)
        t.text(self.node_id.upper(), 16, 100, C.BLUE, C.DARK, 3)
        if line2:
            t.text(line2[:HEAD_CHARS], 16, 160, C.GREY, C.DARK, 2)
        self._last.clear()

    def layout(self):
        """Paint the static furniture once."""
        t = self.tft
        t.fill(C.DARK)
        t.fill_rect(0, HEAD_Y - 6, t.width, 1, C.PANEL)
        t.fill_rect(DIVIDER_X, NUM_Y, 2, LABEL_Y + 16 - NUM_Y, C.PANEL)
        self._last.clear()

    # ---------- live values ----------
    def status(self, severity, ip=None, rssi=None):
        """Status band. ip/rssi are accepted for compatibility; the box has no room for them."""
        t = self.tft
        if self._changed("sev", severity):
            color = _SEV_COLOR.get(severity, C.GREY)
            label = _SEV_TEXT.get(severity, severity.upper())[:10]
            t.fill_rect(0, 0, t.width, BAND_H, color)
            t.text(label, (t.width - 32 * len(label)) // 2, 8, C.BLACK, color, 4)

    def flow(self, cfm, source=None):
        """Big CFM readout from the PC; '---' when there's no link."""
        t = self.tft
        s = "---" if cfm is None else "%3d" % min(999, max(0, int(round(cfm))))
        if self._changed("cfm", s):
            t.seg7(s, CFM_X, NUM_Y, digit_w=CFM_W, digit_h=NUM_H, thick=12,
                   color=C.WHITE if cfm is not None else C.GREY, bg=C.DARK)
        if self._changed("cfmunit", True):
            t.text("CFM", CFM_X + 4, LABEL_Y, C.GREY, C.DARK, 2)

    def fan(self, level, mode=None, recommended=None):
        t = self.tft
        # Fixed width, right-aligned. seg7 only clears as wide as the string it is
        # given, so dropping from "10" to "7" left the old second digit standing and
        # the screen read 70. flow() is safe for the same reason: it uses "%3d".
        s = " -" if level is None else "%2d" % level
        if self._changed("fan", s):
            t.seg7(s, FAN_X, NUM_Y, digit_w=FAN_W, digit_h=NUM_H, thick=12,
                   color=C.BLUE, bg=C.DARK)
        move = recommended is not None and recommended != level
        label = ("SET %d" % recommended) if move else "FAN"
        if self._changed("fanlabel", label):
            self._line(label, FAN_X + 4, LABEL_Y, C.AMBER if move else C.GREY, C.DARK, 2)

    def headline(self, text, severity="ok"):
        """The PC's one-line verdict, wrapped onto two big lines."""
        a, b = wrap(text)
        if self._changed("head", (a, b)):
            self._line(a, 0, HEAD_Y, C.WHITE, C.DARK, 2)
            self._line(b, 0, HEAD_Y + 20, C.WHITE, C.DARK, 2)

    def channels(self, rows):
        """rows: list of (name, pascals, ok). One block per sensor: green ok, orange not."""
        t = self.tft
        state = tuple(bool(ok) for _, _, ok in rows)
        if not state or not self._changed("strip", state):
            return
        gap = 4
        w = (t.width - gap * (len(state) + 1)) // len(state)
        t.fill_rect(0, STRIP_Y, t.width, STRIP_H, C.DARK)
        for i, ok in enumerate(state):
            t.fill_rect(gap + i * (w + gap), STRIP_Y, w, STRIP_H, C.GREEN if ok else C.ORANGE)
