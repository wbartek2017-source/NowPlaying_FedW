#!/usr/bin/env python3
"""
rockpaper - turns the MOTHERBOARD Rockbox theme (by Monica G., CC-BY-SA 3.0)
into a "now playing" GNOME wallpaper driven by MPRIS (Spotify, Firefox, VLC...).

    ./rockpaper.py            run in the background loop and set the wallpaper
    ./rockpaper.py --demo     render demo.png with fake data and exit
"""
import argparse, io, os, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

# ───────────────────────── config ─────────────────────────
SCREEN   = (1920, 1080)          # your monitor resolution
BG_COLOR = (0x25, 0xC2, 0x53)    # theme "background color" (25C253). Try any colour!
FONT     = "terminal"            # "terminal" = same font as your terminal; or a family name e.g. "JetBrains Mono"; "" = system monospace
FONT_SCALE = 1.0                 # make all text bigger/smaller (e.g. 1.2)
MODE     = "cover"                 # "fit" = crisp integer scale, centred, board texture around it
                                 # "cover" = fill the screen (crops top/bottom a little)
POLL     = 1                     # seconds between player checks
REFRESH  = 0                    # also redraw every N s so the progress bar/clock move (0 = only on track/state change)
IDLE_IMAGE   = ""   # path to your own default wallpaper, or "" to draw the MOTHERBOARD screen as "Nothing playing"
IDLE_REFRESH = 60   # seconds between idle redraws so the clock stays right (ignored if IDLE_IMAGE is set)
SHOW_PROGRESS = False            # progress bar + elapsed/remaining times along the bottom
ART_MARGIN = 32                  # cover mode: gap in screen pixels between the album art and the bottom edge

# ──────────────────────────────────────────────────────────

HERE    = Path(__file__).resolve().parent
ASSETS  = HERE / "assets"
OUT_DIR = Path.home() / ".cache" / "rockpaper"
NW, NH  = 320, 240               # the iPod's native screen
WHITE   = (255, 255, 255, 255)
GREY    = (128, 128, 128, 255)


# ───────────────────────── assets ─────────────────────────
def is_key(p):  # Rockbox's transparent colour is magenta
    return p[0] > 240 and p[1] < 16 and p[2] > 240

def load_rgba(name):
    im = Image.open(ASSETS / name).convert("RGB")
    out = Image.new("RGBA", im.size)
    src, dst = im.load(), out.load()
    for y in range(im.height):
        for x in range(im.width):
            p = src[x, y]
            dst[x, y] = (0, 0, 0, 0) if is_key(p) else (*p, 255)
    return out

def load_backdrop():
    im = Image.open(ASSETS / "MOTHERBOARD_WPS.bmp").convert("RGB")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if is_key(px[x, y]):
                px[x, y] = BG_COLOR
    return im.convert("RGBA")

def frame(strip, i, h):  # Rockbox multi-image strips are stacked vertically, 1-based
    return strip.crop((0, (i - 1) * h, strip.width, i * h))

def fc(pattern):
    """Ask fontconfig for the best match -> (file, index, family) or None."""
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}\t%{index}\t%{family}", pattern],
                           capture_output=True, text=True, timeout=5)
        f, i, fam = (r.stdout.split("\t") + ["0", ""])[:3]
        return (f, int(i or 0) & 0xFFFF, fam) if f else None
    except Exception:
        return None

_STYLE_WORDS = {"regular", "bold", "italic", "oblique", "light", "medium", "semibold", "semi-bold",
                "extrabold", "extra-bold", "thin", "heavy", "black", "book", "demi", "condensed", "semi-condensed"}

def clean_family(name):
    """'JetBrains Mono Bold 12' (Pango font string) -> 'JetBrains Mono'."""
    parts = name.strip().strip("'\"").split()
    while parts and (parts[-1].replace(".", "", 1).isdigit() or parts[-1].lower() in _STYLE_WORDS):
        parts.pop()
    return " ".join(parts)

