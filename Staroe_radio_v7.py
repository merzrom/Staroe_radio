# -*- coding: utf-8 -*-
"""
StaroeRadio Player — Staroe_radio_v7.py

v7:
  • Значок окна наконец работает: iconphoto(False, …) — каждому окну отдельно.
    iconphoto(True, …) / iconbitmap(default=…) поверх окна ttkbootstrap дают в Windows
    недействительный значок (пустое место в заголовке) — показала диагностика icon_diag.py.
    Окно настроек получает тот же значок.
  • Нет обложки на сервере — вместо эмодзи 📻 картинка data/Staroe_radio.png
    (если файла нет — по-прежнему эмодзи).
v6:
  • Значок окна: в Tk передаются только размеры до 64 px. Кадр 256×256 Tk на Windows
    обрабатывает неверно (ширина хранится в одном байте, 256 → 0), и значок был пустым.
v5:
  • Исправлен значок окна: icon.ico / icon.png загружаются через Pillow и ставятся
    через iconphoto (Tk не читает .ico с PNG-кадрами, какие сохраняет Pillow, — значок был пустым).
    В лог пишется, какой значок использован.
v4:
  • В заголовке окна — только название трека (без «— StaroeRadio Player»).
  • Прямой эфир «Старое радио»: по названию из эфира находится ID передачи
    (сначала в программе передач staroeradio.ru, затем в data/staroeradio.txt) —
    показываются обложка и описание; клик по названию в плеере — её описание.
  • Двойной клик по кнопке эфира — следующий поток по кругу.
  • Свой значок окна: icon.ico / icon.png рядом со скриптом, иначе нарисованный
    значок-радиоприёмник вместо точек ttkbootstrap; на Windows значок и на панели задач.
v3:
  • Лог перенесён под Поиск, Описание передачи — под Плеер.
  • «⚙ Настройки» — на нижней панели плеера, рядом с переключателями областей.
  • Новое окно настроек: тёмный заголовок, разделы слева (Общие, Плеер, Кнопки,
    Поиск, Описание, Лог, Схемы), изменения видны сразу, «Сохранить» / «Отменить изменения»,
    сброс каждого цвета к значению по умолчанию (↺).
  • Своя палитра: готовые цвета, недавние, темнее/светлее, HEX, системная палитра.
  • Папка сохранения задаётся в Настройках → Общие (по желанию — спрашивать каждый раз).
  • Тонкие ползунки одного цвета без каймы; цвет задаётся в Настройках → Плеер.
  • Время длиннее часа — в формате 1:27:40.
  • Тонкие скроллбары без стрелок.
  • В Поиске убраны кнопки «Найти» и «Вставить» (работают Enter и Ctrl+V).
  • Над названием трека больше нет сайта и ID.
  • Список: клик — выбор и описание, двойной клик или Enter — воспроизведение.
    Играющий трек выделен цветом текста, выбранный — фоном. Повторный двойной клик
    по уже играющему треку не перезапускает его.
  • Клик по названию трека в плеере — описание играющей передачи.
    Описание показывает название передачи; запоздавший ответ по ранее выбранному
    треку больше не перезаписывает описание (и описания кэшируются).
v2 — редизайн: плеер — основная область, скрываемые панели, мини-плеер, обложка,
     горячие клавиши, строка состояния, фоновая загрузка картинок.
"""
import os
import sys
import glob
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, colorchooser, filedialog, simpledialog
import ttkbootstrap

# 1. СНАЧАЛА определяем директорию приложения
if getattr(sys, 'frozen', False):
    # Для скомпилированного .exe
    app_dir = os.path.dirname(sys.executable)
else:
    # Для обычного скрипта
    app_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Устанавливаем пути ДО импорта vlc
os.environ["VLC_PLUGIN_PATH"] = os.path.join(app_dir, "plugins")

# 3. Добавляем директорию с DLL в PATH (важно для Windows)
if sys.platform == "win32":
    os.environ["PATH"] = app_dir + os.pathsep + os.environ.get("PATH", "")
    # Альтернативно можно использовать:
    # os.add_dll_directory(app_dir)  # Python 3.8+

# 4. Только теперь импортируем vlc
import vlc
import time
import subprocess
import json
import re
import threading
import urllib.request
import urllib.error
from urllib.parse import urljoin, urlparse
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ═══════════════════════════════════════════════════════════════════
#  Вспомогательные виджеты интерфейса
# ═══════════════════════════════════════════════════════════════════
IS_WIN = sys.platform == "win32"
UI_FONT = "Segoe UI" if IS_WIN else "DejaVu Sans"
ICON_FONT = "Segoe UI Emoji" if IS_WIN else "DejaVu Sans"
SYM_FONT = "Segoe UI Symbol" if IS_WIN else "DejaVu Sans"


def _shade(color, amount):
    """Осветлить (amount > 0) или затемнить (amount < 0) цвет #rrggbb."""
    try:
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    except Exception:
        return color
    if amount >= 0:
        r, g, b = (int(c + (255 - c) * amount) for c in (r, g, b))
    else:
        r, g, b = (int(c * (1 + amount)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _plural(n, forms):
    """_plural(5, ('трек', 'трека', 'треков')) -> 'треков'"""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


class Tooltip:
    """Всплывающая подсказка при наведении."""
    def __init__(self, widget, text, delay=550):
        self.widget, self.text, self.delay = widget, text, delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tw, text=self.text, bg="#2b2d31", fg="#dcdde0", bd=1, relief="solid",
                 font=(UI_FONT, 9), padx=7, pady=3, justify=tk.LEFT).pack()
        tw.wm_geometry(f"+{x}+{y}")

    def _hide(self, _e=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class FlatButton(tk.Label):
    """Плоская кнопка с подсветкой при наведении.
    kind: "normal" — обычная, "primary" — акцентная (воспроизведение),
          "toggle" — переключатель (активное состояние — акцентным цветом)."""
    def __init__(self, parent, text, command=None, font=None, padx=8, pady=3,
                 tooltip=None, kind="normal", width=None):
        kw = dict(text=text, font=font or (ICON_FONT, 12), padx=padx, pady=pady,
                  cursor="hand2", bd=0, highlightthickness=0)
        if width:
            kw["width"] = width
        super().__init__(parent, **kw)
        self.command = command
        self.kind = kind
        self.active = False
        self._hover = False
        self._pressed = False
        self._bg, self._fg, self._hover_bg, self._accent = "#000000", "#cccccc", "#2a2a2a", "#4c8bf5"
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.tooltip = Tooltip(self, tooltip) if tooltip else None

    def set_colors(self, bg, fg, hover_bg, accent):
        self._bg, self._fg, self._hover_bg, self._accent = bg, fg, hover_bg, accent
        self._refresh()

    def set_active(self, flag):
        self.active = bool(flag)
        self._refresh()

    def _refresh(self):
        if self.kind == "primary":
            base = self._accent
            bg = _shade(base, -0.15) if self._pressed else (_shade(base, 0.15) if self._hover else base)
            fg = "#ffffff"
        else:
            bg = self._hover_bg if (self._hover or self._pressed) else self._bg
            if self._pressed:
                bg = _shade(self._hover_bg, 0.08)
            fg = self._accent if (self.kind == "toggle" and self.active) else self._fg
            if self.kind == "toggle" and not self.active:
                fg = _shade(self._fg, -0.35)
        try:
            self.config(bg=bg, fg=fg)
        except tk.TclError:
            pass

    def _on_enter(self, _e):
        self._hover = True
        self._refresh()

    def _on_leave(self, _e):
        self._hover = False
        self._pressed = False
        self._refresh()

    def _on_press(self, _e):
        self._pressed = True
        self._refresh()

    def _on_release(self, e):
        was = self._pressed
        self._pressed = False
        self._refresh()
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if was and inside and self.command:
            self.command()



def _deep_merge(base, override):
    """Рекурсивно: всё из base, поверх — то, что есть в override."""
    result = dict(base)
    for k, v in (override or {}).items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def set_titlebar_color(win, hex_color):
    """Тёмный заголовок окна + его цвет через DWM (Windows 10 19041+ / 11).
    На других ОС молча ничего не делает."""
    if not IS_WIN:
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (новые / старые сборки Win10)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        if hex_color and len(hex_color) == 7:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            color = ctypes.c_int(b << 16 | g << 8 | r)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))  # DWMWA_CAPTION_COLOR
    except Exception:
        pass


class ThinSlider(tk.Canvas):
    """Тонкий ползунок: полоса одного цвета и круглая ручка, без рамок.
    variable/command — как у ttk.Scale; on_press/on_drag/on_release получают долю 0..1
    (on_press может вернуть False — тогда нажатие игнорируется)."""
    def __init__(self, parent, from_=0, to=100, variable=None, command=None, length=None,
                 on_press=None, on_drag=None, on_release=None, thickness=4, knob=6):
        super().__init__(parent, highlightthickness=0, bd=0, cursor="hand2", takefocus=0)
        self.configure(height=knob * 2 + 6)
        if length:
            self.configure(width=length)
        self.from_, self.to = from_, to
        self.variable, self.command = variable, command
        self.on_press, self.on_drag, self.on_release = on_press, on_drag, on_release
        self.thickness, self.knob = thickness, knob
        self._value = from_
        self._hover = self._drag = self._lock = False
        self._bg, self._fill, self._track = "#000000", "#3d7be0", "#2a2a2a"
        if variable is not None:
            try:
                self._value = float(variable.get())
            except Exception:
                pass
            variable.trace_add("write", lambda *a: self._sync_var())
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def set_colors(self, bg, fill, track):
        self._bg, self._fill, self._track = bg, fill, track
        self.configure(bg=bg)
        self._redraw()

    def get(self):
        return self._value

    def set(self, value):
        if self._drag:
            return
        self._value = max(self.from_, min(self.to, float(value)))
        self._redraw()

    def _ratio(self, x):
        p = self.knob + 2
        w = self.winfo_width() - 2 * p
        return max(0.0, min(1.0, (x - p) / w)) if w > 0 else 0.0

    def _set_hover(self, flag):
        self._hover = flag
        self._redraw()

    def _sync_var(self):
        if self._lock:
            return
        try:
            self._value = float(self.variable.get())
        except Exception:
            return
        self._redraw()

    def _apply(self, r):
        self._value = self.from_ + r * (self.to - self.from_)
        if self.variable is not None:
            self._lock = True
            self.variable.set(int(round(self._value)))
            self._lock = False
        if self.command:
            self.command(self._value)
        self._redraw()

    def _press(self, e):
        r = self._ratio(e.x)
        if self.on_press and self.on_press(r) is False:
            return
        self._drag = True
        self._apply(r)

    def _motion(self, e):
        if not self._drag:
            return
        r = self._ratio(e.x)
        self._apply(r)
        if self.on_drag:
            self.on_drag(r)

    def _release(self, e):
        if not self._drag:
            return
        r = self._ratio(e.x)
        self._apply(r)
        self._drag = False
        if self.on_release:
            self.on_release(r)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        p = self.knob + 2
        cy = h // 2
        x0, x1 = p, w - p
        span = (self.to - self.from_) or 1
        r = (self._value - self.from_) / span
        rx = x0 + (x1 - x0) * max(0.0, min(1.0, r))
        t = self.thickness + (1 if (self._hover or self._drag) else 0)
        self.create_line(x0, cy, x1, cy, fill=self._track, width=t, capstyle=tk.ROUND)
        if rx > x0:
            self.create_line(x0, cy, rx, cy, fill=self._fill, width=t, capstyle=tk.ROUND)
        k = self.knob if (self._hover or self._drag) else self.knob - 1
        self.create_oval(rx - k, cy - k, rx + k, cy + k, fill=self._fill, outline="")


class ThinScrollbar(tk.Canvas):
    """Тонкий скроллбар без стрелок: скруглённый ползунок, подсветка при наведении."""
    def __init__(self, parent, orient="vertical", command=None, thickness=8):
        super().__init__(parent, highlightthickness=0, bd=0, takefocus=0)
        self.vertical = orient in ("vertical", tk.VERTICAL)
        self.configure(**({"width": thickness} if self.vertical else {"height": thickness}))
        self.command = command
        self.thickness = thickness
        self.first, self.last = 0.0, 1.0
        self._hover = False
        self._drag_start = None
        self._bg, self._thumb, self._thumb_hi = "#000000", "#383838", "#5a5a5a"
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_start", None))

    def set_colors(self, bg):
        self._bg = bg
        self._thumb = _shade(bg, 0.22)
        self._thumb_hi = _shade(bg, 0.42)
        self.configure(bg=bg)
        self._redraw()

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._redraw()

    def _length(self):
        return self.winfo_height() if self.vertical else self.winfo_width()

    def _set_hover(self, flag):
        self._hover = flag
        self._redraw()

    def _thumb_span(self):
        L = self._length()
        a, b = self.first * L, self.last * L
        if b - a < 24:
            mid = (a + b) / 2
            a, b = max(0, mid - 12), min(L, mid + 12)
        return a, b

    def _redraw(self):
        self.delete("all")
        if self.last - self.first >= 0.999 or self._length() < 10:
            return
        a, b = self._thumb_span()
        t = self.thickness
        pad = t / 2
        c = t / 2
        color = self._thumb_hi if (self._hover or self._drag_start) else self._thumb
        lw = t - 2
        if self.vertical:
            self.create_line(c, a + pad, c, max(a + pad, b - pad), fill=color, width=lw, capstyle=tk.ROUND)
        else:
            self.create_line(a + pad, c, max(a + pad, b - pad), c, fill=color, width=lw, capstyle=tk.ROUND)

    def _pos(self, e):
        return e.y if self.vertical else e.x

    def _press(self, e):
        if not self.command:
            return
        pos = self._pos(e)
        a, b = self._thumb_span()
        if a <= pos <= b:
            self._drag_start = (pos, self.first)
        else:
            self.command("scroll", 1 if pos > b else -1, "pages")

    def _motion(self, e):
        if not self._drag_start or not self.command:
            return
        L = self._length()
        if L <= 0:
            return
        start, first = self._drag_start
        self.command("moveto", max(0.0, first + (self._pos(e) - start) / L))



def _norm_title(s):
    """Название для сравнения: нижний регистр, ё→е, только буквы и цифры."""
    return re.sub(r"[^0-9a-zа-я]", "", (s or "").lower().replace("ё", "е"))


def _draw_app_icon(size=64, accent="#3d7be0"):
    """Значок-радиоприёмник (на случай, если рядом нет icon.ico / icon.png)."""
    from PIL import Image, ImageDraw
    k = 4                                   # рисуем крупно и уменьшаем — гладкие края
    S = size * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(S * 0.30, S * 0.28), (S * 0.72, S * 0.08)], fill="#c9ccd2", width=int(S * 0.045))
    d.rounded_rectangle([S * 0.06, S * 0.26, S * 0.94, S * 0.90], radius=S * 0.12, fill=accent)
    d.rounded_rectangle([S * 0.14, S * 0.36, S * 0.52, S * 0.80], radius=S * 0.06, fill="#1c2a44")
    for i in range(5):                      # решётка динамика
        y = S * (0.43 + i * 0.08)
        d.line([(S * 0.19, y), (S * 0.47, y)], fill=accent, width=int(S * 0.025))
    d.rounded_rectangle([S * 0.60, S * 0.38, S * 0.86, S * 0.52], radius=S * 0.03, fill="#e8eaee")
    d.ellipse([S * 0.61, S * 0.60, S * 0.73, S * 0.72], fill="#e8eaee")
    d.ellipse([S * 0.75, S * 0.60, S * 0.87, S * 0.72], fill="#e8eaee")
    return img.resize((size, size), Image.LANCZOS)


def set_app_icon(root, app_dir_path, accent="#3d7be0"):
    """Значок главного окна. Порядок: icon.ico → icon.png → нарисованный.
    ВАЖНО: только iconphoto(False, …). Вариант «по умолчанию для всех окон»
    (iconphoto(True) / iconbitmap(default=)) поверх окна ttkbootstrap даёт в Windows
    пустой значок. Дочерние окна берут картинки из root._app_icons сами.
    Разноцветные точки — это значок ttkbootstrap по умолчанию.
    Файлы читаются через Pillow и ставятся через iconphoto: wm iconbitmap в Tk
    не понимает .ico с PNG-кадрами (их сохраняет Pillow и многие редакторы).
    Возвращает строку для лога."""
    if IS_WIN:
        try:
            import ctypes
            # Свой AppUserModelID — чтобы на панели задач был значок окна, а не python.exe
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("merzrom.StaroeRadioPlayer")
        except Exception:
            pass

    # Не больше 64: кадр 256×256 Tk на Windows превращает в пустой значок
    sizes = (64, 48, 32, 24, 16)
    errors = []
    try:
        from PIL import Image, ImageTk
        has_pil = True
    except ImportError:
        has_pil = False

    for name in ("icon.ico", "icon.png"):
        path = os.path.join(app_dir_path, name)
        if not os.path.exists(path):
            continue
        try:
            if has_pil:
                img = Image.open(path)
                if name.endswith(".ico"):
                    # берём самый крупный кадр из .ico
                    best = max(img.ico.sizes(), key=lambda s: s[0] * s[1])
                    img = img.ico.getimage(best)
                img = img.convert("RGBA")
                root._app_icons = [ImageTk.PhotoImage(img.resize((s, s), Image.LANCZOS)) for s in sizes]
                root.iconphoto(False, *root._app_icons)
            elif name.endswith(".png"):
                root._app_icons = [tk.PhotoImage(file=path)]
                root.iconphoto(False, *root._app_icons)
            else:
                root.iconbitmap(path)           # без Pillow — только классические .ico
            return f"🖼 Значок окна: {name}"
        except Exception as ex:
            errors.append(f"{name}: {ex}")

    try:
        from PIL import ImageTk
        root._app_icons = [ImageTk.PhotoImage(_draw_app_icon(s, accent)) for s in (64, 32, 16)]
        root.iconphoto(False, *root._app_icons)
        msg = "🖼 Значок окна: встроенный (icon.ico / icon.png не найдены)"
    except Exception as ex:
        msg = f"⚠️ Не удалось установить значок окна: {ex}"
    if errors:
        msg = "⚠️ Не удалось прочитать " + "; ".join(errors) + " — " + msg
    return msg


class StaroeRadioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("StaroeRadio Player")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)

        # VLC
        self.instance = vlc.Instance(
            "--network-caching=5000",
            "--file-caching=5000",
            "--live-caching=5000",
            "--http-reconnect",
            "--no-video",
            "--quiet",
            "--verbose=-1",
        )

        self.player = self.instance.media_player_new()

        # Привязка события окончания трека для автоперехода
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_track_end)

        # Конфигурация сайтов по имени файла
        self.site_config = {
            "staroeradio.txt": {
                "stream":  "https://staroeradio.ru/ap/get_mp3_radio_128.php?id={id}",
                "info":    "https://staroeradio.ru/audio/{id}",
                "desc_selector": ("div", "grid_6"),
                "desc_type": "class",
            },
            "lektorium.txt": {
                "stream":  "https://lektorium.su/ap/get_mp3_project_1.php?site=lektorium&id={id}",
                "info":    "https://lektorium.su/audio/{id}",
                "desc_selector": ("div", "mright"),
                "desc_type": "id",
            },
            "reportage.txt": {
                "stream":  "https://reportage.su/ap/get_mp3_project_1.php?site=reportage&id={id}",
                "info":    "https://reportage.su/audio/{id}",
                "desc_selector": ("div", "mright"),
                "desc_type": "id",
            },
            "svidetel.txt": {
                "stream":  "https://svidetel.su/ap/get_mp3_project_1.php?site=svidetel&id={id}",
                "info":    "https://svidetel.su/audio/{id}",
                "desc_selector": ("div", "mright"),
                "desc_type": "id",
            },
            "theatrologia.txt": {
                "stream":  "https://theatrologia.su/ap/get_mp3_project_1.php?site=theatrologia&id={id}",
                "info":    "https://theatrologia.su/audio/{id}",
                "desc_selector": ("div", "description-text"),
                "desc_type": "class",
            },
        }

        # Переменные
        self.current_results = []
        self.current_index = -1
        self.playing_track = None  # Трек, который реально сейчас воспроизводится (независимо от current_results)
        self.playback_history = []  # Стек истории воспроизведения для кнопки ⏪
        # Папка, выбранная пользователем в последний раз для сохранения треков/плейлистов
        self.last_save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.is_playing = False
        self.user_seeking = False
        self.auto_play_enabled = True
        self._info_images = []  # Храним ссылки на PhotoImage чтобы GC не удалил

        # Прямой эфир (потоковое радио)
        self.live_streams = {
            "music": {"url": "https://staroeradio.ru/radio/music128",   "icon": "🎵",   "label": "Музыка"},
            "kids":  {"url": "https://staroeradio.ru/radio/detskoe128", "icon": "🧒🏻", "label": "Детское радио"},
            "old":   {"url": "https://staroeradio.ru/radio/ices128",    "icon": "📻",   "label": "Старое радио"},
        }
        self.current_live_stream = "old"
        self.live_mode_active = False
        self._live_last_title = None
        self._icy_thread = None
        self._icy_stop_event = None

        # Общий счётчик очереди скачивания (может пополняться из разных мест не одновременно)
        self._download_lock = threading.Lock()
        self._download_queue_count = 0

        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))

        self.state_file = os.path.join(self.script_dir, "player_state.json")
        self.colors_file = os.path.join(self.script_dir, "colors_config.json")
        self.history_dir = os.path.join(self.script_dir, "History")

        # Загрузка конфига цветов
        self.load_colors_config()

        # UI
        self.setup_ui()

        # Создаём папку истории (после setup_ui, т.к. log() использует log_text)
        self._ensure_history_dir()

        # Загрузка файлов
        self.refresh_files()

        # Загрузка сохранённого состояния
        self.load_state()

        # Таймер обновления
        self.update_position()

        # Цвет заголовка окна Windows — нужен hwnd, который доступен только
        # после полной отрисовки окна, поэтому откладываем через after()
        tb_bg = self.log_colors.get("titlebar", {}).get("background")
        if tb_bg:
            self.root.after(150, lambda: self._set_titlebar_color(tb_bg))

    def setup_ui(self):
        cfg = self.log_colors
        _sash = cfg.get("frame_labels", {}).get("sash", "#212121")
        info_colors = cfg.get("track_info", {})

        self._themed_buttons = []   # (FlatButton, область) — перекрашиваются в apply_colors
        self._scrollbars = []       # (ThinScrollbar, область)
        self._panels = {}           # область -> словарь виджетов панели
        self._player_frames = []    # фреймы плеера с фоном области плеера

        # Видимость панелей и их запомненные размеры
        self.show_search = True
        self.show_log = True
        self.show_info = True
        self.mini_mode = False
        self._pre_mini = None
        self._mini_geometry = None
        self.pin_on_top = False
        self._sizes = {"left_w": 585, "search_h": 430, "info_h": 260}
        self._muted_volume = None
        self._cover_img = None
        self._cover_key = None
        self._source_url = None
        self._last_title = None
        self.selected_index = -1     # выделенная строка в списке (не обязательно играющая)
        self._info_req = 0           # номер последнего запроса описания
        self._info_cache = {}        # (id, source) -> данные описания
        self._settings_win = None
        self.ask_save_dir = False

        # ========= Главный горизонтальный PanedWindow =========
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=5, bd=0, opaqueresize=True)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        left_paned = tk.PanedWindow(paned_window, orient=tk.VERTICAL, sashwidth=5, bd=0, opaqueresize=True)
        right_paned = tk.PanedWindow(paned_window, orient=tk.VERTICAL, sashwidth=5, bd=0, opaqueresize=True)
        paned_window.add(left_paned, width=self._sizes["left_w"], stretch="never")
        paned_window.add(right_paned, width=400, stretch="always")
        self.paned_window = paned_window
        self.left_paned = left_paned
        self.right_paned = right_paned

        # ═══════════════════ Слева: «Поиск» ═══════════════════
        sp = self._make_panel(left_paned, "Поиск", "search", lambda: self.toggle_panel("search"))
        self.search_panel = sp["outer"]
        self.list_frame = sp["body"]
        self.file_count_label = sp["info"]

        self.search_frame = tk.Frame(self.list_frame)
        self.search_frame.pack(fill=tk.X, pady=(0, 6))
        self.search_entry = ttk.Entry(self.search_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.search_entry.bind("<Return>", lambda e: self.search())
        for text, cmd, tip in (
            ("📻", self.load_program, "Программа передач staroeradio.ru"),
            ("🕐", self.load_history, "История и избранное"),
        ):
            b = FlatButton(self.search_frame, text, cmd, font=(ICON_FONT, 13), padx=7, tooltip=tip)
            b.pack(side=tk.LEFT, padx=1)
            self._themed_buttons.append((b, "search"))

        res_wrap = tk.Frame(self.list_frame)
        res_wrap.pack(fill=tk.BOTH, expand=True)
        self._panels["search"]["extra"] = [self.search_frame, res_wrap]
        self.results_listbox = tk.Text(res_wrap, font=("Consolas", 10), height=15, width=50,
                                       wrap=tk.NONE, bd=0, highlightthickness=0, padx=4, cursor="arrow")
        self._attach_scrollbars(res_wrap, self.results_listbox, "search", horizontal=True)

        for tag_name, tag_config in cfg.get("search_tags", {}).items():
            kw = {"foreground": tag_config.get("foreground", "#FFFFFF")}
            if tag_config.get("background"):
                kw["background"] = tag_config["background"]
            self.results_listbox.tag_config(tag_name, **kw)

        # Клик — выбор (и описание), двойной клик / Enter — воспроизведение
        self.results_listbox.bind("<Button-1>", self.on_listbox_click)
        self.results_listbox.bind("<Double-Button-1>", self.on_listbox_double)
        self.results_listbox.bind("<Return>", lambda e: self._play_line(self.selected_index) or "break")
        self.results_listbox.bind("<Motion>", self._on_results_motion)
        self.results_listbox.bind("<Leave>", lambda e: self.results_listbox.tag_remove("hover", "1.0", tk.END))
        self.results_listbox.bind("<Control-c>", lambda e: self._copy_selection(self.results_listbox))
        self.results_listbox.bind("<Control-C>", lambda e: self._copy_selection(self.results_listbox))

        # ═══════════════════ Слева, под поиском: «Лог» ═══════════════════
        lp = self._make_panel(left_paned, "Лог", "log", lambda: self.toggle_panel("log"))
        self.log_panel = lp["outer"]
        self.log_frame = lp["body"]
        clr = FlatButton(lp["head"], "🗑", self.clear_log, font=(ICON_FONT, 10), padx=5, pady=0,
                         tooltip="Очистить лог")
        clr.pack(side=tk.RIGHT, after=lp["close"])
        self._themed_buttons.append((clr, "log"))
        log_wrap = tk.Frame(self.log_frame)
        log_wrap.pack(fill=tk.BOTH, expand=True)
        self._panels["log"]["extra"] = [log_wrap]
        self.log_text = tk.Text(log_wrap, height=6, font=("Consolas", 9), wrap=tk.NONE, bd=0,
                                highlightthickness=0, padx=4, state=tk.DISABLED)
        self._attach_scrollbars(log_wrap, self.log_text, "log", horizontal=True)
        for tag_name, tag_config in cfg.get("log_tags", {}).items():
            kw = {"foreground": tag_config.get("foreground", "#FFFFFF")}
            if tag_config.get("background"):
                kw["background"] = tag_config["background"]
            self.log_text.tag_config(tag_name, **kw)
        self.log_text.bind("<Control-c>", lambda e: self._copy_selection(self.log_text))
        self.log_text.bind("<Control-C>", lambda e: self._copy_selection(self.log_text))

        left_paned.add(self.search_panel, height=self._sizes["search_h"], stretch="always")
        left_paned.add(self.log_panel, stretch="always")

        # ═══════════════════ Справа: Плеер (основная область) ═══════════════════
        self.control_frame = tk.Frame(right_paned)
        right_paned.add(self.control_frame, height=350, stretch="always")
        self._build_player(self.control_frame)

        # ═══════════════════ Справа, под плеером: «Описание передачи» ═══════════════════
        ip = self._make_panel(right_paned, "Описание передачи", "info", lambda: self.toggle_panel("info"))
        self.info_panel = ip["outer"]
        self.info_frame = ip["body"]
        info_wrap = tk.Frame(self.info_frame)
        info_wrap.pack(fill=tk.BOTH, expand=True)
        self._panels["info"]["extra"] = [info_wrap]
        self.info_text = tk.Text(
            info_wrap, height=8, wrap=tk.WORD, state=tk.DISABLED, bd=0, highlightthickness=0, padx=4,
            font=("Consolas", info_colors.get("font_size", 9), info_colors.get("font_weight", "normal")))
        self._attach_scrollbars(info_wrap, self.info_text, "info", horizontal=False)
        self.info_text.tag_config("link", underline=True)
        self.info_text.tag_bind("link", "<Enter>", lambda e: self.info_text.config(cursor="hand2"))
        self.info_text.tag_bind("link", "<Leave>", lambda e: self.info_text.config(cursor=""))
        self.info_text.bind("<Control-c>", lambda e: self._copy_selection(self.info_text))
        self.info_text.bind("<Control-C>", lambda e: self._copy_selection(self.info_text))
        right_paned.add(self.info_panel, height=self._sizes["info_h"], stretch="never")

        # Вставка в поле поиска глобально
        self.root.bind("<Control-v>", self._global_paste)
        self.root.bind("<Control-V>", self._global_paste)
        # Горячие клавиши (работают и в русской раскладке)
        self.root.bind_all("<KeyPress>", self._on_hotkey, add="+")

        # ========= Контекстные меню =========
        self._bind_context_menu(self.search_entry,   can_paste=True,  can_copy=True)
        self._bind_context_menu(self.info_text,      can_paste=False, can_copy=True)
        self._bind_context_menu(self.log_text,       can_paste=False, can_copy=True)
        self._bind_context_menu(self.current_label,  can_paste=False, can_copy=True, is_label=True)
        self._bind_results_context_menu(self.results_listbox)

        self.root.minsize(480, 230)
        self._sync_toggle_buttons()
        self.apply_colors()

    # ══════════════════════ Построение элементов ══════════════════════
    def _attach_scrollbars(self, wrap, text, area, horizontal=True):
        """Разместить Text в wrap с тонкими скроллбарами."""
        vs = ThinScrollbar(wrap, "vertical", command=text.yview)
        text.configure(yscrollcommand=vs.set)
        text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self._scrollbars.append((vs, area))
        if horizontal:
            hs = ThinScrollbar(wrap, "horizontal", command=text.xview)
            text.configure(xscrollcommand=hs.set)
            hs.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            self._scrollbars.append((hs, area))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

    def _make_panel(self, parent, title, area, on_close):
        """Панель с заголовком, кнопкой ✕ (скрыть) и телом."""
        outer = tk.Frame(parent)
        head = tk.Frame(outer)
        head.pack(fill=tk.X, padx=8, pady=(5, 0))
        title_lbl = tk.Label(head, text=title.upper(), font=(UI_FONT, 8, "bold"))
        title_lbl.pack(side=tk.LEFT)
        info_lbl = tk.Label(head, text="", font=(UI_FONT, 8))
        info_lbl.pack(side=tk.LEFT, padx=(8, 0))
        close = FlatButton(head, "✕", on_close, font=(UI_FONT, 9), padx=6, pady=0, tooltip="Скрыть панель")
        close.pack(side=tk.RIGHT)
        self._themed_buttons.append((close, area))
        sep = tk.Frame(outer, height=1)
        sep.pack(fill=tk.X, padx=8, pady=(4, 6))
        body = tk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True, padx=(8, 4), pady=(0, 6))
        panel = {"outer": outer, "head": head, "title": title_lbl, "info": info_lbl,
                 "close": close, "sep": sep, "body": body, "extra": []}
        self._panels[area] = panel
        return panel

    def _build_player(self, parent):
        def frame(master, **kw):
            f = tk.Frame(master, **kw)
            self._player_frames.append(f)
            return f

        def pbtn(master, text, cmd, tip, size=15, kind="normal", padx=9, pady=4, font=None):
            b = FlatButton(master, text, cmd, font=font or (ICON_FONT, size), padx=padx, pady=pady,
                           tooltip=tip, kind=kind)
            self._themed_buttons.append((b, "player"))
            return b

        # ── Нижняя панель: переключатели областей, настройки, статус ──
        # (пакуется первой и снизу — при нехватке высоты не обрезается)
        self.bar_frame = bar = frame(parent)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(3, 4))
        self._bar_sep = tk.Frame(parent, height=1)
        self._bar_sep.pack(side=tk.BOTTOM, fill=tk.X, padx=8)

        def tbtn(text, cmd, tip):
            b = FlatButton(bar, text, cmd, font=(UI_FONT, 9), padx=7, pady=2, tooltip=tip, kind="toggle")
            b.pack(side=tk.LEFT, padx=(0, 2))
            self._themed_buttons.append((b, "player"))
            return b

        self.tg_search = tbtn("◧ Поиск", lambda: self.toggle_panel("search"), "Показать/скрыть поиск  (Ctrl+1)")
        self.tg_log = tbtn("≡ Лог", lambda: self.toggle_panel("log"), "Показать/скрыть лог  (Ctrl+2)")
        self.tg_info = tbtn("▤ Описание", lambda: self.toggle_panel("info"), "Показать/скрыть описание  (Ctrl+3)")
        self.tg_settings = tbtn("⚙ Настройки", self.open_settings, "Цвета, шрифты, папка сохранения")

        self.mini_btn = FlatButton(bar, "▭", self.toggle_mini, font=(SYM_FONT, 11), padx=6, pady=1,
                                   tooltip="Мини-плеер: только плеер в маленьком окне  (Ctrl+M)", kind="toggle")
        self.mini_btn.pack(side=tk.RIGHT)
        self.pin_btn = FlatButton(bar, "📌", self.toggle_pin, font=(ICON_FONT, 10), padx=6, pady=1,
                                  tooltip="Поверх всех окон", kind="toggle")
        self.pin_btn.pack(side=tk.RIGHT)
        self._themed_buttons += [(self.mini_btn, "player"), (self.pin_btn, "player")]

        self.dl_label = tk.Label(bar, text="", font=(UI_FONT, 9))
        self.dl_label.pack(side=tk.RIGHT, padx=(0, 6))
        Tooltip(self.dl_label, "Файлов в очереди на скачивание")
        self.status_label = tk.Label(bar, text="", font=(UI_FONT, 9), anchor="w", cursor="hand2")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 6))
        self.status_label.bind("<Button-1>", lambda e: self.toggle_panel("log", force=True))
        Tooltip(self.status_label, "Последнее сообщение лога — клик открывает лог")

        # ── Карточка текущего трека ─────────────────────────────
        self.card_frame = card = frame(parent)
        card.pack(fill=tk.X, padx=16, pady=(14, 4))
        self.cover_box = tk.Frame(card, width=132, height=132, cursor="hand2")
        self.cover_box.pack(side=tk.LEFT, anchor=tk.N)
        self.cover_box.pack_propagate(False)
        self.cover_label = tk.Label(self.cover_box, text="📻", font=(ICON_FONT, 40), cursor="hand2")
        self.cover_label.pack(fill=tk.BOTH, expand=True)
        for w in (self.cover_box, self.cover_label):
            w.bind("<Button-1>", lambda e: self._open_source_page())
        Tooltip(self.cover_label, "Открыть страницу передачи на сайте")
        self._cover_size = 132
        self._cover_bytes = None
        parent.bind("<Configure>", self._on_player_resize, add="+")

        self.meta_frame = meta = frame(card)
        meta.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))
        self.current_label = ttk.Label(meta, text="Нет трека", wraplength=350, justify=tk.LEFT, cursor="hand2")
        self.current_label.pack(anchor=tk.W, fill=tk.X)
        self.current_label.bind("<Button-1>", self._on_title_click)
        Tooltip(self.current_label, "Показать описание этой передачи")
        meta.bind("<Configure>", lambda e: self.current_label.config(wraplength=max(150, e.width - 6)))
        self.state_label = tk.Label(meta, text="", font=(UI_FONT, 9), anchor="w")
        self.state_label.pack(anchor=tk.W, fill=tk.X, pady=(8, 0))

        # ── Прогресс ────────────────────────────────────────────
        self.progress_frame = frame(parent)
        self.progress_frame.pack(fill=tk.X, padx=16, pady=(8, 0))
        self.time_current = tk.Label(self.progress_frame, text="00:00", width=8, anchor="w", font=(UI_FONT, 9))
        self.time_current.pack(side=tk.LEFT)
        self.time_total = tk.Label(self.progress_frame, text="00:00", width=8, anchor="e", font=(UI_FONT, 9))
        self.time_total.pack(side=tk.RIGHT)
        self.progress_slider = ThinSlider(self.progress_frame, on_press=self._seek_press,
                                          on_drag=self._seek_preview, on_release=self._seek_release)
        self.progress_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.progress_slider.bind("<MouseWheel>", self._on_progress_wheel)

        # ── Кнопки управления + громкость ───────────────────────
        self.btn_frame = row = frame(parent)
        row.pack(fill=tk.X, padx=12, pady=(6, 8))
        transport = frame(row)
        transport.pack(side=tk.LEFT)
        pbtn(transport, "⏮", self.prev_track, "Предыдущий (из истории воспроизведения)",
             font=(SYM_FONT, 15)).pack(side=tk.LEFT)
        self.play_pause_btn = pbtn(transport, "⏸️", self.pause, "Пауза / продолжить  (Пробел)",
                                   kind="primary", padx=14, pady=3, size=16)
        self.play_pause_btn.pack(side=tk.LEFT, padx=6)
        pbtn(transport, "⏭", self.next_track, "Следующий в списке", font=(SYM_FONT, 15)).pack(side=tk.LEFT)

        sep = tk.Frame(row, width=1, height=24)
        sep.pack(side=tk.LEFT, padx=10)
        self._player_seps = [sep]
        actions = frame(row)
        actions.pack(side=tk.LEFT)
        pbtn(actions, "⭐", self.add_to_favorites, "В избранное", size=13).pack(side=tk.LEFT)
        pbtn(actions, "💾", self.download_playing_mp3, "Скачать MP3 текущего трека", size=13).pack(side=tk.LEFT)
        self.live_btn = pbtn(actions, self.live_streams[self.current_live_stream]["icon"],
                             self._on_live_btn_click,
                             "Прямой эфир\nДвойной клик — следующий поток\nПКМ — выбор потока", size=13)
        self.live_btn.pack(side=tk.LEFT)
        self.live_btn.bind("<Button-3>", self._show_live_menu)
        self.live_btn.bind("<Double-Button-1>", self._on_live_btn_double)
        self._live_click_job = None
        self._live_dbl = False

        self.vol_frame = frame(row)
        self.vol_frame.pack(side=tk.RIGHT)
        self.vol_icon_label = tk.Label(self.vol_frame, text="🔊", font=(ICON_FONT, 13), cursor="hand2")
        self.vol_icon_label.pack(side=tk.LEFT, padx=(0, 2))
        self.vol_icon_label.bind("<Button-1>", lambda e: self.toggle_mute())
        Tooltip(self.vol_icon_label, "Без звука / вернуть\nКолесо мыши — громкость")
        self.volume_var = tk.IntVar(value=80)
        self.volume_slider = ThinSlider(self.vol_frame, variable=self.volume_var, command=self.set_volume,
                                        length=110)
        self.volume_slider.pack(side=tk.LEFT)
        self.volume_label = tk.Label(self.vol_frame, text="80%", width=5, anchor="e", font=(UI_FONT, 9))
        self.volume_label.pack(side=tk.LEFT)
        for w in (self.volume_slider, self.vol_icon_label, self.volume_label):
            w.bind("<MouseWheel>", self._on_volume_wheel)

    def _area_bg(self, area):
        cfg = self.log_colors
        if area == "search":
            return cfg.get("results_area", {}).get("background", "#000000")
        if area == "info":
            return cfg.get("track_info", {}).get("background", "#000000")
        if area == "log":
            return cfg.get("log_area", {}).get("background", "#000000")
        return cfg.get("player_labels", {}).get("player_area", {}).get("background", "#000000")

    # ══════════════════════ Показ / скрытие областей ══════════════════════
    def _pane_names(self, pw):
        return [str(p) for p in pw.panes()]

    def _capture_sizes(self):
        """Запомнить текущие размеры видимых панелей (до скрытия/показа)."""
        try:
            if not self.root.winfo_ismapped():
                return
            if str(self.left_paned) in self._pane_names(self.paned_window):
                w = self.left_paned.winfo_width()
                if w > 40:
                    self._sizes["left_w"] = w
            names = self._pane_names(self.left_paned)
            if str(self.search_panel) in names and str(self.log_panel) in names:
                h = self.search_panel.winfo_height()
                if h > 40:
                    self._sizes["search_h"] = h
            if str(self.info_panel) in self._pane_names(self.right_paned):
                h = self.info_panel.winfo_height()
                if h > 30:
                    self._sizes["info_h"] = h
        except tk.TclError:
            pass

    def _apply_layout(self):
        """Привести набор панелей в соответствие с флагами видимости."""
        for p in (self.search_panel, self.log_panel):
            if str(p) in self._pane_names(self.left_paned):
                self.left_paned.forget(p)
        if self.show_search:
            self.left_paned.add(self.search_panel, height=self._sizes["search_h"], stretch="always")
        if self.show_log:
            self.left_paned.add(self.log_panel, stretch="always")

        left_present = str(self.left_paned) in self._pane_names(self.paned_window)
        need_left = self.show_search or self.show_log
        if need_left and not left_present:
            self.paned_window.add(self.left_paned, before=self.right_paned,
                                  width=self._sizes["left_w"], stretch="never")
        elif not need_left and left_present:
            self.paned_window.forget(self.left_paned)

        info_present = str(self.info_panel) in self._pane_names(self.right_paned)
        if self.show_info and not info_present:
            self.right_paned.add(self.info_panel, height=self._sizes["info_h"], stretch="never")
        elif not self.show_info and info_present:
            self.right_paned.forget(self.info_panel)

        self._sync_toggle_buttons()
        self.root.after_idle(self._place_sashes)

    def _place_sashes(self):
        """Выставить разделители по запомненным размерам."""
        try:
            self.root.update_idletasks()
            if str(self.left_paned) in self._pane_names(self.paned_window):
                total = self.paned_window.winfo_width()
                x = min(self._sizes["left_w"], max(150, total - 300))
                self.paned_window.sash_place(0, int(x), 1)
            if self.show_search and self.show_log:
                total = self.left_paned.winfo_height()
                y = min(self._sizes["search_h"], max(80, total - 80))
                self.left_paned.sash_place(0, 1, int(y))
            if self.show_info:
                total = self.right_paned.winfo_height()
                y = max(150, total - self._sizes["info_h"] - int(self.right_paned.cget("sashwidth")))
                self.right_paned.sash_place(0, 1, int(y))
        except (tk.TclError, ValueError):
            pass

    def _sync_toggle_buttons(self):
        for btn, flag in ((self.tg_search, self.show_search), (self.tg_info, self.show_info),
                          (self.tg_log, self.show_log), (self.mini_btn, self.mini_mode),
                          (self.pin_btn, self.pin_on_top),
                          (self.tg_settings, self._settings_win is not None)):
            btn.set_active(flag)


    def toggle_panel(self, name, force=None):
        """Показать/скрыть панель: search | info | log. force=True — только показать."""
        if self.mini_mode:
            # Любой переключатель в мини-режиме возвращает полный вид
            self.toggle_mini()
            if force or not getattr(self, f"show_{name}"):
                setattr(self, f"show_{name}", True)
                self._apply_layout()
            return
        self._capture_sizes()
        attr = f"show_{name}"
        new_val = True if force else not getattr(self, attr)
        if new_val == getattr(self, attr):
            return
        setattr(self, attr, new_val)
        self._apply_layout()
        if name == "search" and new_val:
            self.search_entry.focus_set()

    def toggle_mini(self):
        """Мини-плеер: только область плеера в компактном окне и обратно."""
        if not self.mini_mode:
            self._capture_sizes()
            zoomed = self.root.state() == "zoomed"
            self._pre_mini = {
                "geometry": self.root.geometry(), "zoomed": zoomed,
                "search": self.show_search, "info": self.show_info, "log": self.show_log,
            }
            if zoomed:
                self.root.state("normal")
            self.show_search = self.show_info = self.show_log = False
            self.mini_mode = True
            self._apply_layout()
            self.root.update_idletasks()
            try:
                if self._mini_geometry:
                    self.root.geometry(self._mini_geometry)
                else:
                    # Сначала ширина, затем (после переноса названия) — высота по содержимому
                    x, y = self.root.winfo_x(), self.root.winfo_y()
                    self.root.geometry(f"620x260+{x}+{y}")
                    self.root.after(120, self._fit_mini_height)
            except tk.TclError:
                pass
        else:
            self._mini_geometry = self.root.geometry()
            pre = self._pre_mini or {"geometry": None, "zoomed": False,
                                     "search": True, "info": True, "log": True}
            self.mini_mode = False
            self.show_search, self.show_info, self.show_log = pre["search"], pre["info"], pre["log"]
            if pre.get("geometry"):
                try:
                    self.root.geometry(pre["geometry"])
                except tk.TclError:
                    pass
            if pre.get("zoomed"):
                self.root.state("zoomed")
            self._pre_mini = None
            self._apply_layout()
        self._sync_toggle_buttons()

    def _fit_mini_height(self):
        if not self.mini_mode:
            return
        self.root.update_idletasks()
        h = self.control_frame.winfo_reqheight() + 12
        self.root.geometry(f"{self.root.winfo_width()}x{h}")

    def toggle_pin(self):
        self.pin_on_top = not self.pin_on_top
        try:
            self.root.attributes("-topmost", self.pin_on_top)
        except tk.TclError:
            pass
        self._sync_toggle_buttons()

    # ══════════════════════ Карточка «Сейчас играет» ══════════════════════
    def _set_now_playing(self, track):
        """Обновить название, источник и обложку-заглушку для трека."""
        self.current_label.config(text=f"{track['title']}")
        try:
            self._source_url = self._get_site_cfg(track)['info'].format(id=track['id'])
        except Exception:
            self._source_url = None
        key = (track.get('id'), track.get('source', 'staroeradio.txt'))
        if key != self._cover_key:
            self._cover_key = key
            self._set_cover(None, placeholder="📻")

    def _on_player_resize(self, event):
        """Обложка растёт, если у плеера есть свободное место по высоте."""
        if event.widget is not self.control_frame:
            return
        try:
            other = (self.progress_frame.winfo_reqheight() + self.btn_frame.winfo_reqheight()
                     + self.bar_frame.winfo_reqheight() + 48)
        except tk.TclError:
            return
        size = int(max(132, min(300, event.height - other, event.width * 0.42)))
        if abs(size - self._cover_size) < 6:
            return
        self._cover_size = size
        self.cover_box.config(width=size, height=size)
        self.cover_label.config(font=(ICON_FONT, max(40, size // 3)))
        if self._cover_bytes:
            self._set_cover(self._cover_bytes)

    def _set_cover(self, image_bytes, placeholder="📻"):
        """Показать обложку (bytes); без неё — data/Staroe_radio.png, а если и его нет — эмодзи."""
        size = self._cover_size
        if not image_bytes:
            image_bytes = self._default_cover()
        self._cover_bytes = image_bytes
        if image_bytes:
            try:
                from PIL import Image, ImageTk
                import io
                img = Image.open(io.BytesIO(image_bytes))
                img = img.convert("RGB")
                w, h = img.size
                k = min(size / w, size / h)
                img = img.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
                self._cover_img = ImageTk.PhotoImage(img)
                self.cover_label.config(image=self._cover_img, text="")
                return
            except Exception:
                pass
        self._cover_img = None
        self._cover_bytes = None
        self.cover_label.config(image="", text=placeholder)

    def _default_cover(self):
        """Картинка-заглушка обложки (читается один раз)."""
        if not hasattr(self, "_default_cover_data"):
            try:
                with open(os.path.join(self.script_dir, "data", "Staroe_radio.png"), "rb") as f:
                    self._default_cover_data = f.read()
            except OSError:
                self._default_cover_data = None
        return self._default_cover_data

    def _open_source_page(self):
        if self._source_url:
            self._open_url(self._source_url)

    def _update_status_line(self):
        """Строка состояния под названием и заголовок окна."""
        try:
            st = self.player.get_state()
        except Exception:
            st = None
        if self.live_mode_active:
            state = "🔴 Прямой эфир" if self.player.is_playing() else "⏹ Эфир остановлен"
        elif st in (vlc.State.Opening, vlc.State.Buffering):
            state = "⏳ Загрузка…"
        elif st == vlc.State.Playing:
            state = "▶ Воспроизведение"
        elif st == vlc.State.Paused:
            state = "⏸ Пауза"
        elif st == vlc.State.Error:
            state = "⚠ Ошибка воспроизведения"
        else:
            state = "⏹ Остановлено"
        if self.state_label.cget("text") != state:
            self.state_label.config(text=state)

        # Заголовок окна — видно на панели задач
        if self.live_mode_active:
            stream = self.live_streams.get(self.current_live_stream, {})
            name = self._live_last_title or stream.get("label", "Прямой эфир")
            title = f"📡 {name}"
        elif self.playing_track:
            mark = "▶" if st == vlc.State.Playing else "⏸"
            t = self.playing_track.get('title', '')
            title = f"{mark} {t}"
        else:
            title = "StaroeRadio Player"
        if title != self._last_title:
            self._last_title = title
            self.root.title(title)

        q = self._download_queue_count
        self.dl_label.config(text=f"⬇ {q}" if q else "")

    # ══════════════════════ Мышь и клавиатура ══════════════════════
    def _on_results_motion(self, event):
        w = self.results_listbox
        w.tag_remove("hover", "1.0", tk.END)
        try:
            line = int(w.index(f"@{event.x},{event.y}").split('.')[0]) - 1
        except (tk.TclError, ValueError):
            return
        if 0 <= line < len(self.current_results) and not self.current_results[line].get('is_date'):
            w.tag_add("hover", f"{line + 1}.0", f"{line + 2}.0")

    def _on_volume_wheel(self, event):
        step = 5 if event.delta > 0 else -5
        self.volume_var.set(max(0, min(100, int(self.volume_var.get()) + step)))
        self.set_volume()
        return "break"

    def _on_progress_wheel(self, event):
        self.seek_relative(10 if event.delta > 0 else -10)
        return "break"

    def seek_relative(self, seconds):
        if self.live_mode_active:
            return
        try:
            length = self.player.get_length()
            if length > 0:
                t = max(0, min(length - 1000, self.player.get_time() + seconds * 1000))
                self.player.set_time(int(t))
                self.time_current.config(text=self.format_time(int(t) // 1000))
                self.progress_slider.set(t / length * 100)
        except Exception:
            pass

    def toggle_mute(self):
        if self._muted_volume is None:
            self._muted_volume = int(self.volume_var.get()) or 80
            self.volume_var.set(0)
        else:
            self.volume_var.set(self._muted_volume)
            self._muted_volume = None
        self.set_volume()

    def _on_hotkey(self, event):
        """Горячие клавиши главного окна. Работают по физической клавише (keycode),
        поэтому не зависят от раскладки."""
        try:
            if event.widget.winfo_toplevel() is not self.root:
                return None
        except Exception:
            return None
        ctrl = bool(event.state & 0x4)
        cls = event.widget.winfo_class()
        typing = cls in ("Entry", "TEntry", "TCombobox", "TSpinbox", "Spinbox")
        latin = event.keysym.lower() in ("v", "c", "x", "a", "z")

        if ctrl:
            kc = event.keycode
            if kc == 70:                                  # Ctrl+F — к поиску
                self.toggle_panel("search", force=True)
                self.search_entry.focus_set()
                self.search_entry.select_range(0, tk.END)
                return "break"
            if kc in (49, 50, 51):                        # Ctrl+1/2/3
                self.toggle_panel({49: "search", 50: "log", 51: "info"}[kc])
                return "break"
            if kc == 77:                                  # Ctrl+M — мини-плеер
                self.toggle_mini()
                return "break"
            if kc == 86 and not latin and event.widget == self.search_entry:
                return self.paste(event)                  # Ctrl+V в русской раскладке
            if kc == 67 and not latin and isinstance(event.widget, tk.Text):
                return self._copy_selection(event.widget)  # Ctrl+C в русской раскладке
            return None

        if typing:
            return None
        ks = event.keysym
        if ks == "space":
            self.pause()
            return "break"
        if ks == "Right":
            self.seek_relative(10)
            return "break"
        if ks == "Left":
            self.seek_relative(-10)
            return "break"
        if ks in ("Up", "Down"):
            step = 5 if ks == "Up" else -5
            self.volume_var.set(max(0, min(100, int(self.volume_var.get()) + step)))
            self.set_volume()
            return "break"
        return None

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.status_label.config(text="")


    # ══════════════════════ Список: выбор и воспроизведение ══════════════════════
    @staticmethod
    def _track_key(track):
        return (track.get('id'), track.get('source', 'staroeradio.txt'))

    def _same_track(self, a, b):
        return bool(a and b) and self._track_key(a) == self._track_key(b)

    def _line_at(self, event):
        try:
            line = int(self.results_listbox.index(f"@{event.x},{event.y}").split('.')[0]) - 1
        except (tk.TclError, ValueError):
            return -1
        if 0 <= line < len(self.current_results) and not self.current_results[line].get('is_date'):
            return line
        return -1

    def _refresh_row_tags(self, see=False):
        """Подсветка: выделенная строка (фон) и играющий трек (цвет текста)."""
        w = self.results_listbox
        w.tag_remove("selected", "1.0", tk.END)
        w.tag_remove("playing", "1.0", tk.END)
        if 0 <= self.selected_index < len(self.current_results):
            # до начала следующей строки — фон выделения на всю ширину
            w.tag_add("selected", f"{self.selected_index + 1}.0", f"{self.selected_index + 2}.0")
            if see:
                w.see(f"{self.selected_index + 1}.0")
        ci = self.current_index
        if (0 <= ci < len(self.current_results) and self.playing_track
                and self._same_track(self.current_results[ci], self.playing_track)):
            w.tag_add("playing", f"{ci + 1}.0", f"{ci + 1}.end")
        w.tag_raise("selected")
        w.tag_raise("playing")

    def on_listbox_click(self, event):
        """Один клик — только выбор трека и загрузка его описания."""
        line = self._line_at(event)
        if line < 0:
            return
        self.selected_index = line
        self._refresh_row_tags()
        self.load_track_info(self.current_results[line])

    def on_listbox_double(self, event):
        """Двойной клик — воспроизведение."""
        line = self._line_at(event)
        if line >= 0:
            self._play_line(line)
        return "break"   # без выделения слова двойным кликом

    def _play_line(self, line):
        if not (0 <= line < len(self.current_results)) or self.current_results[line].get('is_date'):
            return
        track = self.current_results[line]
        if not self.live_mode_active and self._same_track(track, self.playing_track):
            # Этот трек уже играет — не перезапускаем; с паузы — продолжаем
            self.current_index = line
            if self.player.get_state() == vlc.State.Paused:
                self.pause()
            self._refresh_row_tags()
            return
        self.current_index = line
        self._play_and_info()

    def load_track_info(self, track):
        """Загрузить описание трека (из кэша сразу, иначе в фоне).
        Отображается только результат последнего запроса."""
        self._info_req += 1
        token = self._info_req
        cached = self._info_cache.get(self._track_key(track))
        if cached:
            description, image_links, page_links, images_data = cached
            self._display_track_info(track['id'], description, image_links, page_links,
                                     track.get('source', 'staroeradio.txt'), images_data,
                                     track=track, token=token)
            return
        threading.Thread(target=self._fetch_track_info, args=(track, token), daemon=True).start()

    def _on_title_click(self, event=None):
        """Клик по названию в плеере — описание играющей передачи."""
        if self.live_mode_active:
            track = getattr(self, "_live_track", None)
            if not track:
                return
            if not self.show_info:
                self.toggle_panel("info", force=True)
            self.load_track_info(track)
            return
        track = self.playing_track
        if not track:
            if 0 <= self.current_index < len(self.current_results):
                track = self.current_results[self.current_index]
            else:
                return
        if not self.show_info:
            self.toggle_panel("info", force=True)
        ci = self.current_index
        if 0 <= ci < len(self.current_results) and self._same_track(self.current_results[ci], track):
            self.selected_index = ci
            self._refresh_row_tags(see=True)
        self.load_track_info(track)

    # ══════════════════════ Перемотка ══════════════════════
    def _seek_press(self, ratio):
        if self.live_mode_active or self.player.get_length() <= 0:
            return False
        self.user_seeking = True
        self._seek_preview(ratio)

    def _seek_preview(self, ratio):
        total = self.player.get_length()
        if total > 0:
            self.time_current.config(text=self.format_time(int(ratio * total / 1000)))

    def _seek_release(self, ratio):
        if self.player.get_length() > 0:
            self.player.set_position(ratio)
        self.user_seeking = False

    def refresh_files(self):
        data_dir = os.path.join(self.script_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        txt_files = glob.glob(os.path.join(data_dir, "*.txt"))
        self.txt_files = txt_files

        if txt_files:
            self.log(f"📁 Найдено файлов: {len(txt_files)}")
            # self.file_count_label.config(text=f"Файлов: {len(txt_files)}")
        else:
            self.log("❌ TXT файлы не найдены!")
            self.file_count_label.config(text="Нет TXT файлов")

    def search(self):
        query = self.search_entry.get().strip()

        if not query:
            messagebox.showwarning("Ошибка", "Введите поисковый запрос!")
            return

        if not self.txt_files:
            messagebox.showwarning("Ошибка", "Нет TXT файлов для поиска!")
            return

        self.log(f"🔍 Поиск: '{query}'")

        search_words = query.lower().split()
        results = []

        for file_path in self.txt_files:
            try:
                filename = os.path.basename(file_path)
                with open(file_path, 'r', encoding='utf-8') as file:
                    for line in file:
                        line = line.strip()

                        if not line:
                            continue

                        line_lower = line.lower()

                        if all(word in line_lower for word in search_words):

                            if '\t' in line:
                                parts = line.split('\t', 1)
                                audio_id = parts[0]
                                title = parts[1]
                            else:
                                parts = line.split(None, 1)
                                audio_id = parts[0] if parts else ""
                                title = parts[1] if len(parts) > 1 else line

                            results.append({
                                'id': audio_id,
                                'title': title,
                                'source': filename,
                            })

            except Exception as e:
                self.log(f"❌ Ошибка чтения {file_path}: {e}")

        # staroeradio.txt — приоритетный источник, выводим первым
        results.sort(key=lambda r: 0 if r['source'] == 'staroeradio.txt' else 1)

        self.current_results = results
        self.current_index = next((i for i, r in enumerate(results)
                                   if self.playing_track and self._same_track(r, self.playing_track)), -1)
        self.update_results_list()

        if results:
            self.log(f"✅ Найдено: {len(results)} треков")
        else:
            self.log("❌ Совпадений не найдено")

    def update_results_list(self):
        self.results_listbox.config(state=tk.NORMAL)
        self.results_listbox.delete(1.0, tk.END)

        track_num = 0
        for item in self.current_results:
            if item.get('is_date'):
                self.results_listbox.insert(tk.END, item['title'] + "\n", "date_header")
            elif item.get('time'):
                # Трек из программы передач — время серым, без нумерации
                self.results_listbox.insert(tk.END, item['time'] + "  ", "time_text")
                self.results_listbox.insert(tk.END, item['title'] + "\n", "title")
            else:
                track_num += 1
                self.results_listbox.insert(tk.END, f"{track_num:3}. ", "number")
                self.results_listbox.insert(tk.END, item['title'] + "\n", "title")

        self.results_listbox.config(state=tk.DISABLED)
        self.results_listbox.yview_moveto(0)
        self.selected_index = -1
        self._refresh_row_tags()
        n = sum(1 for r in self.current_results if not r.get('is_date'))
        self.file_count_label.config(text=f"{n} {_plural(n, ('трек', 'трека', 'треков'))}" if n else "")

    def highlight_selected_line(self):
        """Выделение следует за играющим треком (при переходах и восстановлении)."""
        self.selected_index = self.current_index
        self._refresh_row_tags(see=True)

    def play_selected(self):
        self._play_line(self.selected_index)

    def _get_site_cfg(self, track):
        """Вернуть конфиг сайта для трека по полю source."""
        source = track.get('source', 'staroeradio.txt')
        return self.site_config.get(source, self.site_config['staroeradio.txt'])

    def play_current(self):
        if self.current_index < 0 or self.current_index >= len(self.current_results):
            return
        
        self.auto_play_enabled = True # Сброс флага при новом воспроизведении

        track = self.current_results[self.current_index]

        # Добавляем в стек истории воспроизведения (не дублируем подряд один и тот же трек)
        if not self.playback_history or self.playback_history[-1].get('id') != track.get('id'):
            self.playback_history.append(track)
            # Ограничиваем стек 200 треками
            if len(self.playback_history) > 200:
                self.playback_history = self.playback_history[-200:]

        self._play_track_direct(track)

    def _play_track_direct(self, track):
        """Воспроизвести трек напрямую (без добавления в стек истории)."""
        self.live_mode_active = False  # Выходим из режима прямого эфира при выборе обычного трека
        self._live_track = None
        self._stop_icy_metadata_thread()
        self.playing_track = track  # Запоминаем реально проигрываемый трек независимо от списка результатов

        cfg = self._get_site_cfg(track)
        url = cfg['stream'].format(id=track['id'])

        self.log(f"▶ Воспроизведение: {track['title']}")

        self._log_to_history(track)

        self._set_now_playing(track)

        media = self.instance.media_new(url)

        media.add_option(":http-user-agent=Mozilla/5.0")

        self.player.stop()

        self.player.set_media(media)

        time.sleep(0.1)

        self.player.play()

        self.player.audio_set_volume(self.volume_var.get())

        self.is_playing = True
        self.play_pause_btn.config(text="⏸️")
        self._refresh_row_tags()

    def pause(self):
        if self.live_mode_active:
            # Для прямого эфира нет осмысленной паузы — останавливаем/перезапускаем поток
            if self.player.is_playing():
                self.player.stop()
                self.is_playing = False
                self.play_pause_btn.config(text="▶️")
                self.log("⏸ Эфир остановлен")
                self._stop_icy_metadata_thread()
            else:
                self.play_live_stream(self.current_live_stream)
            return

        if self.player.is_playing():
            self.player.pause()
            self.is_playing = False
            self.play_pause_btn.config(text="▶️")
            self.log("⏸ Пауза")

        elif self.player.get_state() == vlc.State.Paused:
            self.player.play()
            self.is_playing = True
            self.play_pause_btn.config(text="⏸️")
            self.log("▶ Возобновлено")

    def stop(self):
        self.player.stop()
        self.is_playing = False
        self.playing_track = None
        self.live_mode_active = False
        self._stop_icy_metadata_thread()
        self.play_pause_btn.config(text="▶️")
        self.auto_play_enabled = False  # Отключаем автовоспроизведение при ручной остановке
        self.current_label.config(text="Нет трека")
        self.progress_slider.set(0)
        self.time_current.config(text="00:00")
        self.time_total.config(text="00:00")
        self.log("⏹ Остановлено")
        self._refresh_row_tags()
        # Включаем обратно через небольшую задержку, чтобы событие окончания не сработало
        self.root.after(500, lambda: setattr(self, 'auto_play_enabled', True))  

    # ══════════════════════ Прямой эфир ══════════════════════
    def _on_live_btn_click(self):
        """ЛКМ по кнопке эфира — текущий поток. Запуск чуть откладывается,
        чтобы двойной клик не запускал сначала текущий поток."""
        if self._live_dbl:              # отпускание второго клика двойного — пропускаем
            self._live_dbl = False
            return
        if self._live_click_job:
            self.root.after_cancel(self._live_click_job)
        self._live_click_job = self.root.after(
            280, lambda: (setattr(self, "_live_click_job", None),
                          self.play_live_stream(self.current_live_stream)))

    def _on_live_btn_double(self, event=None):
        """Двойной клик — следующий поток по кругу."""
        if self._live_click_job:
            self.root.after_cancel(self._live_click_job)
            self._live_click_job = None
        self._live_dbl = True
        keys = list(self.live_streams)
        i = keys.index(self.current_live_stream) if self.current_live_stream in keys else -1
        self.play_live_stream(keys[(i + 1) % len(keys)])

    def _show_live_menu(self, event):
        """ПКМ по кнопке эфира — меню выбора потока."""
        menu = tk.Menu(self.root, tearoff=0)
        for key, stream in self.live_streams.items():
            menu.add_command(
                label=f"{stream['icon']} {stream['label']}",
                command=lambda k=key: self.play_live_stream(k)
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _update_live_button_icon(self):
        stream = self.live_streams.get(self.current_live_stream)
        if stream:
            self.live_btn.config(text=stream["icon"])

    def play_live_stream(self, key):
        """Запустить прямой эфир по ключу потока (music/kids/old)."""
        stream = self.live_streams.get(key)
        if not stream:
            return

        self.current_live_stream = key
        self.live_mode_active = True
        self.playing_track = None
        self.auto_play_enabled = False  # автопереход треков не нужен в режиме эфира
        self._live_last_title = None
        self._live_track = None

        self._update_live_button_icon()

        self.log(f"📡 Прямой эфир: {stream['label']}")

        media = self.instance.media_new(stream["url"])
        media.add_option(":http-user-agent=Mozilla/5.0")

        self.player.stop()
        self.player.set_media(media)

        time.sleep(0.1)

        self.player.play()
        self.player.audio_set_volume(self.volume_var.get())

        self.is_playing = True
        self.play_pause_btn.config(text="⏸️")
        self.current_label.config(text=f"{stream['icon']} {stream['label']}")
        self._source_url = "https://staroeradio.ru/"
        self._cover_key = ("live", key)
        self._set_cover(None, placeholder=stream["icon"])

        # libVLC не отдаёт ICY-метаданные этих потоков (проверено и в самом VLC),
        # поэтому читаем их отдельным соединением, как это делает AIMP
        self._start_icy_metadata_thread(stream["url"])

        self.save_state()

    def _start_icy_metadata_thread(self, url):
        """Запустить фоновый поток чтения ICY-метаданных (StreamTitle) для потока url."""
        self._stop_icy_metadata_thread()
        stop_event = threading.Event()
        self._icy_stop_event = stop_event
        t = threading.Thread(target=self._icy_metadata_worker, args=(url, stop_event), daemon=True)
        t.start()
        self._icy_thread = t

    def _stop_icy_metadata_thread(self):
        if getattr(self, '_icy_stop_event', None):
            self._icy_stop_event.set()
        self._icy_stop_event = None

    def _icy_metadata_worker(self, url, stop_event):
        """Отдельное HTTP-соединение только для чтения ICY-метаданных (аудио отбрасывается)."""
        resp = None
        try:
            req = urllib.request.Request(
                url,
                headers={"Icy-MetaData": "1", "User-Agent": "Mozilla/5.0"}
            )
            resp = urllib.request.urlopen(req, timeout=10)
            metaint = int(resp.headers.get("icy-metaint", 0) or 0)
            if not metaint:
                return

            while not stop_event.is_set():
                remaining = metaint
                while remaining > 0:
                    if stop_event.is_set():
                        return
                    chunk = resp.read(min(remaining, 8192))
                    if not chunk:
                        return
                    remaining -= len(chunk)

                length_byte = resp.read(1)
                if not length_byte:
                    return
                length = length_byte[0] * 16

                if length > 0:
                    meta_bytes = resp.read(length)
                    if not meta_bytes:
                        return
                    meta_text = meta_bytes.rstrip(b"\x00").decode("utf-8", errors="ignore")
                    m = re.search(r"StreamTitle='(.*?)';", meta_text)
                    if m:
                        title = m.group(1).strip()
                        if title:
                            self.root.after(0, lambda t=title: self._handle_icy_title(t))
        except Exception:
            pass
        finally:
            try:
                if resp:
                    resp.close()
            except Exception:
                pass

    def _handle_icy_title(self, title):
        if not self.live_mode_active:
            return
        if title == self._live_last_title:
            return
        self._live_last_title = title

        stream = self.live_streams.get(self.current_live_stream, {})
        icon = stream.get("icon", "📻")
        label = stream.get("label", "Прямой эфир")

        self.current_label.config(text=f"{icon} {label}\n{title}")
        self.log(f"🎶 {title}")

        # Для «Старого радио» ищем передачу в программе/базе — обложка и описание
        self._live_track = None
        self._cover_key = ("live", title)
        self._set_cover(None, placeholder=icon)
        if self.current_live_stream == "old":
            key = self.current_live_stream
            threading.Thread(target=self._resolve_live_worker, args=(title, key), daemon=True).start()

    # ── Поиск передачи прямого эфира по названию ───────────────
    def _program_cached(self, max_age=1800):
        """Программа передач (кэш на 30 минут). Пустой список при ошибке."""
        cache = getattr(self, "_program_cache", None)
        if cache and time.time() - cache[0] < max_age:
            return cache[1]
        try:
            results = self._download_program()
        except Exception:
            results = cache[1] if cache else []
        self._program_cache = (time.time(), results)
        return results

    def _db_index(self):
        """Индекс data/staroeradio.txt: нормализованное название → (id, название).
        Перестраивается, только если файл изменился."""
        path = os.path.join(self.script_dir, "data", "staroeradio.txt")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return {}
        cache = getattr(self, "_db_index_cache", None)
        if cache and cache[0] == mtime:
            return cache[1]
        index = {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split('\t', 1) if '\t' in line else line.split(None, 1)
                    if len(parts) == 2 and parts[0].isdigit():
                        index.setdefault(_norm_title(parts[1]), (parts[0], parts[1]))
        except Exception:
            return {}
        self._db_index_cache = (mtime, index)
        return index

    def _resolve_live_worker(self, title, stream_key):
        """Фоновый поток: найти ID передачи эфира по названию."""
        norm = _norm_title(title)
        found, where = None, ""
        if norm:
            # 1. Программа передач — там ровно то, что идёт в эфире, с ID
            if HAS_BS4:
                prog = [r for r in self._program_cached() if r.get('id') and not r.get('is_date')]
                for r in prog:
                    if _norm_title(r['title']) == norm:
                        found, where = (r['id'], r['title']), "программа"
                        break
                if not found and len(norm) >= 15:      # название в эфире могло быть обрезано
                    for r in prog:
                        if _norm_title(r['title']).startswith(norm):
                            found, where = (r['id'], r['title']), "программа"
                            break
            # 2. Локальная база
            if not found:
                index = self._db_index()
                found = index.get(norm)
                if not found and len(norm) >= 15:
                    found = next((v for k, v in index.items() if k.startswith(norm)), None)
                where = "база" if found else ""
        self.root.after(0, lambda: self._apply_live_track(title, stream_key, found, where))

    def _apply_live_track(self, title, stream_key, found, where):
        # Пока искали, эфир могли выключить или сменилась передача
        if not (self.live_mode_active and self.current_live_stream == stream_key
                and self._live_last_title == title):
            return
        if not found:
            self.log("ℹ️ Передача из эфира не найдена ни в программе, ни в базе")
            return
        track = {'id': found[0], 'title': found[1], 'source': 'staroeradio.txt'}
        self._live_track = track
        self._cover_key = self._track_key(track)
        self._source_url = self._get_site_cfg(track)['info'].format(id=track['id'])
        self.log(f"🔎 Эфир: ID {track['id']} ({where})")
        self.load_track_info(track)

    def _play_and_info(self):
        """Воспроизвести текущий трек, обновить выделение и загрузить описание."""
        self.highlight_selected_line()
        self.play_current()
        if 0 <= self.current_index < len(self.current_results):
            track = self.current_results[self.current_index]
            self.load_track_info(track)

    def next_track(self):
        if self.current_results and self.current_index + 1 < len(self.current_results):
            self.current_index += 1
            self._play_and_info()
        else:
            self.log("📋 Это последний трек в списке")

    def on_track_end(self, event):
        """Автоматический переход к следующему треку при окончании текущего"""
        if self.live_mode_active:
            return
        if self.auto_play_enabled:
            self.root.after(0, self.auto_next_track)

    def auto_next_track(self):
        """Автоматическое воспроизведение следующего трека"""
        if self.current_results and self.current_index + 1 < len(self.current_results):
            self.current_index += 1
            self.log("⏭ Автопереход к следующему треку")
            self._play_and_info()
        elif self.current_results and self.current_index + 1 >= len(self.current_results):
            self.log("📋 Достигнут конец плейлиста")
            self.stop()

    def prev_track(self):
        # Если в стеке истории воспроизведения есть предыдущий трек — играем его
        if len(self.playback_history) >= 2:
            # Убираем текущий трек из стека
            self.playback_history.pop()
            prev = self.playback_history[-1]
            # Ищем трек в текущих результатах
            found_idx = None
            for i, t in enumerate(self.current_results):
                if not t.get('is_date') and t.get('id') == prev.get('id'):
                    found_idx = i
                    break
            if found_idx is not None:
                self.current_index = found_idx
                self.highlight_selected_line()
            else:
                self.current_index = -1
            # Воспроизводим напрямую, без добавления в стек (уже там)
            self._play_track_direct(prev)
            self.load_track_info(prev)
        else:
            self.log("📋 Нет предыдущего трека в истории воспроизведения")

    def set_volume(self, *args):
        volume = int(float(self.volume_var.get()))
        self.player.audio_set_volume(volume)
        self.volume_label.config(text=f"{volume}%")
        icon = "🔇" if volume == 0 else ("🔈" if volume < 34 else ("🔉" if volume < 67 else "🔊"))
        self.vol_icon_label.config(text=icon)
        if volume > 0:
            self._muted_volume = None

    def update_position(self):
        try:
            self._update_status_line()
        except Exception:
            pass
        try:
            if self.player.is_playing():

                if self.live_mode_active:
                    if not self.user_seeking:
                        self.progress_slider.set(0)
                    self.time_current.config(text="🔴 LIVE")
                    self.time_total.config(text="--:--")
                    self.root.after(1000, self.update_position)
                    return

                current_time = self.player.get_time() // 1000
                total_time = self.player.get_length() // 1000

                if total_time > 0:
                    position = (current_time / total_time) * 100

                    if not self.user_seeking:
                        self.progress_slider.set(position)

                self.time_current.config(
                    text=self.format_time(current_time)
                )

                self.time_total.config(
                    text=self.format_time(total_time)
                )

        except Exception as e:
            self.log(f"❌ Ошибка обновления позиции: {e}")

        self.root.after(1000, self.update_position)

    def format_time(self, seconds):
        seconds = max(0, int(seconds))
        h, rest = divmod(seconds, 3600)
        m, s = divmod(rest, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def _choose_save_dir(self):
        """Папка Staroe_radio_downloads внутри папки из Настроек.
        Если в Настройках включено «Спрашивать каждый раз» (или папки нет) — диалог выбора.
        Возвращает путь или None при отмене."""
        base = self.last_save_dir
        if self.ask_save_dir or not base:
            chosen = filedialog.askdirectory(initialdir=base or os.path.expanduser("~"),
                                             title="Выберите папку для сохранения")
            if not chosen:
                return None
            base = self.last_save_dir = chosen

        staroe_radio_dir = os.path.join(base, "Staroe_radio_downloads")
        try:
            os.makedirs(staroe_radio_dir, exist_ok=True)
        except Exception as e:
            self.log(f"❌ Не удалось создать папку {staroe_radio_dir}: {e}  (проверьте Настройки → Общие)")
            return None
        return staroe_radio_dir

    def _open_folder(self, path=None):
        path = path or self.last_save_dir
        sub = os.path.join(path, "Staroe_radio_downloads")
        target = sub if os.path.isdir(sub) else path
        try:
            if sys.platform == "win32":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as e:
            self.log(f"❌ Не удалось открыть папку: {e}")

    def save_m3u(self):
        if not self.current_results:
            messagebox.showwarning("Ошибка", "Нет результатов для сохранения!")
            return

        staroe_radio_dir = self._choose_save_dir()
        if not staroe_radio_dir:
            return

        query = self.search_entry.get().strip()

        if not query:
            query = "search"

        safe_query = "".join(
            c for c in query
            if c.isalnum() or c in (' ', '-', '_')
        ).strip()

        safe_query = safe_query[:50]

        if not safe_query:
            safe_query = "playlist"

        # Для всех результатов поиска создаём подпапку с названием поискового запроса
        query_dir = os.path.join(staroe_radio_dir, safe_query)
        try:
            os.makedirs(query_dir, exist_ok=True)
        except Exception as e:
            self.log(f"❌ Ошибка создания папки: {e}")
            return

        m3u_filename = f"{safe_query}.m3u"

        m3u_filepath = os.path.join(
            query_dir,
            m3u_filename
        )

        try:
            with open(m3u_filepath, 'w', encoding='utf-8') as f:

                f.write("#EXTM3U\n")
                f.write(f"#PLAYLIST:{query}\n\n")

                for item in self.current_results:
                    if item.get('is_date'):
                        continue
                    cfg = self._get_site_cfg(item)
                    url = cfg['stream'].format(id=item['id'])
                    f.write(f"#EXTINF:-1,{item['title']}\n")
                    f.write(f"{url}\n\n")

            self.log(
                f"✅ Плейлист сохранен: "
                f"{m3u_filename} "
                f"({len(self.current_results)} треков)"
            )

        except Exception as e:
            self.log(f"❌ Ошибка сохранения: {e}")

            messagebox.showerror(
                "Ошибка",
                f"Не удалось сохранить плейлист:\n{e}"
            )

    def _save_track_to_m3u(self, track):
        """Сохранить один трек в отдельный плейлист с названием трека"""
        staroe_radio_dir = self._choose_save_dir()
        if not staroe_radio_dir:
            return

        # Имя файла = название трека
        safe_name = "".join(
            c for c in track['title']
            if c.isalnum() or c in (' ', '-', '_', '.')
        ).strip()[:80] or track['id']

        m3u_filepath = os.path.join(staroe_radio_dir, f"{safe_name}.m3u")

        cfg = self._get_site_cfg(track)
        url = cfg['stream'].format(id=track['id'])

        with open(m3u_filepath, 'w', encoding='utf-8') as f:
            f.write(f"#EXTM3U\n#PLAYLIST:{track['title']}\n\n")
            f.write(f"#EXTINF:-1,{track['title']}\n{url}\n\n")

        self.log(f"💾 Сохранён плейлист: {safe_name}.m3u")

    # Год записи ищем по 4 цифрам перед "г." / "гг." (после "Зап.: ..."), например:
    # "1977г.", "сентябрь 1967г.", "04.03.1987г.", "1940-х гг." — из последнего берём начало десятилетия
    _YEAR_RE = re.compile(r'(?<!\d)(\d{4})(?:-х)?\s*гг?\.')

    def _extract_year_from_title(self, title):
        """Вытащить год записи из названия трека, если он там указан."""
        if not title:
            return None
        m = self._YEAR_RE.search(title)
        if m:
            return m.group(1)
        return None

    def smart_truncate(self, text, max_length=50):
        """
        Умная обрезка текста до max_length символов.
        Если последнее слово не вмещается целиком, обрезает до предпоследнего целого слова.
        """
        if len(text) <= max_length:
            return text

        # Обрезаем до max_length
        truncated = text[:max_length]

        # Ищем последний пробел
        last_space = truncated.rfind(' ')

        if last_space > 0:
            # Обрезаем до последнего пробела
            return truncated[:last_space]
        else:
            # Если пробелов нет, просто обрезаем до max_length
            return truncated

    def download_playing_mp3(self):
        """Скачать реально воспроизводимый трек (по playing_track, не по курсору)"""
        track = self.playing_track
        if not track:
            # Нет воспроизводимого трека — пробуем выделенный в списке
            self.download_selected_mp3()
            return
        self._download_mp3([track], is_single=True)

    def download_selected_mp3(self):
        """Скачать только выбранный трек"""
        # Получаем позицию курсора в Text виджете
        try:
            cursor_pos = self.results_listbox.index(tk.INSERT)
            line_num = int(cursor_pos.split('.')[0]) - 1
            
            if 0 <= line_num < len(self.current_results):
                selected_item = self.current_results[line_num]
                self._download_mp3([selected_item], is_single=True)
            else:
                messagebox.showwarning("Ошибка", "Выберите трек из списка!")
        except:
            messagebox.showwarning("Ошибка", "Выберите трек из списка!")

    def download_all_mp3(self):
        """Скачать все треки из результатов поиска"""
        if not self.current_results:
            messagebox.showwarning("Ошибка", "Нет результатов для скачивания!")
            return

        self._download_mp3(self.current_results, is_single=False)

    def _download_mp3(self, items, is_single=False):
        """Выбрать папку (на главном потоке) и запустить скачивание MP3 в фоновом потоке."""
        staroe_radio_dir = self._choose_save_dir()
        if not staroe_radio_dir:
            return

        if is_single:
            # Одиночный трек сохраняется прямо в Staroe_radio
            download_dir = staroe_radio_dir
        else:
            # Все результаты поиска — в подпапку с названием поискового запроса
            query = self.search_entry.get().strip() or "search"
            safe_query = "".join(
                c for c in query
                if c.isalnum() or c in (' ', '-', '_')
            ).strip()[:50] or "downloads"
            download_dir = os.path.join(staroe_radio_dir, safe_query)

        try:
            os.makedirs(download_dir, exist_ok=True)
        except Exception as e:
            self.log(f"❌ Ошибка создания папки: {e}")
            return

        with self._download_lock:
            self._download_queue_count += len(items)
            total_in_queue = self._download_queue_count
        self._safe_log(f"➕ В очередь на скачивание добавлено: {len(items)} (всего в очереди: {total_in_queue})")

        threading.Thread(target=self._download_mp3_thread, args=(items, download_dir), daemon=True).start()

    def _download_mp3_thread(self, items, download_dir):
        """Внутренняя функция для скачивания MP3 файлов (выполняется в фоновом потоке)"""
        # Проверяем наличие mutagen
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import TIT2, COMM, APIC, TDRC, TYER
        except ImportError:
            self._safe_log("⚠️  Mutagen не установлен, теги не будут добавлены")
            has_mutagen = False
        else:
            has_mutagen = True

        # Скачиваем файлы
        saved_count = 0
        error_count = 0

        for item in items:
            try:
                # Создаем имя файла: ID_название (умная обрезка до 50 символов)
                title_short = self.smart_truncate(item['title'], max_length=50)
                # Очищаем неподходящие символы
                title_short = "".join(
                    c for c in title_short
                    if c.isalnum() or c in (' ', '-', '_', '.')
                ).strip()

                filename = f"{item['id']}_{title_short}.mp3"
                filepath = os.path.join(download_dir, filename)

                # Пропускаем, если файл уже существует
                if os.path.exists(filepath):
                    self._safe_log(f"⏭️  Файл уже существует: {filename}")
                    saved_count += 1
                    continue

                # Скачиваем файл
                cfg = self._get_site_cfg(item)
                url = cfg['stream'].format(id=item['id'])

                # Логируем название и считаем размер по длине трека (128 кбит/с)
                self._safe_log(f"⬇️ Скачиваем: {item['title'][:60]}")
                length_ms = self.player.get_length() if (self.playing_track and self.playing_track.get('id') == item['id']) else 0
                if length_ms > 0:
                    size_mb = (length_ms / 1000) * 128 * 1024 / 8 / (1024 * 1024)
                    self._safe_log(f"📦 Размер: ~{size_mb:.1f} МБ")

                try:
                    urllib.request.urlretrieve(url, filepath)
                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    self._safe_log(f"⚠️  Не удалось скачать {filename}: {e}")
                    error_count += 1
                    continue

                # Добавляем теги ID3
                if has_mutagen:
                    try:
                        audio = MP3(filepath)
                        if audio.tags is None:
                            audio.add_tags()

                        audio.tags["TIT2"] = TIT2(encoding=3, text=[item['title']])

                        # Год записи, если он указан в названии трека
                        year = self._extract_year_from_title(item['title'])
                        if year:
                            audio.tags.add(TDRC(encoding=3, text=[year]))
                            audio.tags.add(TYER(encoding=3, text=[year]))

                        # Описание передачи и обложка со страницы трека (если есть)
                        description, image_links, _, _ = self._scrape_track_page(item)

                        if description:
                            audio.tags.add(COMM(encoding=3, lang='rus', desc='', text=[description]))

                        if image_links:
                            try:
                                img_url = image_links[0]
                                img_req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(img_req, timeout=10) as img_resp:
                                    img_data = img_resp.read()

                                lower_url = img_url.lower()
                                if lower_url.endswith('.png'):
                                    mime = 'image/png'
                                elif lower_url.endswith('.gif'):
                                    mime = 'image/gif'
                                else:
                                    mime = 'image/jpeg'

                                audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc='Cover', data=img_data))
                            except Exception as e:
                                self._safe_log(f"⚠️  Не удалось добавить обложку для {filename}: {e}")

                        audio.save()
                    except Exception as e:
                        self._safe_log(f"⚠️  Ошибка добавления тега для {filename}: {e}")

                saved_count += 1
                self._safe_log(f"✅ Сохранен: {filename}")

            except Exception as e:
                self._safe_log(f"❌ Ошибка при обработке {item['id']}: {e}")
                error_count += 1

            finally:
                with self._download_lock:
                    self._download_queue_count = max(0, self._download_queue_count - 1)
                    remaining = self._download_queue_count
                self._safe_log(f"📊 В очереди на скачивание: {remaining}")

        # Итоговое сообщение
        self._safe_log(f"📁 Скачивание завершено: сохранено {saved_count}, ошибок {error_count}, папка: {download_dir}")


    def paste(self, event=None):
        """Вставка из буфера в поле поиска"""
        try:
            text = self.root.clipboard_get()
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, text)
            self.search_entry.focus()
        except Exception:
            pass
        if event:
            return "break"

    def paste_root(self, event=None):
        """Глобальная вставка из буфера"""
        self.paste(event)
        if event:
            return "break"

    def _global_paste(self, event=None):
        """Ctrl+V глобально: если фокус на search_entry — вставляем туда, иначе игнорируем"""
        focused = self.root.focus_get()
        if focused == self.search_entry:
            return self.paste(event)
        # Для других виджетов не перехватываем — пусть работает стандартно
        return None

    def _bind_context_menu(self, widget, can_paste=False, can_copy=True, is_label=False):
        """Привязать контекстное меню к виджету."""
        is_entry = isinstance(widget, ttk.Entry)

        def show_menu(event):
            menu = tk.Menu(self.root, tearoff=0)
            if is_entry and can_paste:
                menu.add_command(label="Вставить", command=self.paste)
                if can_copy:
                    menu.add_separator()
            if can_copy:
                if is_label:
                    menu.add_command(label="Копировать", command=lambda: self._copy_label(widget))
                elif is_entry:
                    menu.add_command(label="Копировать", command=lambda: self._copy_entry(widget))
                else:
                    menu.add_command(label="Копировать", command=lambda: self._copy_selection(widget))
                    menu.add_command(label="Копировать всё", command=lambda: self._copy_all(widget))
            if can_paste and not is_entry:
                if can_copy:
                    menu.add_separator()
                menu.add_command(label="Вставить", command=self.paste)
            if menu.index("end") is not None:
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()
        widget.bind("<Button-3>", show_menu)

    def _bind_results_context_menu(self, widget):
        """Контекстное меню для списка результатов поиска."""
        def show_menu(event):
            pos = widget.index(f"@{event.x},{event.y}")
            line_num = int(pos.split('.')[0]) - 1

            menu = tk.Menu(self.root, tearoff=0)

            if 0 <= line_num < len(self.current_results):
                track = self.current_results[line_num]
                if not track.get('is_date'):
                    menu.add_command(label="▶ Воспроизвести", command=lambda n=line_num: self._play_line(n))
                    menu.add_separator()
                label = f"💿 Скачать: {track['title'][:40]}{'…' if len(track['title']) > 40 else ''}"
                label_m3u = f"💾 Сохранить: {track['title'][:40]}{'…' if len(track['title']) > 40 else ''}"
                menu.add_command(label=label, command=lambda t=track: self._download_mp3([t], is_single=True))
                menu.add_command(label=label_m3u, command=lambda t=track: self._save_track_to_m3u(t))
                menu.add_separator()

            if self.current_results:
                menu.add_command(label="💾 Сохранить все в плейлист", command=self.save_m3u)
                menu.add_command(label="💿 Скачать все треки", command=self.download_all_mp3)
            else:
                menu.add_command(label="(Список пуст)", state=tk.DISABLED)

            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        widget.bind("<Button-3>", show_menu)

    def _copy_label(self, label):
        """Копировать текст из tk.Label."""
        text = label.cget("text")
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _copy_entry(self, entry):
        """Копировать текст из Entry-виджета."""
        try:
            text = entry.selection_get()
        except tk.TclError:
            text = entry.get()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _copy_all(self, widget):
        """Копировать весь текст из Text-виджета."""
        try:
            text = widget.get("1.0", tk.END).strip()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass

    def _copy_selection(self, widget, event=None):
        """Копировать выделенный текст из Text-виджета в буфер"""
        try:
            text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass
        return "break"

    def save_state(self, quiet=False):
        """Сохранить состояние приложения перед выходом"""
        try:
            # Получаем текущую позицию плеера (в миллисекундах)
            player_time = self.player.get_time()
            player_position = player_time if player_time > 0 else -1

            # Получаем ID трека и полный объект трека, который сейчас воспроизводится или был выбран
            # Приоритет — реально проигрываемый трек (playing_track), он может отличаться
            # от current_results[current_index], если список результатов поиска изменился после начала воспроизведения
            current_track = self.playing_track
            if current_track is None and 0 <= self.current_index < len(self.current_results):
                current_track = self.current_results[self.current_index]
            current_track_id = current_track['id'] if current_track else None

            # Получаем размер и позицию окна
            window_geometry = self.root.geometry()

            # Размеры и видимость панелей
            if self.mini_mode and self._pre_mini:
                layout = {"search": self._pre_mini["search"], "info": self._pre_mini["info"],
                          "log": self._pre_mini["log"]}
                window_geometry = self._pre_mini["geometry"]
                was_zoomed = self._pre_mini["zoomed"]
                mini_geometry = self.root.geometry()
            else:
                self._capture_sizes()
                layout = {"search": self.show_search, "info": self.show_info, "log": self.show_log}
                was_zoomed = self.root.state() == "zoomed"
                mini_geometry = self._mini_geometry

            state = {
                "search_query": self.search_entry.get(),
                "current_results": self.current_results,
                "current_index": self.current_index,
                "player_position": player_position,
                "current_track_id": current_track_id,
                "current_track": current_track,
                "volume": self.volume_var.get(),
                "window_geometry": window_geometry,
                "window_zoomed": was_zoomed,
                "panels": layout,
                "panel_sizes": dict(self._sizes),
                "mini_mode": self.mini_mode,
                "mini_geometry": mini_geometry,
                "pin_on_top": self.pin_on_top,
                "last_save_dir": self.last_save_dir,
                "ask_save_dir": self.ask_save_dir,
                "current_live_stream": self.current_live_stream,
                "live_mode_active": self.live_mode_active
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            if not quiet:
                self.log(f"💾 Состояние сохранено (позиция: {player_position}мс, громкость: {self.volume_var.get()}%)")

        except Exception as e:
            self.log(f"⚠️  Ошибка сохранения состояния: {e}")

    def load_state(self):
        """Загрузить сохранённое состояние приложения"""
        try:
            if not os.path.exists(self.state_file):
                # Первый запуск — загружаем программу передач по умолчанию
                self.root.after(200, self.load_program)
                return

            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Восстанавливаем размер и позицию окна
            window_geometry = state.get("window_geometry")
            if window_geometry:
                try:
                    self.root.geometry(window_geometry)
                    self.log(f"🪟 Размер окна восстановлен")
                except:
                    self.log(f"⚠️  Не удалось восстановить размер окна")

            if state.get("window_zoomed"):
                try:
                    self.root.state("zoomed")
                except tk.TclError:
                    pass

            # Размеры и видимость панелей (старые ключи — для совместимости с прошлой версией)
            sizes = state.get("panel_sizes") or {}
            if not sizes:
                if state.get("paned_sash_position"):
                    sizes["left_w"] = state["paned_sash_position"]
                if state.get("left_paned_sash_position"):
                    sizes["search_h"] = state["left_paned_sash_position"]
            for k, v in sizes.items():
                try:
                    self._sizes[k] = int(v)
                except (TypeError, ValueError):
                    pass
            panels = state.get("panels") or {}
            self.show_search = panels.get("search", True)
            self.show_info = panels.get("info", True)
            self.show_log = panels.get("log", True)
            self._mini_geometry = state.get("mini_geometry")
            self.root.after(100, self._apply_layout)
            if state.get("mini_mode"):
                self.root.after(250, self.toggle_mini)
            if state.get("pin_on_top"):
                self.toggle_pin()

            # Восстанавливаем поисковый запрос
            search_query = state.get("search_query", "")
            if search_query:
                self.search_entry.insert(0, search_query)

            # Восстанавливаем папку сохранения
            self.ask_save_dir = bool(state.get("ask_save_dir", False))
            saved_dir = state.get("last_save_dir")
            if saved_dir and os.path.isdir(saved_dir):
                self.last_save_dir = saved_dir

            # Восстанавливаем выбранный поток прямого эфира
            self.current_live_stream = state.get("current_live_stream", self.current_live_stream)
            if self.current_live_stream not in self.live_streams:
                self.current_live_stream = "old"
            self._update_live_button_icon()
            live_was_active = state.get("live_mode_active", False)

            # Восстанавливаем результаты поиска
            self.current_results = state.get("current_results", [])
            self.current_index = state.get("current_index", -1)

            current_track = state.get("current_track")
            current_track_id_check = state.get("current_track_id")

            track_in_results = (
                self.current_index >= 0
                and self.current_index < len(self.current_results)
                and (
                    current_track_id_check is None
                    or self.current_results[self.current_index].get('id') == current_track_id_check
                )
            )

            if self.current_results:
                self.update_results_list()
                self.log(f"✅ Восстановлены результаты поиска: {len(self.current_results)} треков")

            if track_in_results:
                track = self.current_results[self.current_index]
                self._set_now_playing(track)
                self.highlight_selected_line()
                self.load_track_info(track)
            elif current_track:
                # Трек был выбран, но в текущих результатах (другое расписание/поиск) его нет —
                # восстанавливаем его отдельно, чтобы название и описание не пропадали
                self.current_results = [current_track]
                self.current_index = 0
                self.update_results_list()
                self._set_now_playing(current_track)
                self.highlight_selected_line()
                self.load_track_info(current_track)

            # Восстанавливаем громкость
            volume = state.get("volume", 80)
            self.volume_var.set(volume)
            self.set_volume(volume)
            self.log(f"🔊 Громкость восстановлена: {volume}%")

            # Восстанавливаем позицию плеера
            player_position = state.get("player_position", -1)

            if live_was_active:
                # Был активен прямой эфир — перезапускаем выбранный поток
                self.root.after(500, lambda: self.play_live_stream(self.current_live_stream))
            elif player_position > 0 and current_track:
                # Запускаем трек и устанавливаем позицию
                self.root.after(500, lambda t=current_track: self._restore_playback(t, player_position))

        except Exception as e:
            self.log(f"⚠️  Ошибка загрузки состояния: {e}")

    def _restore_playback(self, track, position):
        """Восстановить воспроизведение с сохранённой позиции для указанного трека,
        независимо от текущих результатов поиска."""
        try:
            self.live_mode_active = False
            self._stop_icy_metadata_thread()
            cfg = self._get_site_cfg(track)
            url = cfg['stream'].format(id=track['id'])

            media = self.instance.media_list_new()
            media.add_media(self.instance.media_new(url))
            self.player.set_media(media[0])
            self.player.play()

            self.playing_track = track
            self._set_now_playing(track)
            self.is_playing = True
            self.play_pause_btn.config(text="⏸️")

            # Даём плееру время на загрузку, затем устанавливаем позицию
            self.root.after(1000, lambda: self.player.set_time(int(position)))
            
            # Форматируем позицию в мм:сс:мс для лога
            total_seconds = int(position) // 1000
            milliseconds = int(position) % 1000
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            formatted = f"{minutes:02d}:{seconds:02d}"
            
            self.log(f"▶ Воспроизведение восстановлено с позиции {formatted}\n▶ {track['title'][:80]}")
        except Exception as e:
            self.log(f"⚠️  Ошибка восстановления воспроизведения: {e}")

    def _scrape_track_page(self, track):
        """Скачивает страницу трека и возвращает (description, image_links, page_links, error).
        Не трогает UI — используется и для панели описания, и для тегов при скачивании."""
        description = ""
        image_links = []
        page_links = []

        if not HAS_BS4:
            return description, image_links, page_links, None

        cfg = self._get_site_cfg(track)
        audio_id = track['id']
        url = cfg['info'].format(id=audio_id)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            soup = BeautifulSoup(html, "html.parser")

            # Описание — ищем нужный блок по конфигу сайта
            sel_tag, sel_val = cfg['desc_selector']
            if cfg['desc_type'] == 'id':
                desc_el = soup.find(sel_tag, id=sel_val)
            else:
                desc_el = soup.find(sel_tag, class_=sel_val)

            if desc_el:
                for br in desc_el.find_all('br'):
                    br.replace_with('\n')
                description = desc_el.get_text(strip=False)
                description = '\n'.join(line.strip() for line in description.splitlines() if line.strip())

            # Картинки (только для сайтов со структурой staroeradio)
            images_div = soup.find('div', class_='images')
            if images_div:
                for link in images_div.find_all('a'):
                    href = link.get('href')
                    if href:
                        page_links.append(urljoin(url, href))
                    img = link.find('img')
                    if img:
                        src = img.get('src')
                        if src:
                            image_links.append(urljoin(url, src))

            if not image_links and page_links:
                for page_url in page_links[:5]:
                    try:
                        req2 = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req2, timeout=8) as resp2:
                            html2 = resp2.read().decode("utf-8", errors="replace")
                        soup2 = BeautifulSoup(html2, "html.parser")
                        for img in soup2.find_all('img'):
                            src = img.get('src', '')
                            if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                                image_links.append(urljoin(page_url, src))
                                break
                    except Exception:
                        pass

        except Exception as e:
            return "", [], [], str(e)

        return description, image_links, page_links, None

    def _fetch_track_info(self, track, token=None):
        """Получить описание и картинки трека со страницы (в фоновом потоке)"""
        audio_id = track['id']
        source = track.get('source', 'staroeradio.txt')

        if not HAS_BS4:
            self.root.after(0, lambda: self._display_track_info(
                audio_id, "⚠️  Для парсинга описания установите beautifulsoup4:\npip install beautifulsoup4",
                [], [], source, None, track=track, token=token, cache=False))
            return

        description, image_links, page_links, err = self._scrape_track_page(track)
        if err:
            description = f"❌ Ошибка загрузки страницы: {err}"

        # Картинки скачиваем здесь, в фоновом потоке, чтобы не подвешивать интерфейс
        images_data = []
        for img_url in image_links:
            try:
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    images_data.append(resp.read())
            except Exception:
                images_data.append(None)

        self.root.after(0, lambda: self._display_track_info(
            audio_id, description, image_links, page_links, source, images_data,
            track=track, token=token, cache=not err))

    def load_program(self):
        """Загрузить программу передач со staroeradio.ru/program/full"""
        if not HAS_BS4:
            messagebox.showwarning("Ошибка", "Для парсинга расписания установите:\npip install beautifulsoup4")
            return
        self.log("📻 Загружаем программу передач...")
        threading.Thread(target=self._fetch_program, daemon=True).start()

    def _fetch_program(self):
        """Загрузка расписания в фоновом потоке и вывод в список."""
        try:
            results = self._download_program()
            self._program_cache = (time.time(), results)
            self.root.after(0, lambda: self._apply_program(results))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Ошибка загрузки расписания: {e}"))

    def _download_program(self):
        """Скачать и разобрать staroeradio.ru/program (без обращения к интерфейсу)."""
        url = "https://staroeradio.ru/program"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        soup = BeautifulSoup(html, "html.parser")

        results = []
        days_seen = 0
        current_date = ""

        container = soup.find('div', class_='content') or soup.body
        for el in container.descendants:
            if not hasattr(el, 'get'):
                continue

            # Дата — добавляем как псевдотрек-заголовок (id='')
            if el.get('class') and 'date' in el.get('class', []):
                date_text = el.get_text(strip=True)
                if date_text and date_text != current_date:
                    current_date = date_text
                    days_seen += 1
                    if days_seen > 7:
                        break
                    results.append({'id': '', 'title': f'── {current_date} ──', 'is_date': True})
                continue

            # Запись расписания
            if el.name == 'a':
                href = el.get('href', '')
                if not href.startswith('/audio/'):
                    continue
                audio_id = href.split('/')[-1]
                if not audio_id.isdigit():
                    continue

                time_td = el.find(class_='time1')
                name_td = el.find(class_='mp3name1')
                if not time_td or not name_td:
                    continue

                time_str = time_td.get_text(strip=True)
                title = name_td.get_text(strip=True)
                if not title:
                    continue

                results.append({'id': audio_id, 'title': title, 'time': time_str, 'source': 'staroeradio.txt'})

        return results

    def _apply_program(self, results):
        """Применить результаты парсинга расписания к списку."""
        if not results:
            self.log("❌ Расписание не найдено или пусто")
            return
        self.current_results = results
        self.current_index = -1
        self.update_results_list()
        self.log(f"✅ Программа передач загружена: {len(results)} записей")

    def _display_track_info(self, audio_id, description, image_links, page_links=None, source='staroeradio.txt',
                            images_data=None, track=None, token=None, cache=True):
        """Вывести описание и изображения в панель (в главном потоке)"""
        key = (audio_id, source)
        if cache:
            self._info_cache[key] = (description, image_links, page_links or [], images_data)
            while len(self._info_cache) > 30:
                self._info_cache.pop(next(iter(self._info_cache)))

        # Первая картинка — обложка в плеере (если описание относится к играющему треку)
        if key == self._cover_key and images_data:
            first = next((d for d in images_data if d), None)
            if first:
                self._set_cover(first)

        # Пришёл ответ на устаревший запрос (уже выбран другой трек) — не показываем
        if token is not None and token != self._info_req:
            return

        try:
            from PIL import Image, ImageTk
            HAS_PIL = True
        except ImportError:
            HAS_PIL = False

        # Сбрасываем старые картинки
        self._info_images = []

        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)

        # Заголовок с ID (и названием каталога/ресурса, если не staroeradio)
        if source and source != 'staroeradio.txt':
            site_name = os.path.splitext(source)[0]
            self.info_text.insert(tk.END, f"🎵 {site_name} ID: {audio_id}\n", "header")
        else:
            self.info_text.insert(tk.END, f"🎵 ID: {audio_id}\n", "header")
        if track and track.get('title'):
            self.info_text.insert(tk.END, track['title'] + "\n", "track_title")
        self.info_text.insert(tk.END, "─" * 40 + "\n", "header")

        # Описание
        if description:
            self.info_text.insert(tk.END, description + "\n")
        else:
            self.info_text.insert(tk.END, "(Описание не найдено)\n")

        # Картинки
        if image_links:
            info_colors = self.log_colors.get("track_info", {})
            link_fg = info_colors.get("link_foreground", "#4ECDC4")
            self.info_text.insert(tk.END, "\n🖼 Изображения:\n", "header")

            if not HAS_PIL:
                self.info_text.insert(tk.END, "  (установите Pillow для показа картинок: pip install pillow)\n")

            for i, img_url in enumerate(image_links, 1):
                page_url = (page_links[i - 1] if page_links and i - 1 < len(page_links) else img_url)

                if HAS_PIL:
                    # Загружаем и показываем картинку
                    try:
                        data = images_data[i - 1] if images_data and i - 1 < len(images_data) else None
                        if data is None:
                            raise ValueError("нет данных картинки")
                        import io
                        pil_img = Image.open(io.BytesIO(data))
                        # Масштабируем чтобы вписать в ширину панели
                        max_w = max(200, min(520, self.info_text.winfo_width() - 40))
                        w, h = pil_img.size
                        if w > max_w:
                            pil_img = pil_img.resize((max_w, int(h * max_w / w)), Image.LANCZOS)
                        tk_img = ImageTk.PhotoImage(pil_img)
                        self._info_images.append(tk_img)  # держим ссылку
                        self.info_text.insert(tk.END, "\n")
                        self.info_text.image_create(tk.END, image=tk_img)
                        self.info_text.insert(tk.END, "\n")
                        # Ссылка под картинкой
                        tag_name = f"link_{i}"
                        self.info_text.tag_config(tag_name, foreground=link_fg, underline=True)
                        self.info_text.tag_bind(tag_name, "<Button-1>", lambda e, u=page_url: self._open_url(u))
                        self.info_text.tag_bind(tag_name, "<Enter>", lambda e: self.info_text.config(cursor="hand2"))
                        self.info_text.tag_bind(tag_name, "<Leave>", lambda e: self.info_text.config(cursor=""))
                        self.info_text.insert(tk.END, f"🔗{i}\n", tag_name)
                    except Exception as ex:
                        # Если картинку загрузить не удалось — показываем ссылку
                        tag_name = f"link_{i}"
                        self.info_text.tag_config(tag_name, foreground=link_fg, underline=True)
                        self.info_text.tag_bind(tag_name, "<Button-1>", lambda e, u=page_url: self._open_url(u))
                        self.info_text.tag_bind(tag_name, "<Enter>", lambda e: self.info_text.config(cursor="hand2"))
                        self.info_text.tag_bind(tag_name, "<Leave>", lambda e: self.info_text.config(cursor=""))
                        self.info_text.insert(tk.END, f"  [{i}] {img_url}\n", tag_name)
                else:
                    # Без Pillow — только ссылки
                    tag_name = f"link_{i}"
                    self.info_text.tag_config(tag_name, foreground=link_fg, underline=True)
                    self.info_text.tag_bind(tag_name, "<Button-1>", lambda e, u=page_url: self._open_url(u))
                    self.info_text.tag_bind(tag_name, "<Enter>", lambda e: self.info_text.config(cursor="hand2"))
                    self.info_text.tag_bind(tag_name, "<Leave>", lambda e: self.info_text.config(cursor=""))
                    self.info_text.insert(tk.END, f"  [{i}] {img_url}\n", tag_name)

        self.info_text.config(state=tk.DISABLED)
        self.info_text.yview_moveto(0)

    def _on_info_link_click(self, event):
        """Обработка клика по ссылке в области описания"""
        # Общий тег link — открываем первую ссылку (запасной вариант)
        pass

    def _open_url(self, url):
        """Открыть URL в браузере"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            self.log(f"❌ Не удалось открыть ссылку: {e}")

    def log(self, message):
        # Определяем цвет в зависимости от типа сообщения
        if message.startswith("✅"):
            tag = "success"
        elif message.startswith("❌"):
            tag = "error"
        elif message.startswith("⚠️"):
            tag = "warning"
        else:
            tag = "info"

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

        # Последнее сообщение — в строку состояния плеера (видно и при скрытом логе)
        first = message.strip().splitlines()[0] if message.strip() else ""
        fg = self.log_colors.get("log_tags", {}).get(tag, {}).get("foreground", "#888888")
        self.status_label.config(text=first, fg=fg)

    def _safe_log(self, message):
        """Вызов log() из фонового потока через главный поток (thread-safe)"""
        self.root.after(0, lambda m=message: self.log(m))

    def load_colors_config(self):
        """Загрузить конфиг цветов, создать если не существует"""
        default_colors = {
            "search_tags": {
                "number": {
                    "foreground": "#979695",
                    "description": "Номер трека"
                },
                "title": {
                    "foreground": "#61A0F3",
                    "description": "Название трека"
                },
                "date_header": {
                    "foreground": "#FFD54F",
                    "description": "Заголовок даты в программе"
                },
                "time_text": {
                    "foreground": "#888888",
                    "description": "Время передачи в программе"
                },
                "selected": {
                    "background": "#1E3A8A",
                    "foreground": "#FFFFFF",
                    "description": "Выбранная строка"
                },
                "playing": {
                    "foreground": "#FFB74D",
                    "description": "Играющий трек"
                }
            },
            "results_area": {
                "background": "#000000",
                "description": "Фон области поиска"
            },
            "log_tags": {
                "success": {
                    "foreground": "#81C784",
                    "description": "Успех"
                },
                "error": {
                    "foreground": "#E57373",
                    "description": "Ошибка"
                },
                "warning": {
                    "foreground": "#FFB74D",
                    "description": "Предупреждение"
                },
                "info": {
                    "foreground": "#64B5F6",
                    "description": "Информация"
                }
            },
            "log_area": {
                "background": "#000000",
                "description": "Фон области лога"
            },
            "player_labels": {
                "current_track": {
                    "foreground": "#D5B491",
                    "background": "#000000",
                    "font_size": 13,
                    "font_weight": "normal",
                    "description": "Текущий трек в плеере"
                },
                "player_area": {
                    "background": "#000000",
                    "description": "Фон области плеера"
                },
                "volume_label": {
                    "foreground": "#696c70",
                    "description": "Эмодзи громкости и проценты"
                },
                "time_label": {
                    "foreground": "#696c70",
                    "description": "Время в прогресс-баре"
                },
                "slider": {
                    "fill": "#3d7be0",
                    "track": "#2a2a2a",
                    "description": "Ползунки: заполненная часть/ручка и фон"
                }
            },
            "track_info": {
                "foreground": "#64B5F6",
                "background": "#000000",
                "header_foreground": "#FFB74D",
                "link_foreground": "#4ECDC4",
                "font_size": 10,
                "font_weight": "normal",
                "description": "Область описания трека"
            },
            "frame_labels": {
                "title_foreground": "#696c70",
                "sash": "#1a1a1a",
                "description": "Цвет заголовков панелей и разделителей между ними"
            },
            "buttons": {
                "foreground": "#b8bcc4",
                "hover_background": "#25272c",
                "accent": "#3d7be0",
                "description": "Плоские кнопки: значки, подсветка, акцент"
            },
            "titlebar": {
                "background": "#383838",
                "description": "Цвет заголовка окна Windows (только Windows 10 build 19041+ и Windows 11)"
            }
        }

        import copy
        self.default_colors = copy.deepcopy(default_colors)

        def deep_merge(base, override):
            """Рекурсивно: берём всё из base, перезаписываем тем что есть в override."""
            result = dict(base)
            for k, v in override.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k] = deep_merge(result[k], v)
                else:
                    result[k] = v
            return result

        # Если конфиг не существует, создаём его
        if not os.path.exists(self.colors_file):
            try:
                with open(self.colors_file, 'w', encoding='utf-8') as f:
                    json.dump(default_colors, f, ensure_ascii=False, indent=2)
                self.log_colors = default_colors
                print(f"✅ Создан конфиг цветов: {self.colors_file}")
            except Exception as e:
                print(f"❌ Ошибка создания конфига: {e}")
                self.log_colors = default_colors
        else:
            # Загружаем существующий конфиг и мёржим с дефолтом
            try:
                with open(self.colors_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self.log_colors = deep_merge(default_colors, loaded)
                print(f"✅ Загружен конфиг цветов: {self.colors_file}")
            except Exception as e:
                print(f"⚠️  Ошибка загрузки конфига, используются стандартные цвета: {e}")
                self.log_colors = default_colors
    
    def _ensure_history_dir(self):
        """Создать папку History если не существует"""
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
            self.log("📁 Создана папка History")

    def _log_to_history(self, track):
        """Записать проигранный трек в историю"""
        from datetime import datetime
    
        today = datetime.now().strftime("%d.%m.%Y")
        history_file = os.path.join(self.history_dir, f"{today}.txt")
    
        time_str = datetime.now().strftime("%H:%M")
    
        with open(history_file, 'a', encoding='utf-8') as f:
            f.write(f"{time_str}\n")
            f.write(f"{track['id']}\t{track['title']}\n")
            f.write("\n")
    
        self.log(f"📝 Записано в историю: {track['title'][:40]}...")

    def load_history(self):
        """Загрузить историю из папки History и показать в Результатах поиска.
        Избранное (favorites.txt) выводится вверху, затем история по убыванию даты."""
        from datetime import datetime

        results = []

        favorites_file = os.path.join(self.history_dir, "favorites.txt")
        fav_tracks = []

        # ── Избранное ────────────────────────────────────────────────────
        if os.path.exists(favorites_file):
            try:
                with open(favorites_file, 'r', encoding='utf-8') as f:
                    lines = [l.rstrip('\n') for l in f.readlines()]

                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if not line:
                        i += 1
                        continue
                    # Строка вида "дд.мм.гггг чч:мм:сс" — метка времени добавления
                    # Следующая строка — id\tназвание или название\tназвание
                    if i + 1 < len(lines) and '\t' in lines[i + 1]:
                        parts = lines[i + 1].split('\t', 1)
                        track_id = parts[0].strip()
                        title = parts[1].strip()
                        # Определяем source по ID (числовой ID → staroeradio)
                        source = 'staroeradio.txt'
                        fav_tracks.append({
                            'id': track_id,
                            'title': title,
                            'source': source,
                        })
                        i += 2
                    else:
                        i += 1
            except Exception as e:
                self.log(f"⚠️ Ошибка чтения избранного: {e}")

        # ── Заголовок «Избранное» и сами треки ──────────────────────────
        if fav_tracks:
            results.append({'is_date': True, 'title': '⭐ Избранное', 'id': None})
            for t in fav_tracks:
                results.append(t)

        # ── История по датам (убывание) ───────────────────────────────
        history_files = sorted(
            glob.glob(os.path.join(self.history_dir, "??.??.????.txt")),
            reverse=True
        )

        if not history_files and not fav_tracks:
            self.log("⚠️ История пуста")
            return

        for hf in history_files:
            date_label = os.path.splitext(os.path.basename(hf))[0]  # дд.мм.гггг
            day_tracks = []

            try:
                with open(hf, 'r', encoding='utf-8') as f:
                    lines = [l.rstrip('\n') for l in f.readlines()]

                i = 0
                while i < len(lines):
                    time_line = lines[i].strip()
                    if not time_line:
                        i += 1
                        continue
                    # Строка времени чч:мм или чч:мм:сс
                    if len(time_line) >= 5 and time_line[2] == ':':
                        hhmm = time_line[:5]  # только чч:мм
                        if i + 1 < len(lines) and lines[i + 1].strip():
                            track_line = lines[i + 1].strip()
                            if '\t' in track_line:
                                parts = track_line.split('\t', 1)
                                track_id = parts[0].strip()
                                title = parts[1].strip()
                            else:
                                # Старый формат: "ID -- название"
                                if ' -- ' in track_line:
                                    parts = track_line.split(' -- ', 1)
                                    track_id = parts[0].strip()
                                    title = parts[1].strip()
                                else:
                                    track_id = track_line
                                    title = track_line
                            source = 'staroeradio.txt'
                            day_tracks.append({
                                'id': track_id,
                                'title': title,
                                'source': source,
                                'time': hhmm,
                            })
                            i += 2
                        else:
                            i += 1
                    else:
                        i += 1

            except Exception as e:
                self.log(f"⚠️ Ошибка чтения {hf}: {e}")
                continue

            if day_tracks:
                results.append({'is_date': True, 'title': date_label, 'id': None})
                results.extend(day_tracks)

        self.current_results = results
        self.current_index = -1
        self.update_results_list()
        count = sum(1 for r in results if not r.get('is_date'))
        self.log(f"🕐 История загружена: {count} записей")

    def add_to_favorites(self):
        """Записать текущий трек в favorites.txt"""
        # Приоритет — реально воспроизводимый трек, затем выбранный в списке
        track = self.playing_track
        if track is None:
            if self.current_index < 0 or self.current_index >= len(self.current_results):
                self.log("⚠️ Нет выбранного трека")
                return
            track = self.current_results[self.current_index]

        if track.get('is_date'):
            return

        favorites_file = os.path.join(self.history_dir, "favorites.txt")

        # Проверяем — вдруг уже есть
        if os.path.exists(favorites_file):
            with open(favorites_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(track['id'] + '\t'):
                        self.log(f"⚠️ Уже в избранном: {track['title'][:40]}")
                        return
                    
        from datetime import datetime

        today = datetime.now().strftime("%d.%m.%Y")
        time_str = datetime.now().strftime("%H:%M:%S")

        with open(favorites_file, 'a', encoding='utf-8') as f:
            f.write(f"{today} {time_str}\n")
            f.write(f"{track['id']}\t{track['title']}\n")

        self.log(f"⭐ Добавлено в избранное: {track['title'][:40]}")

    def apply_colors(self):
        """Применить текущий self.log_colors к виджетам без перезапуска."""
        cfg = self.log_colors
        pl = cfg.get("player_labels", {})
        btn_cfg = cfg.get("buttons", {})
        btn_fg = btn_cfg.get("foreground", "#b8bcc4")
        btn_hover = btn_cfg.get("hover_background", "#2a2d33")
        accent = btn_cfg.get("accent", "#4c8bf5")
        fl_fg = cfg.get("frame_labels", {}).get("title_foreground", "#696c70")
        sash = cfg.get("frame_labels", {}).get("sash", "#212121")
        slider = pl.get("slider", {})

        ra_bg = self._area_bg("search")
        la_bg = self._area_bg("log")
        ti_bg = self._area_bg("info")
        pa_bg = self._area_bg("player")

        # ── Разделители ───────────────────────────────────────────
        for pw in (self.paned_window, self.left_paned, self.right_paned):
            pw.config(bg=sash)
        self.root.config(bg=sash)

        # ── Панели с заголовками ──────────────────────────────────
        for area, p in self._panels.items():
            bg = self._area_bg(area)
            for w in [p["outer"], p["head"], p["body"]] + p["extra"]:
                w.config(bg=bg)
            p["title"].config(bg=bg, fg=fl_fg)
            p["info"].config(bg=bg, fg=fl_fg)
            p["sep"].config(bg=_shade(bg, 0.12))
        for sb, area in self._scrollbars:
            sb.set_colors(self._area_bg(area))

        # ── Поиск ─────────────────────────────────────────────────
        self.results_listbox.config(bg=ra_bg, selectbackground=_shade(ra_bg, 0.2))
        for tag_name, tag_cfg in cfg.get("search_tags", {}).items():
            kw = {}
            if tag_cfg.get("foreground"): kw["foreground"] = tag_cfg["foreground"]
            if tag_cfg.get("background"): kw["background"] = tag_cfg["background"]
            if kw:
                self.results_listbox.tag_config(tag_name, **kw)
        self.results_listbox.tag_config("hover", background=_shade(ra_bg, 0.08))
        self.results_listbox.tag_raise("selected")
        self.results_listbox.tag_raise("playing")

        # ── Лог ───────────────────────────────────────────────────
        self.log_text.config(bg=la_bg)
        for tag_name, tag_cfg in cfg.get("log_tags", {}).items():
            kw = {}
            if tag_cfg.get("foreground"): kw["foreground"] = tag_cfg["foreground"]
            if tag_cfg.get("background"): kw["background"] = tag_cfg["background"]
            if kw:
                self.log_text.tag_config(tag_name, **kw)

        # ── Плеер: фон ────────────────────────────────────────────
        self.control_frame.config(bg=pa_bg)
        for f in self._player_frames:
            f.config(bg=pa_bg)
        for sep in self._player_seps:
            sep.config(bg=_shade(pa_bg, 0.15))
        self._bar_sep.config(bg=_shade(pa_bg, 0.12))
        cover_bg = _shade(pa_bg, 0.06)
        self.cover_box.config(bg=cover_bg)
        self.cover_label.config(bg=cover_bg, fg=_shade(pa_bg, 0.35))
        s_fill = slider.get("fill") or accent
        s_track = slider.get("track") or _shade(pa_bg, 0.15)
        self.progress_slider.set_colors(pa_bg, s_fill, s_track)
        self.volume_slider.set_colors(pa_bg, s_fill, s_track)

        vl_fg = pl.get("volume_label", {}).get("foreground", "#696c70")
        tl_fg = pl.get("time_label", {}).get("foreground", "#696c70")
        for w in (self.vol_icon_label, self.volume_label):
            w.config(bg=pa_bg, fg=vl_fg)
        for w in (self.time_current, self.time_total, self.state_label, self.dl_label):
            w.config(bg=pa_bg, fg=tl_fg)
        self.status_label.config(bg=pa_bg)

        # ── Плеер: текущий трек ───────────────────────────────────
        ct = pl.get("current_track", {})
        kw = {}
        if ct.get("foreground"): kw["foreground"] = ct["foreground"]
        kw["background"] = ct.get("background") or pa_bg
        kw["font"] = (UI_FONT, int(ct.get("font_size", 11)), ct.get("font_weight", "normal"))
        self.current_label.config(**kw)

        # ── Описание трека ────────────────────────────────────────
        ti = cfg.get("track_info", {})
        if ti.get("foreground"): self.info_text.config(fg=ti["foreground"])
        ti_size = int(ti.get("font_size", 10))
        self.info_text.config(bg=ti_bg, font=("Consolas", ti_size, ti.get("font_weight", "normal")),
                              selectbackground=_shade(ti_bg, 0.25))
        if ti.get("link_foreground"):
            self.info_text.tag_config("link", foreground=ti["link_foreground"])
        if ti.get("header_foreground"):
            self.info_text.tag_config("header", foreground=ti["header_foreground"])
        self.info_text.tag_config("track_title", foreground=ct.get("foreground", "#D5B491"),
                                  font=(UI_FONT, ti_size + 1, "bold"))

        # ── Кнопки ────────────────────────────────────────────────
        for btn, area in self._themed_buttons:
            btn.set_colors(self._area_bg(area), btn_fg, btn_hover, accent)

        # ── Заголовок окна Windows ────────────────────────────────
        tb_bg = cfg.get("titlebar", {}).get("background")
        if tb_bg:
            self._set_titlebar_color(tb_bg)

    def _set_titlebar_color(self, hex_color: str):
        """Цвет заголовка главного окна (Windows 10 19041+ / 11)."""
        set_titlebar_color(self.root, hex_color)

    def open_settings(self):
        """Окно настроек (одно; повторное нажатие — поднять его)."""
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.deiconify()
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        self._settings_win = SettingsWindow(self.root, self)
        self._sync_toggle_buttons()

    def on_closing(self):
        self.save_state()
        self._stop_icy_metadata_thread()
        self.player.stop()
        self.root.destroy()



# ═══════════════════════════════════════════════════════════════════
#  Окно настроек
# ═══════════════════════════════════════════════════════════════════
S_BG = "#1c1d20"
S_SIDE = "#17181a"
S_CARD = "#232428"
S_FIELD = "#2b2d31"
S_FG = "#dcdde0"
S_DIM = "#8e9097"
S_BORDER = "#3a3c42"
S_ERR = "#e57373"


def _mk(cls, parent, **opts):
    """Создать tk-виджет и задать цвета ПОСЛЕ создания (ttkbootstrap перекрашивает
    tk-виджеты в момент создания, поэтому цвета из конструктора могут теряться)."""
    w = cls(parent)
    if opts:
        w.configure(**opts)
    return w


def _palette():
    """Набор готовых цветов: серые + 8 оттенков по 5 уровней яркости."""
    import colorsys
    rows = [["#000000", "#141414", "#1e1e1e", "#2a2a2a", "#3a3a3a", "#5c5c5c", "#9a9a9a", "#ffffff"]]
    hues = [0, 25, 45, 120, 170, 205, 230, 285]
    for light in (0.22, 0.38, 0.55, 0.70, 0.84):
        row = []
        for h in hues:
            r, g, b = colorsys.hls_to_rgb(h / 360, light, 0.62)
            row.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
        rows.append(row)
    return rows


def _valid_hex(v):
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", v or ""))


class ColorPopup(tk.Toplevel):
    """Всплывающая палитра под образцом цвета: готовые цвета, недавние,
    светлее/темнее, HEX и системная палитра."""
    def __init__(self, master, anchor, initial, on_pick, recent, accent):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.on_pick = on_pick
        self.recent = recent
        self.accent = accent
        self.current = initial if _valid_hex(initial) else "#ffffff"
        self.configure(bg=S_BORDER)
        body = _mk(tk.Frame, self, bg=S_CARD)
        body.pack(padx=1, pady=1)

        top = _mk(tk.Frame, body, bg=S_CARD)
        top.pack(fill=tk.X, padx=10, pady=(10, 6))
        self.preview = _mk(tk.Canvas, top, width=34, height=22, bg=S_CARD, highlightthickness=0)
        self.preview.pack(side=tk.LEFT)
        self.hex_var = tk.StringVar(value=self.current)
        e = _mk(tk.Entry, top, textvariable=self.hex_var, width=9, bg=S_FIELD, fg=S_FG,
                insertbackground=S_FG, relief="flat", font=("Consolas", 10),
                highlightthickness=1, highlightbackground=S_BORDER, highlightcolor=accent)
        e.pack(side=tk.LEFT, padx=8, ipady=2)
        e.bind("<Return>", lambda ev: self._from_entry(close=True))
        e.bind("<KeyRelease>", lambda ev: self._from_entry())
        self.entry = e
        for text, amt, tip in (("◐−", -0.12, "Темнее"), ("◑+", 0.12, "Светлее")):
            b = FlatButton(top, text, lambda a=amt: self._pick(_shade(self.current, a)),
                           font=(UI_FONT, 9), padx=6, pady=1, tooltip=tip)
            b.set_colors(S_CARD, S_FG, S_FIELD, accent)
            b.pack(side=tk.LEFT, padx=1)

        grid = _mk(tk.Frame, body, bg=S_CARD)
        grid.pack(padx=10)
        for r, row in enumerate(_palette()):
            for c, col in enumerate(row):
                self._swatch(grid, col).grid(row=r, column=c, padx=2, pady=2)

        if recent:
            _mk(tk.Label, body, text="Недавние", bg=S_CARD, fg=S_DIM, font=(UI_FONT, 8)).pack(
                anchor="w", padx=12, pady=(8, 0))
            rr = _mk(tk.Frame, body, bg=S_CARD)
            rr.pack(anchor="w", padx=10)
            for col in recent[:8]:
                self._swatch(rr, col).pack(side=tk.LEFT, padx=2, pady=2)

        bottom = _mk(tk.Frame, body, bg=S_CARD)
        bottom.pack(fill=tk.X, padx=8, pady=(6, 8))
        sysb = FlatButton(bottom, "Системная палитра…", self._system, font=(UI_FONT, 9), padx=6, pady=2)
        sysb.set_colors(S_CARD, S_DIM, S_FIELD, accent)
        sysb.pack(side=tk.LEFT)
        okb = FlatButton(bottom, "Готово", self.close, font=(UI_FONT, 9), padx=10, pady=2, kind="primary")
        okb.set_colors(S_CARD, S_FG, S_FIELD, accent)
        okb.pack(side=tk.RIGHT)

        self._draw_preview()
        self.bind("<Escape>", lambda ev: self.close())
        self.bind("<FocusOut>", lambda ev: self.after(120, self._check_focus))
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if x + w > sw:
            x = sw - w - 8
        if y + h > sh:
            y = anchor.winfo_rooty() - h - 4
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.focus_force()
        self.entry.focus_set()

    def _swatch(self, parent, color):
        c = _mk(tk.Canvas, parent, width=20, height=20, bg=S_CARD, highlightthickness=0, cursor="hand2")
        rect = c.create_rectangle(2, 2, 19, 19, fill=color, outline=_shade(color, 0.18))
        c.bind("<Enter>", lambda e: c.itemconfig(rect, outline="#ffffff"))
        c.bind("<Leave>", lambda e: c.itemconfig(rect, outline=_shade(color, 0.18)))
        c.bind("<Button-1>", lambda e: self._pick(color))
        return c

    def _draw_preview(self):
        self.preview.delete("all")
        self.preview.create_rectangle(1, 1, 33, 21, fill=self.current, outline=S_BORDER)

    def _pick(self, color):
        self.current = color
        self.hex_var.set(color)
        self._draw_preview()
        self.on_pick(color)

    def _from_entry(self, close=False):
        v = self.hex_var.get().strip()
        if _valid_hex(v):
            self.entry.configure(highlightbackground=S_BORDER)
            if v.lower() != self.current.lower():
                self.current = v
                self._draw_preview()
                self.on_pick(v)
            if close:
                self.close()
        else:
            self.entry.configure(highlightbackground=S_ERR)

    def _system(self):
        cur = self.current
        master = self.master
        self.close()
        try:
            res = colorchooser.askcolor(color=cur, title="Выберите цвет", parent=master)
        except Exception:
            res = (None, None)
        if res and res[1]:
            self.on_pick(res[1])

    def _check_focus(self):
        try:
            f = self.focus_get()
        except Exception:
            f = None
        if f is None or not str(f).startswith(str(self)):
            self.close()

    def close(self):
        try:
            if _valid_hex(self.current) and self.current not in self.recent:
                self.recent.insert(0, self.current)
                del self.recent[12:]
            self.destroy()
        except tk.TclError:
            pass


class SettingsWindow(tk.Toplevel):
    """Настройки: цвета и шрифты по разделам (изменения видны сразу), папка сохранения, схемы."""

    C, SIZE, WEIGHT = "color", "size", "weight"
    PAGES = [
        ("general", "⚙", "Общие", [
            ("Сохранение файлов", "SAVE_DIR"),
            ("Окно", [
                (("titlebar", None, "background"), "Заголовок окна Windows", C),
                (("frame_labels", None, "sash"), "Разделители между панелями", C),
                (("frame_labels", None, "title_foreground"), "Заголовки панелей (ПОИСК, ЛОГ…)", C),
            ]),
        ]),
        ("player", "▶", "Плеер", [
            ("Название трека", [
                (("player_labels", "current_track", "foreground"), "Цвет текста", C),
                (("player_labels", "current_track", "background"), "Фон", C),
                (("player_labels", "current_track", "font_size"), "Размер шрифта", SIZE),
                (("player_labels", "current_track", "font_weight"), "Начертание", WEIGHT),
            ]),
            ("Область плеера", [
                (("player_labels", "player_area", "background"), "Фон", C),
                (("player_labels", "time_label", "foreground"), "Время и статус", C),
                (("player_labels", "volume_label", "foreground"), "Значок 🔊 и громкость %", C),
            ]),
            ("Ползунки", [
                (("player_labels", "slider", "fill"), "Заполненная часть и ручка", C),
                (("player_labels", "slider", "track"), "Незаполненная часть", C),
            ]),
        ]),
        ("buttons", "◉", "Кнопки", [
            ("Кнопки", [
                (("buttons", None, "foreground"), "Значки", C),
                (("buttons", None, "hover_background"), "Подсветка при наведении", C),
                (("buttons", None, "accent"), "Акцент (▶ и включённые переключатели)", C),
            ]),
        ]),
        ("search", "🔍", "Поиск", [
            ("Список", [
                (("search_tags", "number", "foreground"), "Номер трека", C),
                (("search_tags", "title", "foreground"), "Название", C),
                (("search_tags", "playing", "foreground"), "Играющий трек", C),
                (("search_tags", "date_header", "foreground"), "Заголовок даты", C),
                (("search_tags", "time_text", "foreground"), "Время передачи", C),
            ]),
            ("Выделенная строка", [
                (("search_tags", "selected", "foreground"), "Текст", C),
                (("search_tags", "selected", "background"), "Фон", C),
            ]),
            ("Область", [
                (("results_area", None, "background"), "Фон", C),
            ]),
        ]),
        ("info", "▤", "Описание", [
            ("Текст", [
                (("track_info", None, "foreground"), "Текст", C),
                (("track_info", None, "header_foreground"), "Заголовок (ID)", C),
                (("track_info", None, "link_foreground"), "Ссылки", C),
                (("track_info", None, "font_size"), "Размер шрифта", SIZE),
                (("track_info", None, "font_weight"), "Начертание", WEIGHT),
            ]),
            ("Область", [
                (("track_info", None, "background"), "Фон", C),
            ]),
        ]),
        ("log", "≡", "Лог", [
            ("Сообщения", [
                (("log_tags", "success", "foreground"), "Успех (✅)", C),
                (("log_tags", "error", "foreground"), "Ошибка (❌)", C),
                (("log_tags", "warning", "foreground"), "Предупреждение (⚠️)", C),
                (("log_tags", "info", "foreground"), "Информация", C),
            ]),
            ("Область", [
                (("log_area", None, "background"), "Фон", C),
            ]),
        ]),
        ("schemes", "🎨", "Схемы", [("Цветовые схемы", "SCHEMES")]),
    ]
    WEIGHTS = [("normal", "Обычный"), ("bold", "Жирный"), ("italic", "Курсив"), ("bold italic", "Ж+К")]

    def __init__(self, parent, player):
        super().__init__(parent)
        import copy
        self.player = player
        self.cfg = copy.deepcopy(player.log_colors)
        self.dirty = False
        self._apply_job = None
        self._popup = None
        self._page = None
        if not hasattr(player, "_recent_colors"):
            player._recent_colors = []
        self.schemes_dir = os.path.join(player.script_dir, "color_schemes")
        os.makedirs(self.schemes_dir, exist_ok=True)

        self.title("Настройки")
        icons = getattr(parent, "_app_icons", None)
        if icons:
            try:
                self.iconphoto(False, *icons)
            except tk.TclError:
                pass
        self.geometry("780x600")
        self.minsize(640, 420)
        self.configure(bg=S_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Button-1>", self._close_popup_on_click, add="+")
        self._build()
        self._show_page("general")
        self.after(30, lambda: set_titlebar_color(self, self._tb_color()))

    # ── каркас ─────────────────────────────────────────────────────
    def _accent(self):
        return self.cfg.get("buttons", {}).get("accent", "#3d7be0")

    def _tb_color(self):
        return self.cfg.get("titlebar", {}).get("background", S_BG)

    def _btn(self, parent, text, cmd, bg, kind="normal", font=None, padx=10, pady=4, tip=None, fg=S_FG):
        b = FlatButton(parent, text, cmd, font=font or (UI_FONT, 10), padx=padx, pady=pady,
                       tooltip=tip, kind=kind)
        b.set_colors(bg, fg, _shade(bg, 0.08), self._accent())
        return b

    def _build(self):
        # Нижняя панель (пакуется первой — всегда видна)
        self.bottom = _mk(tk.Frame, self, bg=S_SIDE)
        self.bottom.pack(side=tk.BOTTOM, fill=tk.X)
        _mk(tk.Frame, self, bg=S_BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        self._build_bottom_normal()

        # Боковое меню
        side = _mk(tk.Frame, self, bg=S_SIDE, width=180)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)
        _mk(tk.Label, side, text="НАСТРОЙКИ", bg=S_SIDE, fg=S_DIM, font=(UI_FONT, 8, "bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        self.nav = {}
        for key, icon, title, _ in self.PAGES:
            b = FlatButton(side, f"{icon}   {title}", lambda k=key: self._show_page(k),
                           font=(UI_FONT, 10), padx=16, pady=7, kind="toggle")
            b.configure(anchor="w")
            b.set_colors(S_SIDE, S_FG, _shade(S_SIDE, 0.07), self._accent())
            b.pack(fill=tk.X)
            self.nav[key] = b

        # Содержимое
        main = _mk(tk.Frame, self, bg=S_BG)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.page_title = _mk(tk.Label, main, text="", bg=S_BG, fg=S_FG, font=(UI_FONT, 14, "bold"))
        self.page_title.pack(anchor="w", padx=22, pady=(14, 6))
        wrap = _mk(tk.Frame, main, bg=S_BG)
        wrap.pack(fill=tk.BOTH, expand=True, padx=(14, 4), pady=(0, 6))
        self.canvas = _mk(tk.Canvas, wrap, bg=S_BG, highlightthickness=0, bd=0)
        sb = ThinScrollbar(wrap, "vertical", command=self.canvas.yview)
        sb.set_colors(S_BG)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.inner = None
        self._inner_id = None
        self.canvas.bind("<Configure>", lambda e: self._inner_id and self.canvas.itemconfig(self._inner_id, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

    def _on_wheel(self, e):
        top, bottom = self.canvas.yview()
        if top <= 0 and bottom >= 1:
            return
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _clear_bottom(self):
        for w in self.bottom.winfo_children():
            w.destroy()

    def _build_bottom_normal(self):
        self._clear_bottom()
        bg = S_SIDE
        self.status = _mk(tk.Label, self.bottom, text="", bg=bg, fg=S_DIM, font=(UI_FONT, 9))
        self.status.pack(side=tk.LEFT, padx=16)
        self._btn(self.bottom, "Закрыть", self._on_close, bg).pack(side=tk.RIGHT, padx=(4, 12), pady=8)
        self._btn(self.bottom, "Сохранить", self._save, bg, kind="primary").pack(side=tk.RIGHT, padx=4, pady=8)
        self._btn(self.bottom, "↺ Отменить изменения", self._revert, bg, fg=S_DIM).pack(side=tk.RIGHT, padx=4, pady=8)
        self._update_status()

    def _build_bottom_confirm(self):
        self._clear_bottom()
        bg = S_SIDE
        _mk(tk.Label, self.bottom, text="Сохранить изменения перед закрытием?", bg=bg, fg=S_FG,
            font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=16)
        self._btn(self.bottom, "Отмена", self._build_bottom_normal, bg).pack(side=tk.RIGHT, padx=(4, 12), pady=8)
        self._btn(self.bottom, "Не сохранять", lambda: (self._revert(), self._destroy()), bg,
                  fg=S_DIM).pack(side=tk.RIGHT, padx=4, pady=8)
        self._btn(self.bottom, "Сохранить", lambda: (self._save(), self._destroy()), bg,
                  kind="primary").pack(side=tk.RIGHT, padx=4, pady=8)

    def _update_status(self):
        if hasattr(self, "status") and self.status.winfo_exists():
            self.status.configure(
                text="● Есть несохранённые изменения" if self.dirty else "Изменения видны сразу",
                fg="#e0b050" if self.dirty else S_DIM)

    # ── страницы ───────────────────────────────────────────────────
    def _show_page(self, key):
        self._close_popup()
        self._page = key
        for k, b in self.nav.items():
            b.set_active(k == key)
        page = next(p for p in self.PAGES if p[0] == key)
        self.page_title.configure(text=page[2])
        if self.inner is not None:
            self.inner.destroy()
        self.inner = _mk(tk.Frame, self.canvas, bg=S_BG)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw",
                                                   width=max(300, self.canvas.winfo_width()))
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.yview_moveto(0)
        for group_title, rows in page[3]:
            card = self._card(group_title)
            if rows == "SAVE_DIR":
                self._build_save_dir(card)
            elif rows == "SCHEMES":
                self._build_schemes(card)
            else:
                for key_path, label, kind in rows:
                    self._row(card, key_path, label, kind)

    def _card(self, title):
        _mk(tk.Label, self.inner, text=title.upper(), bg=S_BG, fg=S_DIM, font=(UI_FONT, 8, "bold")).pack(
            anchor="w", padx=8, pady=(10, 4))
        card = _mk(tk.Frame, self.inner, bg=S_CARD)
        card.pack(fill=tk.X, padx=8, pady=(0, 4))
        card.columnconfigure(0, weight=1)
        return card

    def _row(self, card, key, label, kind):
        r = card.grid_size()[1]
        if r > 0:
            _mk(tk.Frame, card, bg=_shade(S_CARD, 0.05), height=1).grid(row=r, column=0, columnspan=2,
                                                                       sticky="ew", padx=12)
            r += 1
        _mk(tk.Label, card, text=label, bg=S_CARD, fg=S_FG, font=(UI_FONT, 10), anchor="w").grid(
            row=r, column=0, sticky="w", padx=14, pady=7)
        ctl = _mk(tk.Frame, card, bg=S_CARD)
        ctl.grid(row=r, column=1, sticky="e", padx=10, pady=4)
        if kind == self.C:
            self._color_control(ctl, key)
        elif kind == self.SIZE:
            self._size_control(ctl, key)
        else:
            self._weight_control(ctl, key)

    # ── элементы управления ────────────────────────────────────────
    def _color_control(self, ctl, key):
        val = self._get(key) or "#ffffff"
        sw = _mk(tk.Canvas, ctl, width=40, height=24, bg=S_CARD, highlightthickness=0, cursor="hand2")
        sw.pack(side=tk.LEFT)
        rect = sw.create_rectangle(1, 1, 39, 23, fill=val if _valid_hex(val) else "#000000", outline=S_BORDER)
        var = tk.StringVar(value=val)
        ent = _mk(tk.Entry, ctl, textvariable=var, width=9, bg=S_FIELD, fg=S_FG, insertbackground=S_FG,
                  relief="flat", font=("Consolas", 10), highlightthickness=1,
                  highlightbackground=S_BORDER, highlightcolor=self._accent())
        ent.pack(side=tk.LEFT, padx=(8, 4), ipady=3)

        def on_write(*_):
            v = var.get().strip()
            if _valid_hex(v):
                ent.configure(highlightbackground=S_BORDER)
                sw.itemconfig(rect, fill=v)
                if v != self._get(key):
                    self._set(key, v)
            else:
                ent.configure(highlightbackground=S_ERR)
        var.trace_add("write", on_write)

        def open_popup(_e=None):
            self._close_popup()
            self._popup = ColorPopup(self, sw, var.get().strip(), lambda c: var.set(c),
                                     self.player._recent_colors, self._accent())
            return "break"
        sw.bind("<Button-1>", open_popup)
        sw.bind("<Enter>", lambda e: sw.itemconfig(rect, outline="#ffffff"))
        sw.bind("<Leave>", lambda e: sw.itemconfig(rect, outline=S_BORDER))
        Tooltip(sw, "Выбрать цвет")

        default = self._get(key, self.player.default_colors)
        rb = self._btn(ctl, "↺", lambda: default and var.set(default), S_CARD, font=(UI_FONT, 10),
                       padx=6, pady=1, tip=f"По умолчанию: {default}", fg=S_DIM)
        rb.pack(side=tk.LEFT)

    def _size_control(self, ctl, key):
        try:
            val = int(self._get(key) or 10)
        except (TypeError, ValueError):
            val = 10
        var = tk.IntVar(value=val)
        lbl = _mk(tk.Label, ctl, text=str(val), width=4, bg=S_FIELD, fg=S_FG, font=(UI_FONT, 10))

        def change(d):
            v = max(6, min(28, var.get() + d))
            var.set(v)
            lbl.configure(text=str(v))
            self._set(key, v)
        self._btn(ctl, "−", lambda: change(-1), S_CARD, padx=8, pady=1).pack(side=tk.LEFT)
        lbl.pack(side=tk.LEFT, padx=2, ipady=3)
        self._btn(ctl, "+", lambda: change(1), S_CARD, padx=8, pady=1).pack(side=tk.LEFT)
        lbl.bind("<MouseWheel>", lambda e: change(1 if e.delta > 0 else -1))

    def _weight_control(self, ctl, key):
        cur = self._get(key) or "normal"
        btns = {}

        def choose(v):
            for k, b in btns.items():
                b.set_active(k == v)
            self._set(key, v)
        for value, text in self.WEIGHTS:
            f = (UI_FONT, 9, value) if value != "normal" else (UI_FONT, 9)
            b = FlatButton(ctl, text, lambda v=value: choose(v), font=f, padx=8, pady=2, kind="toggle")
            b.set_colors(S_FIELD, S_FG, _shade(S_FIELD, 0.08), self._accent())
            b.pack(side=tk.LEFT, padx=1)
            btns[value] = b
        for k, b in btns.items():
            b.set_active(k == cur)

    def _build_save_dir(self, card):
        p = self.player
        _mk(tk.Label, card, text="Скачанные MP3 и плейлисты сохраняются в подпапку Staroe_radio_downloads",
            bg=S_CARD, fg=S_DIM, font=(UI_FONT, 9), anchor="w").grid(row=0, column=0, columnspan=2,
                                                                     sticky="w", padx=14, pady=(10, 4))
        line = _mk(tk.Frame, card, bg=S_CARD)
        line.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6))
        var = tk.StringVar(value=p.last_save_dir)
        ent = _mk(tk.Entry, line, textvariable=var, bg=S_FIELD, fg=S_FG, insertbackground=S_FG,
                  relief="flat", font=(UI_FONT, 10), highlightthickness=1,
                  highlightbackground=S_BORDER, highlightcolor=self._accent())
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        def on_write(*_):
            v = var.get().strip()
            if v:
                p.last_save_dir = v
        var.trace_add("write", on_write)

        def browse():
            d = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~"),
                                        title="Папка для сохранения", parent=self)
            if d:
                var.set(os.path.normpath(d))
        self._btn(line, "📁 Выбрать…", browse, S_CARD).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(line, "Открыть", lambda: p._open_folder(var.get()), S_CARD, fg=S_DIM).pack(side=tk.LEFT)

        def toggle_ask():
            p.ask_save_dir = not p.ask_save_dir
            ask.set_active(p.ask_save_dir)
            ask.configure(text=("☑" if p.ask_save_dir else "☐") + "  Спрашивать папку при каждом сохранении")
        ask = FlatButton(card, "", toggle_ask, font=(UI_FONT, 10), padx=12, pady=4, kind="toggle")
        ask.set_colors(S_CARD, S_FG, _shade(S_CARD, 0.06), self._accent())
        ask.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ask.set_active(p.ask_save_dir)
        ask.configure(text=("☑" if p.ask_save_dir else "☐") + "  Спрашивать папку при каждом сохранении")

    def _build_schemes(self, card):
        _mk(tk.Label, card, text="Схема — это набор всех цветов и шрифтов. Хранятся в папке color_schemes.",
            bg=S_CARD, fg=S_DIM, font=(UI_FONT, 9), anchor="w").grid(row=0, column=0, columnspan=2,
                                                                     sticky="w", padx=14, pady=(10, 6))
        lb = _mk(tk.Listbox, card, bg=S_FIELD, fg=S_FG, selectbackground=self._accent(),
                 selectforeground="#ffffff", relief="flat", highlightthickness=0, bd=0,
                 font=(UI_FONT, 10), activestyle="none", height=8)
        lb.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 10))
        self.scheme_list = lb
        side = _mk(tk.Frame, card, bg=S_CARD)
        side.grid(row=1, column=1, sticky="n", padx=(0, 12))
        self._btn(side, "Применить", self._load_scheme, S_CARD, kind="primary").pack(fill=tk.X, pady=(0, 4))
        self.del_btn = self._btn(side, "Удалить", self._delete_scheme, S_CARD, fg=S_DIM)
        self.del_btn.pack(fill=tk.X)
        lb.bind("<Double-Button-1>", lambda e: self._load_scheme())

        line = _mk(tk.Frame, card, bg=S_CARD)
        line.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        self.scheme_name = tk.StringVar()
        ent = _mk(tk.Entry, line, textvariable=self.scheme_name, bg=S_FIELD, fg=S_FG, insertbackground=S_FG,
                  relief="flat", font=(UI_FONT, 10), highlightthickness=1,
                  highlightbackground=S_BORDER, highlightcolor=self._accent())
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        ent.bind("<Return>", lambda e: self._save_scheme())
        self._btn(line, "Сохранить текущие цвета как схему", self._save_scheme, S_CARD).pack(side=tk.LEFT, padx=(8, 0))
        self._refresh_schemes()

    # ── схемы ──────────────────────────────────────────────────────
    def _refresh_schemes(self):
        files = sorted(glob.glob(os.path.join(self.schemes_dir, "*.json")))
        self.scheme_list.delete(0, tk.END)
        for f in files:
            self.scheme_list.insert(tk.END, os.path.splitext(os.path.basename(f))[0])

    def _selected_scheme(self):
        sel = self.scheme_list.curselection()
        return self.scheme_list.get(sel[0]) if sel else None

    def _load_scheme(self):
        name = self._selected_scheme()
        if not name:
            return
        try:
            with open(os.path.join(self.schemes_dir, f"{name}.json"), 'r', encoding='utf-8') as f:
                self.cfg = _deep_merge(self.player.default_colors, json.load(f))
            self._changed()
            self.player.log(f"📂 Схема загружена: {name}")
        except Exception as e:
            self.player.log(f"❌ Не удалось загрузить схему: {e}")

    def _save_scheme(self):
        name = "".join(c for c in self.scheme_name.get().strip() if c not in r'\/:*?"<>|')
        if not name:
            return
        try:
            with open(os.path.join(self.schemes_dir, f"{name}.json"), 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            self.scheme_name.set("")
            self._refresh_schemes()
            self.player.log(f"💾 Схема сохранена: {name}")
        except Exception as e:
            self.player.log(f"❌ Не удалось сохранить схему: {e}")

    def _delete_scheme(self):
        name = self._selected_scheme()
        if not name:
            return
        # Подтверждение без системного диалога: второй клик в течение 3 секунд
        if getattr(self, "_del_armed", None) != name:
            self._del_armed = name
            self.del_btn.configure(text="Точно удалить?")
            self.after(3000, self._disarm_delete)
            return
        try:
            os.remove(os.path.join(self.schemes_dir, f"{name}.json"))
            self.player.log(f"🗑 Схема удалена: {name}")
        except Exception as e:
            self.player.log(f"❌ Не удалось удалить схему: {e}")
        self._disarm_delete()
        self._refresh_schemes()

    def _disarm_delete(self):
        self._del_armed = None
        try:
            self.del_btn.configure(text="Удалить")
        except tk.TclError:
            pass

    # ── значения ───────────────────────────────────────────────────
    def _get(self, key, src=None):
        src = self.cfg if src is None else src
        section, sub, field = key
        try:
            return (src[section] if sub is None else src[section][sub]).get(field)
        except (KeyError, TypeError, AttributeError):
            return None

    def _set(self, key, value):
        section, sub, field = key
        if sub is None:
            self.cfg.setdefault(section, {})[field] = value
        else:
            self.cfg.setdefault(section, {}).setdefault(sub, {})[field] = value
        self._changed()

    def _changed(self):
        self.dirty = True
        self._update_status()
        if self._apply_job:
            self.after_cancel(self._apply_job)
        self._apply_job = self.after(80, self._apply_live)

    def _apply_live(self):
        import copy
        self._apply_job = None
        self.player.log_colors = copy.deepcopy(self.cfg)
        self.player.apply_colors()
        set_titlebar_color(self, self._tb_color())

    # ── сохранить / отменить / закрыть ─────────────────────────────
    def _save(self):
        if self._apply_job:
            self.after_cancel(self._apply_job)
            self._apply_live()
        try:
            with open(self.player.colors_file, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            self.dirty = False
            self._update_status()
            self.player.save_state(quiet=True)
            self.player.log("💾 Настройки сохранены")
        except Exception as e:
            self.player.log(f"❌ Не удалось сохранить настройки: {e}")

    def _revert(self):
        import copy
        self.player.load_colors_config()
        self.cfg = copy.deepcopy(self.player.log_colors)
        self.player.apply_colors()
        self.dirty = False
        set_titlebar_color(self, self._tb_color())
        if self.winfo_exists() and self._page:
            self._show_page(self._page)
            self._update_status()

    def _close_popup(self):
        if self._popup is not None:
            try:
                self._popup.close()
            except Exception:
                pass
            self._popup = None

    def _close_popup_on_click(self, event):
        if self._popup is not None and not str(event.widget).startswith(str(self._popup)):
            self.after(10, self._close_popup)

    def _on_close(self):
        self._close_popup()
        if self.dirty:
            self._build_bottom_confirm()
            return
        self._destroy()

    def _destroy(self):
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.player._settings_win = None
        self.player._sync_toggle_buttons()
        self.destroy()



if __name__ == "__main__":
    root = ttkbootstrap.Window(themename="darkly")

    app = StaroeRadioPlayer(root)
    app.log(set_app_icon(root, app.script_dir, app.log_colors.get("buttons", {}).get("accent", "#3d7be0")))

    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    root.mainloop()