def gs(*args):
    try:
        r = subprocess.run(["gsettings", "get", *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip().strip("'") if r.returncode == 0 else ""
    except Exception:
        return ""

_family = None
def wanted_family():
    """Font family named by FONT, or the one your terminal uses (Ptyxis / GNOME Terminal / system)."""
    global _family
    if _family is not None:
        return _family
    fam = ""
    if FONT and FONT != "terminal":
        fam = clean_family(FONT)
    elif FONT == "terminal":
        if gs("org.gnome.Ptyxis", "use-system-font") == "false":              # Ptyxis (Fedora's default terminal)
            fam = clean_family(gs("org.gnome.Ptyxis", "font-name"))
        if not fam:                                                           # GNOME Terminal default profile
            uuid = gs("org.gnome.Terminal.ProfilesList", "default")
            if uuid:
                schema = f"org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{uuid}/"
                if gs(schema, "use-system-font") == "false":
                    fam = clean_family(gs(schema, "font"))
        if not fam:                                                           # system monospace font
            fam = clean_family(gs("org.gnome.desktop.interface", "monospace-font-name"))
    _family = fam
    return fam

def find_font(bold=False, lang=None):
    """Returns (path, index) of a scalable font. lang='ja' picks a Japanese-capable font."""
    if lang is None:
        local = ASSETS / "fonts"
        if local.exists():                              # fonts you drop in assets/fonts win
            for p in sorted(local.iterdir()):
                if p.suffix.lower() in (".ttf", ".otf") and (("bold" in p.name.lower()) == bold):
                    return str(p), 0
        fam = wanted_family()
        if fam:                                          # terminal / requested font, only if really installed
            m = fc(f"{fam}" + (":bold" if bold else ""))
            if m and fam.lower() in m[2].lower() and m[0].lower().endswith((".ttf", ".otf", ".ttc")):
                return m[0], m[1]
        t = fc("Terminus" + (":bold" if bold else ""))  # real Terminus TTF, if installed
        if t and "terminus" in t[2].lower() and t[0].lower().endswith((".ttf", ".otf")):
            return t[0], t[1]
        m = fc("monospace" + (":bold" if bold else ""))
    else:
        m = fc(f"sans-serif:lang={lang}" + (":bold" if bold else ""))
    if m and m[0].lower().endswith((".ttf", ".otf", ".ttc")):
        return m[0], m[1]
    return None

_fonts = {}
def _load(size, bold, lang):
    k = (size, bold, lang)
    if k not in _fonts:
        f = None
        found = find_font(bold, lang)
        if found:
            try:
                f = ImageFont.truetype(found[0], size, index=found[1])
            except Exception:
                f = None
        if f is None:
            try:
                f = ImageFont.load_default(size)         # last resort: still honours the size
            except TypeError:
                f = ImageFont.load_default()
            print(f"rockpaper: no usable {lang or 'monospace'} font found, using Pillow's default", file=sys.stderr)
        _fonts[k] = f
    return _fonts[k]

def font(size, bold=False):      return _load(size, bold, None)
def cjk_font(size, bold=False):  return _load(size, bold, "ja")

def is_cjk(ch):
    o = ord(ch)
    return 0x2E80 <= o <= 0xD7FF or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF


# ───────────────────────── text (drawn at full screen resolution) ─────────────────────────
def text_px(img, box, s, size, bold, align, k):
    """Draw s in viewport box (native coords) at screen scale k: smooth, clipped, ellipsised.
    Latin text uses the main font; CJK characters switch to a Japanese-capable font."""
    x, y, w, h = [round(v * k) for v in box]
    px = max(1, round(size * k * FONT_SCALE))
    main, alt = font(px, bold), cjk_font(px, bold)
    asc, desc = main.getmetrics()
    if asc + desc > h:                               # font's line is taller than the box: shrink to fit
        px = max(1, int(px * h / (asc + desc)))
        main, alt = font(px, bold), cjk_font(px, bold)
    layer = Image.new("RGBA", (max(1, w), max(1, h) + px // 3), (0, 0, 0, 0))   # slack so CJK descenders aren't clipped
    d = ImageDraw.Draw(layer)

    def runs(t):                                     # split into (chunk, font) runs
        out = []
        for ch in t:
            f = alt if is_cjk(ch) else main
            if out and out[-1][1] is f:
                out[-1][0] += ch
            else:
                out.append([ch, f])
        return out
    width = lambda t: sum(d.textlength(c, font=f) for c, f in runs(t))

    while len(s) > 1 and width(s) > w:
        s = s[:-2].rstrip() + "…" if not s.endswith("…") else s[:-2] + "…"
    cx = {"l": 0, "c": (w - width(s)) // 2, "r": w - width(s)}[align]
    base = main.getmetrics()[0]                      # shared baseline so mixed scripts line up
    for chunk, f in runs(s):
        d.text((cx, base), chunk, font=f, fill=WHITE, anchor="ls")
        cx += d.textlength(chunk, font=f)
    img.paste(layer, (x, y), layer)


# ───────────────────────── player data ─────────────────────────
SEP = "¦¦"
FMT = SEP.join("{{%s}}" % k for k in (
    "status", "title", "artist", "album", "mpris:artUrl", "position",
    "mpris:length", "volume", "loop", "shuffle", "playerName"))

def get_state():
    r = subprocess.run(["playerctl", "metadata", "--format", FMT],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    p = (r.stdout.rstrip("\n").split(SEP) + [""] * 11)[:11]
    num = lambda v: float(v) if v.replace(".", "", 1).isdigit() else 0.0
    return dict(status=p[0], title=p[1], artist=p[2], album=p[3], art=p[4],
                pos=num(p[5]) / 1e6, length=num(p[6]) / 1e6, volume=num(p[7]),
                loop=p[8], shuffle=p[9].lower() == "true", player=p[10])

_art_cache = {}
def system_volume():
    """Master volume 0..1 (0 if muted): PipeWire first (Fedora's default), then PulseAudio."""
    try:
        out = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                             capture_output=True, text=True, timeout=2).stdout
        if out.startswith("Volume:"):
            return 0.0 if "MUTED" in out else float(out.split()[1])
    except Exception:
        pass
    try:
        out = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                             capture_output=True, text=True, timeout=2).stdout
        mute = subprocess.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                              capture_output=True, text=True, timeout=2).stdout
        return 0.0 if "yes" in mute else int(out.split("/")[1].strip().rstrip("%")) / 100
    except Exception:
        return None
def idle_state():
    return dict(status="Stopped", title="Nothing playing", artist="", album="MOTHERBOARD",
                art="", pos=0, length=0, volume=0.0, loop="None", shuffle=False, player="idle")
def fetch_art(url):
    if not url:
        return None
    if url not in _art_cache:
        try:
            if url.startswith("file://"):
                im = Image.open(urllib.request.url2pathname(url[7:]))
            else:
                with urllib.request.urlopen(url, timeout=6) as f:
                    im = Image.open(io.BytesIO(f.read()))
            _art_cache.clear()
            _art_cache[url] = im.convert("RGB")
        except Exception:
            _art_cache[url] = None
    return _art_cache[url]

def battery():
    for b in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        try:
            return int((b / "capacity").read_text()), (b / "status").read_text().strip()
        except Exception:
            pass
    return None, None

def mmss(t):
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


# ───────────────────────── render ─────────────────────────
def render_native(s, A):
    """Pixel-art layer at 320x240 (backdrop, icons, bars) + overlays drawn sharp later."""
    c = A["backdrop"].copy()
    ov = []                                            # ("text", box, str, size, bold, align) / ("art", box, img)

    # album art box: black plate here, real art drawn at full resolution on top
    art = fetch_art(s["art"])
    c.alpha_composite(Image.new("RGBA", (92, 92), (0, 0, 0, 255)), (223, 100))
    ov.append(("art", (223, 100, 92, 92), art) if art else ("text", (223, 100 + 38, 92, 16), "NO ART", 12, False, "c"))

    mp = {"Playing": 2, "Paused": 3}.get(s["status"], 1)
    c.alpha_composite(frame(A["modes"], mp, 25), (15, 137))
    rep = {"Playlist": 2, "Track": 3}.get(s["loop"], 1)
    c.alpha_composite(frame(A["repeat"], rep, 25), (16, 167))
    c.alpha_composite(frame(A["shuffle"], 2 if s["shuffle"] else 1, 25), (45, 167))
    c.alpha_composite(frame(A["lock"], 2, 16), (7, 8))   # unlocked frame covers the backdrop's lock silhouette

    ov.append(("text", (100, 0, 140, 13), datetime.now().strftime("%H:%M"), 12, False, "c"))

    pct, st = battery()
    if pct is not None:
        ov.append(("text", (253, 12, 27, 13), f"{pct}%", 12, False, "r"))
        c.alpha_composite(frame(A["battery"], 1 + min(10, pct // 10), 10), (291, 13))

    vol = max(0.0, min(1.0, s["volume"]))
    c.alpha_composite(A["vb_back"], (249, 60))
    if round(70 * vol):
        c.alpha_composite(A["vb"].crop((0, 0, round(70 * vol), 12)), (249, 60))
    ov.append(("text", (254, 73, 35, 13), "VOL", 10, False, "l"))
    ov.append(("text", (270, 73, 46, 13), f"{round(vol * 100)}%", 10, False, "r"))

    ov.append(("text", (35, 35, 178, 18), s["album"] or "Unknown Album", 14, False, "l"))
    ov.append(("text", (35, 55, 178, 30), s["title"] or "Unknown Title", 18, True, "l"))
    ov.append(("text", (35, 79, 178, 18), s["artist"], 14, False, "l"))
    ov.append(("text", (35, 98, 175, 15), f"{s['player'].upper()} // {s['status'].upper()}", 12, False, "l"))

    if SHOW_PROGRESS:
        frac = max(0.0, min(1.0, (s["pos"] / s["length"]) if s["length"] else 0))
        c.alpha_composite(A["pb_back"], (35, 234))
        if round(247 * frac):
            c.alpha_composite(A["pb"].crop((0, 0, round(247 * frac), 3)), (35, 234))
        ov.append(("text", (2, 228, 32, 12), mmss(s["pos"]), 11, False, "c"))
        ov.append(("text", (284, 228, 32, 12), mmss(max(0, s["length"] - s["pos"])), 11, False, "c"))
    return c, ov


def to_screen(native, ov, A):
    sw, sh = SCREEN
    if MODE == "cover":
        k = max(sw / NW, sh / NH)
    else:
        k = max(1, min(sw // NW, sh // NH))
    uw, uh = round(NW * k), round(NH * k)
    ox, oy = (sw - uw) // 2, (sh - uh) // 2
    if MODE == "cover":              # slide the UI up so the album art sits just above the bottom edge
        want = sh - ART_MARGIN - round((100 + 92) * k)
        oy = max(sh - uh, min(0, want))
    # surround: dimmed board texture (only visible in "fit" mode)
    kk = max(sw / NW, sh / NH)
    fill = A["backdrop"].resize((round(NW * kk), round(NH * kk)), Image.NEAREST)
    l, t = (fill.width - sw) // 2, (fill.height - sh) // 2
    out = ImageEnhance.Brightness(fill.crop((l, t, l + sw, t + sh)).convert("RGB")).enhance(0.35)

    # pixel-art layer: crisp nearest-neighbour
    out.paste(native.resize((uw, uh), Image.NEAREST).convert("RGB"), (ox, oy))

    # sharp layer: album art + text at full resolution
    for o in ov:
        if o[0] == "art":
            x, y, w, h = [round(v * k) for v in o[1]]
            out.paste(o[2].resize((w, h), Image.LANCZOS), (ox + x, oy + y))
        else:
            _, (x, y, w, h), txt, size, bold, align = o
            text_px(out, (x + ox / k, y + oy / k, w, h), txt, size, bold, align, k)
    return out


# ───────────────────────── GNOME ─────────────────────────
def active_key():
    dark = gs("org.gnome.desktop.interface", "color-scheme") == "prefer-dark"
    return "picture-uri-dark" if dark else "picture-uri"

def set_wallpaper(img):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"wp_{int(time.time() * 1000)}.png"   # new name each time: GNOME caches by URI
    tmp = path.with_suffix(".tmp")
    img.save(tmp, format="PNG", compress_level=1)           # fast save
    os.replace(tmp, path)                                   # atomic: GNOME never sees a half-written file
    subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                    active_key(), f"file://{path}"])        # only the key GNOME is actually showing
    now = time.time()
    for old in sorted(OUT_DIR.glob("wp_*.png"))[:-4]:       # delete only files older than a minute
        if now - old.stat().st_mtime > 60:
            old.unlink()

def load_assets():
    return dict(
        backdrop=load_backdrop(), modes=load_rgba("playmodes_wps.bmp"),
        repeat=load_rgba("repeat_status_wps.bmp"), shuffle=load_rgba("shuffle_wps.bmp"),
        battery=load_rgba("battery.bmp"), lock=load_rgba("lock.bmp"), vb=load_rgba("vb.bmp"), vb_back=load_rgba("vb_back.bmp"),
        pb=load_rgba("pb.bmp"), pb_back=load_rgba("pb_back.bmp"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="write demo.png with fake data and exit")
    args = ap.parse_args()
    A = load_assets()

    if args.demo:
        s = dict(status="Playing", title="Digital Love", artist="Daft Punk", album="Discovery",
                 art="", pos=83, length=301, volume=0.7, loop="Playlist", shuffle=True, player="spotify")
        to_screen(*render_native(s, A), A).save("demo.png")
        print("wrote demo.png")
        return

    subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-options", "zoom"])
    for k, v in (("primary-color", "'#000000'"), ("secondary-color", "'#000000'"),
             ("color-shading-type", "'solid'")):
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", k, v])
    last_key, last_draw = None, 0
    last_key, last_draw = None, 0
    while True:
        s = get_state()
        playing = bool(s) and s["status"] in ("Playing", "Paused")
        if not playing:
            s = idle_state()
        sv = system_volume()
        if sv is not None:
            s["volume"] = sv
        vol = round(s["volume"] * 100)

        if playing:
            key, interval = (s["title"], s["artist"], s["status"], s["art"], vol), REFRESH
        else:
            key = ("idle",) if IDLE_IMAGE else ("idle", vol)
            interval = 0 if IDLE_IMAGE else IDLE_REFRESH

        if key != last_key or (interval and time.time() - last_draw >= interval):
            if not playing and IDLE_IMAGE:
                img = Image.open(os.path.expanduser(IDLE_IMAGE)).convert("RGB")
            else:
                img = to_screen(*render_native(s, A), A)
            set_wallpaper(img)
            last_key, last_draw = key, time.time()
        time.sleep(POLL)


if __name__ == "__main__":
    main()
