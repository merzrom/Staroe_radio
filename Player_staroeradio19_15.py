
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
import threading
import urllib.request
import urllib.error
from urllib.parse import urljoin
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

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
        # ========= PanedWindow для изменяемых границ =========
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#212121", sashwidth=5)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Левая часть — вертикальный PanedWindow (результаты + описание)
        left_paned = tk.PanedWindow(paned_window, orient=tk.VERTICAL, bg="#212121", sashwidth=5)
        paned_window.add(left_paned, width=585)

        _fl_fg = self.log_colors.get("frame_labels", {}).get("title_foreground", "#5E5C5E")
        _ra_bg = self.log_colors.get("results_area", {}).get("background", "#0d0d0d")

        # Верхняя левая часть - результаты поиска
        self.list_frame = tk.LabelFrame(left_paned, text="Результаты поиска", bg=_ra_bg)
        self.list_frame.config(fg=_fl_fg)
        left_paned.add(self.list_frame, height=350)

        # === ПАНЕЛЬ ПОИСКА ===
        self.search_frame = tk.Frame(self.list_frame, bg=_ra_bg)
        self.search_frame.pack(fill=tk.X, pady=(0, 10))

        self.search_entry = ttk.Entry(self.search_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda e: self.search())

        ttk.Button(self.search_frame, text="🔍", command=self.search).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(self.search_frame, text="📋", command=self.paste).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(self.search_frame, text="📻", command=self.load_program, width=4).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(self.search_frame, text="🕐", command=self.load_history, width=4).pack(side=tk.LEFT, padx=(0, 3))
        # ttk.Button(self.search_frame, text="💾 M3U",  command=self.save_m3u).pack(side=tk.LEFT, padx=(0, 3))
        # ttk.Button(self.search_frame, text="💿 MP3",  command=self.download_selected_mp3).pack(side=tk.LEFT, padx=(0, 3))
        # ttk.Button(self.search_frame, text="💿 Скачать все", command=self.download_all_mp3).pack(side=tk.LEFT)

        self.file_count_label = ttk.Label(self.search_frame, text="")
        self.file_count_label.pack(side=tk.RIGHT, padx=(10, 0))
        # ====================================

        # Список результатов
        scrollbar = ttk.Scrollbar(self.list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        results_hscroll = ttk.Scrollbar(self.list_frame, orient=tk.HORIZONTAL)
        results_hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.results_listbox = tk.Text(
            self.list_frame,
            yscrollcommand=scrollbar.set,
            xscrollcommand=results_hscroll.set,
            font=("Consolas", 10),
            height=15,
            width=50,
            wrap=tk.NONE,
            bg=self.log_colors.get("results_area", {}).get("background", "#0d0d0d")
        )
        self.results_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.results_listbox.yview)
        results_hscroll.config(command=self.results_listbox.xview)

        # Конфигурируем теги для результатов поиска из конфига
        results_tags = self.log_colors.get("results_tags", {})
        for tag_name, tag_config in results_tags.items():
            fg = tag_config.get("foreground", "#FFFFFF")
            bg = tag_config.get("background")
            if bg:
                self.results_listbox.tag_config(tag_name, foreground=fg, background=bg)
            else:
                self.results_listbox.tag_config(tag_name, foreground=fg)

        # Привязываем клик мышью для выбора трека
        self.results_listbox.bind("<Button-1>", self.on_listbox_click)
        # Копирование из результатов поиска
        self.results_listbox.bind("<Control-c>", lambda e: self._copy_selection(self.results_listbox))
        self.results_listbox.bind("<Control-C>", lambda e: self._copy_selection(self.results_listbox))

        # ========= Нижняя левая часть — Описание передачи =========
        # Цвета области описания из конфига
        info_colors = self.log_colors.get("track_info", {})
        info_fg = info_colors.get("foreground", "#A7F585")
        info_bg = info_colors.get("background", "#1E1E1E")
        info_link_fg = info_colors.get("link_foreground", "#4ECDC4")

        self.info_frame = tk.LabelFrame(left_paned, text="Описание передачи", bg=info_bg)
        self.info_frame.config(fg=_fl_fg)
        left_paned.add(self.info_frame, height=200)

        info_scroll = ttk.Scrollbar(self.info_frame)
        info_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        font_size = info_colors.get("font_size", 9)
        font_weight = info_colors.get("font_weight", "normal")

        self.info_text = tk.Text(
            self.info_frame,
            height=8,
            font=("Consolas", font_size, font_weight),
            bg=info_bg,
            wrap=tk.WORD,
            state=tk.DISABLED,
            yscrollcommand=info_scroll.set
        )
        self.info_text.config(fg=info_fg)  # принудительно
        self.info_text.pack(fill=tk.BOTH, expand=True)
        info_scroll.config(command=self.info_text.yview)

        # Теги для описания
        self.info_text.tag_config("link", foreground=info_link_fg, underline=True)
        self.info_text.tag_config("header", foreground=info_colors.get("header_foreground", "#FFB74D"))
        self.info_text.tag_bind("link", "<Enter>", lambda e: self.info_text.config(cursor="hand2"))
        self.info_text.tag_bind("link", "<Leave>", lambda e: self.info_text.config(cursor=""))
        # Копирование из области описания
        self.info_text.bind("<Control-c>", lambda e: self._copy_selection(self.info_text))
        self.info_text.bind("<Control-C>", lambda e: self._copy_selection(self.info_text))

        # Второе PanedWindow для плеера и лога (вертикальное)
        right_paned = tk.PanedWindow(paned_window, orient=tk.VERTICAL, bg="#212121", sashwidth=5)
        paned_window.add(right_paned, width=400)

        # ========= Плеер =========
        self.control_frame = tk.LabelFrame(right_paned, text="Плеер",
            bg=self.log_colors.get("player_labels", {}).get("player_area", {}).get("background", "#212121"))
        self.control_frame.config(fg=_fl_fg)
        right_paned.add(self.control_frame, height=350)

        _player_bg = self.log_colors.get("player_labels", {}).get("player_area", {}).get("background", "#212121")

        # Стиль Scale — фон совпадает с фоном области плеера
        self._player_style = ttk.Style()
        self._player_style.configure("Player.Horizontal.TScale",
                                     background=_player_bg, troughcolor=_player_bg)

        self.btn_frame = tk.Frame(self.control_frame, bg=_player_bg)
        self.btn_frame.pack(pady=5)

        ttk.Button(self.btn_frame, text="⏪", command=self.prev_track).pack(side=tk.LEFT, padx=2)
        # ttk.Button(self.btn_frame, text="▶️", command=self.play_current).pack(side=tk.LEFT, padx=2)
        self.play_pause_btn = ttk.Button(self.btn_frame, text="⏸️", command=self.pause)
        self.play_pause_btn.pack(side=tk.LEFT, padx=2)
        # ttk.Button(self.btn_frame, text="⏹", command=self.stop).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.btn_frame, text="⏩", command=self.next_track).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.btn_frame, text="⭐", command=self.add_to_favorites).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.btn_frame, text="💾", command=self.download_playing_mp3).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.btn_frame, text="🎨", command=self.open_settings).pack(side=tk.LEFT, padx=2)

        # Громкость
        _vol_fg = self.log_colors.get("player_labels", {}).get("volume_label", {}).get("foreground", "#828485")
        _time_fg = self.log_colors.get("player_labels", {}).get("time_label", {}).get("foreground", "#828485")

        self.vol_frame = tk.Frame(self.control_frame, bg=_player_bg)
        self.vol_frame.pack(pady=10, fill=tk.X)

        self.vol_icon_label = tk.Label(self.vol_frame, text="🔊",
                                       bg=_player_bg, fg=_vol_fg,
                                       font=("Segoe UI Emoji", 16))
        self.vol_icon_label.pack(side=tk.LEFT, padx=(0, 5))

        self.volume_var = tk.IntVar(value=80)

        self.volume_slider = ttk.Scale(
            self.vol_frame,
            from_=0,
            to=100,
            variable=self.volume_var,
            orient=tk.HORIZONTAL,
            style="Player.Horizontal.TScale",
            command=self.set_volume
        )
        self.volume_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.volume_label = tk.Label(self.vol_frame, text="80%", width=5,
                                     bg=_player_bg, fg=_vol_fg)
        self.volume_label.pack(side=tk.LEFT, padx=(5, 0))

        # Прогресс
        self.progress_frame = tk.Frame(self.control_frame, bg=_player_bg)
        self.progress_frame.pack(fill=tk.X, pady=10)

        self.time_current = tk.Label(self.progress_frame, text="00:00",
                                     bg=_player_bg, fg=_time_fg)
        self.time_current.pack(side=tk.LEFT, padx=(0, 5))

        self.progress_slider = ttk.Scale(
            self.progress_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            style="Player.Horizontal.TScale",
        )
        self.progress_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.progress_slider.bind("<Button-1>", self.start_seek)
        self.progress_slider.bind("<ButtonRelease-1>", self.end_seek)
        self.progress_slider.bind("<B1-Motion>", self.on_seek_drag)

        self.time_total = tk.Label(self.progress_frame, text="00:00",
                                   bg=_player_bg, fg=_time_fg)
        self.time_total.pack(side=tk.RIGHT, padx=(5, 0))

        # Текущий трек
        player_colors = self.log_colors.get("player_labels", {}).get("current_track", {})
        font_size = player_colors.get("font_size", 10)
        font_weight = player_colors.get("font_weight", "normal")
        wraplength = player_colors.get("wraplength", 350)

        self.current_label = ttk.Label(
            self.control_frame,
            text="Нет трека",
            wraplength=wraplength,
            foreground=player_colors.get("foreground", "#D5B491"),
            background=player_colors.get("background", "#212121"),
            font=("Segoe UI", font_size, font_weight)
        )
        self.current_label.pack(pady=10)

        # ========= Лог =========
        self.log_frame = tk.LabelFrame(right_paned, text="Лог",
            bg=self.log_colors.get("log_area", {}).get("background", "#212121"))
        self.log_frame.config(fg=_fl_fg)
        right_paned.add(self.log_frame, height=200)

        log_scroll = ttk.Scrollbar(self.log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        log_hscroll = ttk.Scrollbar(self.log_frame, orient=tk.HORIZONTAL)
        log_hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.log_text = tk.Text(
            self.log_frame,
            height=6,
            font=("Consolas", 9),
            yscrollcommand=log_scroll.set,
            xscrollcommand=log_hscroll.set,
            wrap=tk.NONE,
            bg=self.log_colors.get("log_area", {}).get("background", "#0d0d0d")
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)
        log_hscroll.config(command=self.log_text.xview)

        # Конфигурируем теги для лога из конфига
        log_tags = self.log_colors.get("log_tags", {})
        for tag_name, tag_config in log_tags.items():
            fg = tag_config.get("foreground", "#FFFFFF")
            bg = tag_config.get("background")
            if bg:
                self.log_text.tag_config(tag_name, foreground=fg, background=bg)
            else:
                self.log_text.tag_config(tag_name, foreground=fg)
        # Копирование из лога
        self.log_text.bind("<Control-c>", lambda e: self._copy_selection(self.log_text))
        self.log_text.bind("<Control-C>", lambda e: self._copy_selection(self.log_text))

        # Вставка в поле поиска глобально
        self.root.bind("<Control-v>", self._global_paste)
        self.root.bind("<Control-V>", self._global_paste)

        # ========= Контекстные меню =========
        self._bind_context_menu(self.search_entry,   can_paste=True,  can_copy=True)
        self._bind_context_menu(self.info_text,      can_paste=False, can_copy=True)
        self._bind_context_menu(self.log_text,       can_paste=False, can_copy=True)
        self._bind_context_menu(self.current_label,  can_paste=False, can_copy=True, is_label=True)
        self._bind_results_context_menu(self.results_listbox)

        # Сохраняем ссылки на PanedWindow для сохранения позиций
        self.paned_window = paned_window
        self.left_paned = left_paned
        self.right_paned = right_paned

        # Гарантируем, что после создания всех виджетов реально применён
        # именно конфиг цветов (та же логика, что и кнопка «Применить» в настройках),
        # а не разрозненные дефолты, читавшиеся по ходу создания виджетов.
        self.apply_colors()

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

    def on_listbox_click(self, event):
        """Обработка клика мышью по окну результатов"""
        pos = self.results_listbox.index(f"@{event.x},{event.y}")
        line_num = int(pos.split('.')[0]) - 1

        if 0 <= line_num < len(self.current_results):
            if self.current_results[line_num].get('is_date'):
                return  # клик на заголовок даты — игнорируем
            self.current_index = line_num
            self.highlight_selected_line()
            self.play_current()
            track = self.current_results[line_num]
            threading.Thread(target=self._fetch_track_info, args=(track,), daemon=True).start()

    def highlight_selected_line(self):
        """Выделить текущую строку цветом"""
        # Удаляем старое выделение
        self.results_listbox.tag_remove("selected", "1.0", tk.END)
        
        # Выделяем новую строку
        if 0 <= self.current_index < len(self.current_results):
            line_start = f"{self.current_index + 1}.0"
            line_end = f"{self.current_index + 1}.end"
            self.results_listbox.tag_add("selected", line_start, line_end)

    def play_selected(self):
        # Получаем текущую строку в Text виджете
        try:
            cursor_pos = self.results_listbox.index(tk.INSERT)
            line_num = int(cursor_pos.split('.')[0]) - 1
            
            if 0 <= line_num < len(self.current_results):
                self.current_index = line_num
                self.highlight_selected_line()
                self.play_current()
            else:
                messagebox.showwarning("Ошибка", "Выберите трек из списка!")
        except:
            messagebox.showwarning("Ошибка", "Выберите трек из списка!")

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
        self.playing_track = track  # Запоминаем реально проигрываемый трек независимо от списка результатов

        cfg = self._get_site_cfg(track)
        url = cfg['stream'].format(id=track['id'])

        self.log(f"▶ Воспроизведение: {track['title']}")

        self._log_to_history(track)

        self.current_label.config(
            text=f"{track['title']}"
        )

        media = self.instance.media_new(url)

        media.add_option(":http-user-agent=Mozilla/5.0")

        self.player.stop()

        self.player.set_media(media)

        time.sleep(0.1)

        self.player.play()

        self.player.audio_set_volume(self.volume_var.get())

        self.is_playing = True
        self.play_pause_btn.config(text="⏸️")

    def pause(self):
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
        self.play_pause_btn.config(text="▶️")
        self.auto_play_enabled = False  # Отключаем автовоспроизведение при ручной остановке
        self.current_label.config(text="Нет трека")
        self.progress_slider.set(0)
        self.time_current.config(text="00:00")
        self.time_total.config(text="00:00")
        self.log("⏹ Остановлено")
        # Включаем обратно через небольшую задержку, чтобы событие окончания не сработало
        self.root.after(500, lambda: setattr(self, 'auto_play_enabled', True))  

    def _play_and_info(self):
        """Воспроизвести текущий трек, обновить выделение и загрузить описание."""
        self.highlight_selected_line()
        self.play_current()
        if 0 <= self.current_index < len(self.current_results):
            track = self.current_results[self.current_index]
            threading.Thread(target=self._fetch_track_info, args=(track,), daemon=True).start()

    def next_track(self):
        if self.current_results and self.current_index + 1 < len(self.current_results):
            self.current_index += 1
            self._play_and_info()
        else:
            self.log("📋 Это последний трек в списке")

    def on_track_end(self, event):
        """Автоматический переход к следующему треку при окончании текущего"""
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
            threading.Thread(target=self._fetch_track_info, args=(prev,), daemon=True).start()
        else:
            self.log("📋 Нет предыдущего трека в истории воспроизведения")

    def set_volume(self, *args):
        volume = int(float(self.volume_var.get()))

        self.player.audio_set_volume(volume)

        self.volume_label.config(text=f"{volume}%")

    def start_seek(self, event):
        self.user_seeking = True

    def on_seek_drag(self, event):
        """Динамически обновлять таймкод слева при перетаскивании ползунка"""
        total_length = self.player.get_length()
        if total_length > 0:
            width = self.progress_slider.winfo_width()
            if width > 0:
                ratio = max(0.0, min(1.0, event.x / width))
                preview_sec = int((ratio * total_length) / 1000)
                self.time_current.config(text=self.format_time(preview_sec))

    def end_seek(self, event):
        if self.player.get_length() > 0:
            position = self.progress_slider.get() / 100
            self.player.set_position(position)

        self.user_seeking = False

    def update_position(self):
        try:
            if self.player.is_playing():

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
        if seconds < 0:
            seconds = 0

        minutes = seconds // 60
        secs = seconds % 60

        return f"{minutes:02d}:{secs:02d}"

    def _choose_save_dir(self):
        """Открыть диалог выбора папки для сохранения. Возвращает путь к папке Staroe_radio_downloads
        внутри выбранной пользователем папки, либо None если пользователь отменил."""
        chosen = filedialog.askdirectory(
            initialdir=self.last_save_dir,
            title="Выберите папку для сохранения"
        )
        if not chosen:
            return None

        # Запоминаем выбранную папку для следующего раза
        self.last_save_dir = chosen

        staroe_radio_dir = os.path.join(chosen, "Staroe_radio_downloads")
        try:
            os.makedirs(staroe_radio_dir, exist_ok=True)
        except Exception as e:
            self.log(f"❌ Ошибка создания папки Staroe_radio_downloads: {e}")
            return None

        return staroe_radio_dir

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

        threading.Thread(target=self._download_mp3_thread, args=(items, download_dir), daemon=True).start()

    def _download_mp3_thread(self, items, download_dir):
        """Внутренняя функция для скачивания MP3 файлов (выполняется в фоновом потоке)"""
        # Проверяем наличие mutagen
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import TIT2
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
                        audio.save()
                    except Exception as e:
                        self._safe_log(f"⚠️  Ошибка добавления тега для {filename}: {e}")

                saved_count += 1
                self._safe_log(f"✅ Сохранен: {filename}")

            except Exception as e:
                self._safe_log(f"❌ Ошибка при обработке {item['id']}: {e}")
                error_count += 1

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

    def save_state(self):
        """Сохранить состояние приложения перед выходом"""
        try:
            # Получаем текущую позицию плеера (в миллисекундах)
            player_time = self.player.get_time()
            player_position = player_time if player_time > 0 else -1

            # Получаем ID трека и полный объект трека, который сейчас воспроизводится или был выбран
            # Приоритет — реально проигрываемый трек (playing_track), он может отличаться
            # от current_results[current_index], если список результатов изменился после начала воспроизведения
            current_track = self.playing_track
            if current_track is None and 0 <= self.current_index < len(self.current_results):
                current_track = self.current_results[self.current_index]
            current_track_id = current_track['id'] if current_track else None

            # Получаем размер и позицию окна
            window_geometry = self.root.geometry()

            # Получаем позиции разделителей PanedWindow
            paned_sash_pos = self.paned_window.sash_coord(0)[0] if self.paned_window.sash_coord(0) else 525
            right_paned_sash_pos = self.right_paned.sash_coord(0)[1] if self.right_paned.sash_coord(0) else 350
            try:
                left_paned_sash_pos = self.left_paned.sash_coord(0)[1] if self.left_paned.sash_coord(0) else 350
            except Exception:
                left_paned_sash_pos = 350
            try:
                right_paned_sash2_pos = self.right_paned.sash_coord(1)[1] if self.right_paned.sash_coord(1) else 450
            except Exception:
                right_paned_sash2_pos = 450

            state = {
                "search_query": self.search_entry.get(),
                "current_results": self.current_results,
                "current_index": self.current_index,
                "player_position": player_position,
                "current_track_id": current_track_id,
                "current_track": current_track,
                "volume": self.volume_var.get(),
                "window_geometry": window_geometry,
                "paned_sash_position": paned_sash_pos,
                "left_paned_sash_position": left_paned_sash_pos,
                "right_paned_sash_position": right_paned_sash_pos,
                "right_paned_sash2_position": right_paned_sash2_pos,
                "last_save_dir": self.last_save_dir
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

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

            # Восстанавливаем позиции разделителей PanedWindow
            paned_sash_pos = state.get("paned_sash_position")
            right_paned_sash_pos = state.get("right_paned_sash_position")

            if paned_sash_pos:
                try:
                    self.root.after(100, lambda v=paned_sash_pos: self.paned_window.sash_place(0, int(v), 1))
                except:
                    pass

            if right_paned_sash_pos:
                try:
                    self.root.after(100, lambda v=right_paned_sash_pos: self.right_paned.sash_place(0, 1, int(v)))
                except:
                    pass

            left_paned_sash_pos = state.get("left_paned_sash_position")
            if left_paned_sash_pos:
                try:
                    self.root.after(100, lambda v=left_paned_sash_pos: self.left_paned.sash_place(0, 1, int(v)))
                except:
                    pass

            # Восстанавливаем поисковый запрос
            search_query = state.get("search_query", "")
            if search_query:
                self.search_entry.insert(0, search_query)

            # Восстанавливаем папку сохранения
            saved_dir = state.get("last_save_dir")
            if saved_dir and os.path.isdir(saved_dir):
                self.last_save_dir = saved_dir

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
                self.current_label.config(text=f"{track['title']}")
                self.highlight_selected_line()
                threading.Thread(target=self._fetch_track_info, args=(track,), daemon=True).start()
            elif current_track:
                # Трек был выбран, но в текущих результатах (другое расписание/поиск) его нет —
                # восстанавливаем его отдельно, чтобы название и описание не пропадали
                self.current_results = [current_track]
                self.current_index = 0
                self.update_results_list()
                self.current_label.config(text=f"{current_track['title']}")
                self.highlight_selected_line()
                threading.Thread(target=self._fetch_track_info, args=(current_track,), daemon=True).start()

            # Восстанавливаем громкость
            volume = state.get("volume", 80)
            self.volume_var.set(volume)
            self.set_volume(volume)
            self.log(f"🔊 Громкость восстановлена: {volume}%")

            # Восстанавливаем позицию плеера
            player_position = state.get("player_position", -1)

            if player_position > 0 and current_track:
                # Запускаем трек и устанавливаем позицию
                self.root.after(500, lambda t=current_track: self._restore_playback(t, player_position))

        except Exception as e:
            self.log(f"⚠️  Ошибка загрузки состояния: {e}")

    def _restore_playback(self, track, position):
        """Восстановить воспроизведение с сохранённой позиции для указанного трека,
        независимо от текущих результатов поиска."""
        try:
            cfg = self._get_site_cfg(track)
            url = cfg['stream'].format(id=track['id'])

            media = self.instance.media_list_new()
            media.add_media(self.instance.media_new(url))
            self.player.set_media(media[0])
            self.player.play()

            self.playing_track = track
            self.current_label.config(text=f"{track['title']}")
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

    def _fetch_track_info(self, track):
        """Получить описание и картинки трека со страницы (в фоновом потоке)"""
        cfg = self._get_site_cfg(track)
        audio_id = track['id']
        url = cfg['info'].format(id=audio_id)
        description = ""
        image_links = []
        page_links = []

        if not HAS_BS4:
            self.root.after(0, lambda: self._display_track_info(
                audio_id, "⚠️  Для парсинга описания установите beautifulsoup4:\npip install beautifulsoup4", [], [], track.get('source', 'staroeradio.txt')
            ))
            return

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
            description = f"❌ Ошибка загрузки страницы: {e}"

        self.root.after(0, lambda: self._display_track_info(audio_id, description, image_links, page_links, track.get('source', 'staroeradio.txt')))

    def load_program(self):
        """Загрузить программу передач со staroeradio.ru/program/full"""
        if not HAS_BS4:
            messagebox.showwarning("Ошибка", "Для парсинга расписания установите:\npip install beautifulsoup4")
            return
        self.log("📻 Загружаем программу передач...")
        threading.Thread(target=self._fetch_program, daemon=True).start()

    def _fetch_program(self):
        """Парсим расписание в фоновом потоке."""
        url = "https://staroeradio.ru/program"
        try:
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

            self.root.after(0, lambda: self._apply_program(results))

        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Ошибка загрузки расписания: {e}"))

    def _apply_program(self, results):
        """Применить результаты парсинга расписания к списку."""
        if not results:
            self.log("❌ Расписание не найдено или пусто")
            return
        self.current_results = results
        self.current_index = -1
        self.update_results_list()
        self.log(f"✅ Программа передач загружена: {len(results)} записей")

    def _display_track_info(self, audio_id, description, image_links, page_links=None, source='staroeradio.txt'):
        """Вывести описание и изображения в панель (в главном потоке)"""
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
                        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = resp.read()
                        import io
                        pil_img = Image.open(io.BytesIO(data))
                        # Масштабируем чтобы вписать в ширину панели
                        max_w = 360
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
        from datetime import datetime

        # timestamp = datetime.now().strftime("%H:%M:%S")

        # Вставляем временную метку (серый цвет)
        # self.log_text.insert(
        #     tk.END,
        #     f"[{timestamp}] ",
        #     "timestamp"
        # )

        # Определяем цвет в зависимости от типа сообщения
        if message.startswith("✅"):
            tag = "success"
        elif message.startswith("❌"):
            tag = "error"
        elif message.startswith("⚠️"):
            tag = "warning"
        else:
            tag = "info"

        # Вставляем само сообщение с тегом
        self.log_text.insert(
            tk.END,
            f"{message}\n",
            tag
        )

        self.log_text.see(tk.END)

    def _safe_log(self, message):
        """Вызов log() из фонового потока через главный поток (thread-safe)"""
        self.root.after(0, lambda m=message: self.log(m))

    def load_colors_config(self):
        """Загрузить конфиг цветов, создать если не существует"""
        default_colors = {
            "results_tags": {
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
                }
            },
            "results_area": {
                "background": "#000000",
                "description": "Фон области результатов поиска"
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
                    "font_size": 11,
                    "font_weight": "normal",
                    "wraplength": 350,
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
                "description": "Цвет заголовков областей (Результаты поиска, Описание передачи, Плеер, Лог)"
            },
            "titlebar": {
                "background": "#383838",
                "description": "Цвет заголовка окна Windows (только Windows 10 build 19041+ и Windows 11)"
            }
        }

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

        # ── Результаты: фон области и search_frame ────────────────
        ra_bg = cfg.get("results_area", {}).get("background")
        if ra_bg:
            self.results_listbox.config(bg=ra_bg)
            self.list_frame.config(bg=ra_bg)
            self.search_frame.config(bg=ra_bg)
        # ── Результаты: теги ──────────────────────────────────────
        for tag_name, tag_cfg in cfg.get("results_tags", {}).items():
            fg = tag_cfg.get("foreground")
            bg = tag_cfg.get("background")
            kw = {}
            if fg: kw["foreground"] = fg
            if bg: kw["background"] = bg
            if kw:
                self.results_listbox.tag_config(tag_name, **kw)

        # ── Лог: фон области ──────────────────────────────────────
        la_bg = cfg.get("log_area", {}).get("background")
        if la_bg:
            self.log_text.config(bg=la_bg)
            self.log_frame.config(bg=la_bg)

        # ── Лог: теги ─────────────────────────────────────────────
        for tag_name, tag_cfg in cfg.get("log_tags", {}).items():
            fg = tag_cfg.get("foreground")
            bg = tag_cfg.get("background")
            kw = {}
            if fg: kw["foreground"] = fg
            if bg: kw["background"] = bg
            if kw:
                self.log_text.tag_config(tag_name, **kw)

        # ── Плеер: фон области ────────────────────────────────────
        pa_bg = cfg.get("player_labels", {}).get("player_area", {}).get("background")
        if pa_bg:
            self.control_frame.config(bg=pa_bg)
            self.btn_frame.config(bg=pa_bg)
            self.vol_frame.config(bg=pa_bg)
            self.progress_frame.config(bg=pa_bg)
            self.vol_icon_label.config(bg=pa_bg)
            self.volume_label.config(bg=pa_bg)
            self.time_current.config(bg=pa_bg)
            self.time_total.config(bg=pa_bg)
            self._player_style.configure("Player.Horizontal.TScale",
                                         background=pa_bg, troughcolor=pa_bg)

        # ── Плеер: цвет шрифта громкости и времени ───────────────
        vl_fg = cfg.get("player_labels", {}).get("volume_label", {}).get("foreground")
        if vl_fg:
            self.volume_label.config(fg=vl_fg)
            self.vol_icon_label.config(fg=vl_fg)
        tl_fg = cfg.get("player_labels", {}).get("time_label", {}).get("foreground")
        if tl_fg:
            self.time_current.config(fg=tl_fg)
            self.time_total.config(fg=tl_fg)

        # ── Плеер: текущий трек ───────────────────────────────────
        ct = cfg.get("player_labels", {}).get("current_track", {})
        ct_fg = ct.get("foreground")
        ct_bg = ct.get("background")
        ct_size = ct.get("font_size", 11)
        ct_weight = ct.get("font_weight", "italic")
        ct_wrap = ct.get("wraplength", 350)
        kw = {}
        if ct_fg: kw["foreground"] = ct_fg
        if ct_bg: kw["background"] = ct_bg
        kw["font"] = ("Segoe UI", int(ct_size), ct_weight)
        kw["wraplength"] = int(ct_wrap)
        self.current_label.config(**kw)

        # ── Описание трека ────────────────────────────────────────
        ti = cfg.get("track_info", {})
        if ti.get("foreground"): self.info_text.config(fg=ti["foreground"])
        if ti.get("background"):
            self.info_text.config(bg=ti["background"])
            self.info_frame.config(bg=ti["background"])
        ti_size = ti.get("font_size", 10)
        ti_weight = ti.get("font_weight", "normal")
        self.info_text.config(font=("Consolas", int(ti_size), ti_weight))
        if ti.get("link_foreground"):
            self.info_text.tag_config("link", foreground=ti["link_foreground"])
        if ti.get("header_foreground"):
            self.info_text.tag_config("header", foreground=ti["header_foreground"])

        # ── Заголовки областей ────────────────────────────────────
        fl_fg = cfg.get("frame_labels", {}).get("title_foreground")
        if fl_fg:
            self.list_frame.config(fg=fl_fg)
            self.info_frame.config(fg=fl_fg)
            self.control_frame.config(fg=fl_fg)
            self.log_frame.config(fg=fl_fg)

        # ── Заголовок окна Windows ────────────────────────────────
        tb_bg = cfg.get("titlebar", {}).get("background")
        if tb_bg:
            self._set_titlebar_color(tb_bg)



    def _set_titlebar_color(self, hex_color: str):
        """Устанавливает цвет заголовка окна через Windows DWM API.
        Работает на Windows 10 (build 19041+) и Windows 11.
        На других ОС — молча игнорируется."""
        try:
            import ctypes
            import ctypes.wintypes

            # DWMWA_CAPTION_COLOR = 35 (доступно с Windows 11 build 22000)
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 19041+)
            DWMWA_CAPTION_COLOR     = 35
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            # Конвертируем #rrggbb → COLORREF (0x00bbggrr)
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            colorref = ctypes.c_int(b << 16 | g << 8 | r)

            # Пробуем DWMWA_CAPTION_COLOR (Win11)
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_CAPTION_COLOR,
                ctypes.byref(colorref),
                ctypes.sizeof(colorref)
            )

            if result != 0:
                # Fallback: тёмный режим DWM (Win10)
                dark = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(dark),
                    ctypes.sizeof(dark)
                )
        except Exception:
            pass  # не Windows или нет dwmapi — тихо игнорируем

    def open_settings(self):
        """Открыть окно настроек интерфейса"""
        win = ColorSettingsWindow(self.root, self)
        win.grab_set()

    def on_closing(self):
        self.save_state()
        self.player.stop()
        self.root.destroy()



# ═══════════════════════════════════════════════════════════════════
#  Окно настроек интерфейса
# ═══════════════════════════════════════════════════════════════════
class ColorSettingsWindow(tk.Toplevel):
    """Отдельное окно для редактирования colors_config.json с превью."""

    # Человекочитаемые метки для каждого поля
    FIELD_LABELS = {
        # results_tags
        ("results_tags", "number",      "foreground"):   "Результаты: номер трека",
        ("results_tags", "title",       "foreground"):   "Результаты: название",
        ("results_tags", "date_header", "foreground"):   "Результаты: заголовок даты",
        ("results_tags", "time_text",   "foreground"):   "Результаты: время передачи",
        ("results_tags", "selected",    "foreground"):   "Результаты: выбранная строка (текст)",
        ("results_tags", "selected",    "background"):   "Результаты: выбранная строка (фон)",
        # results area
        ("results_area", None, "background"): "Результаты: фон области",
        # log_tags
        ("log_tags", "success",   "foreground"): "Лог: успех (✅)",
        ("log_tags", "error",     "foreground"): "Лог: ошибка (❌)",
        ("log_tags", "warning",   "foreground"): "Лог: предупреждение (⚠️)",
        ("log_tags", "info",      "foreground"): "Лог: информация",
        # log area
        ("log_area", None, "background"): "Лог: фон области",
        # player_labels
        ("player_labels", "current_track", "foreground"):  "Плеер: текущий трек (текст)",
        ("player_labels", "current_track", "background"):  "Плеер: текущий трек (фон)",
        ("player_labels", "current_track", "font_size"):   "Плеер: размер шрифта трека",
        ("player_labels", "current_track", "font_weight"): "Плеер: жирный/курсив трека",
        ("player_labels", "current_track", "wraplength"):  "Плеер: ширина переноса (px)",
        ("player_labels", "player_area",   "background"):  "Плеер: фон области",
        ("player_labels", "volume_label",  "foreground"):  "Плеер: иконка 🔊 и громкость %",
        ("player_labels", "time_label",    "foreground"):  "Плеер: время трека",
        # track_info
        ("track_info", None, "foreground"):        "Описание: текст",
        ("track_info", None, "background"):        "Описание: фон",
        ("track_info", None, "header_foreground"): "Описание: заголовок",
        ("track_info", None, "link_foreground"):   "Описание: ссылка",
        ("track_info", None, "font_size"):         "Описание: размер шрифта",
        ("track_info", None, "font_weight"):       "Описание: жирный/курсив",
        # frame_labels
        ("frame_labels", None, "title_foreground"): "Заголовки областей (Плеер, Лог и др.)",
        # titlebar
        ("titlebar", None, "background"): "Заголовок окна Windows (фон)",
    }

    # Поля, которые не цвет, а что-то другое
    FONT_SIZE_FIELDS  = {"font_size", "wraplength"}
    FONT_WEIGHT_FIELDS = {"font_weight"}

    SECTION_TITLES = {
        "results_tags":  "Список результатов — теги",
        "results_area":  "Список результатов — область",
        "log_tags":      "Лог — теги",
        "log_area":      "Лог — область",
        "player_labels": "Плеер",
        "track_info":    "Описание трека",
        "frame_labels":  "Заголовки областей",
        "titlebar":      "Заголовок окна Windows",
    }

    def __init__(self, parent, player):
        super().__init__(parent)
        self.player = player
        self.title("🎨 Настройки интерфейса")
        self.geometry("680x620")
        self.resizable(True, True)
        self.configure(bg="#1a1a1a")

        # Рабочая копия конфига
        import copy
        self.cfg = copy.deepcopy(player.log_colors)

        # Папка для схем
        self.schemes_dir = os.path.join(player.script_dir, "color_schemes")
        os.makedirs(self.schemes_dir, exist_ok=True)

        self._build_ui()
        self._populate_rows()

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        BG = "#1a1a1a"

        # Верхняя панель: схемы
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=8, pady=6)

        tk.Label(top, text="Схема:", bg=BG, fg="#aaaaaa").pack(side=tk.LEFT)
        self.scheme_var = tk.StringVar()
        self.scheme_combo = ttk.Combobox(top, textvariable=self.scheme_var, width=22, state="readonly")
        self.scheme_combo.pack(side=tk.LEFT, padx=(4, 8))
        self._refresh_schemes()

        ttk.Button(top, text="Загрузить", command=self._load_scheme).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Сохранить как…", command=self._save_scheme).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Удалить", command=self._delete_scheme).pack(side=tk.LEFT, padx=2)

        # Разделитель
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8)

        # Прокручиваемая область параметров
        container = tk.Frame(self, bg=BG)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=BG)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(e):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1*(e.delta/120)), "units")

        self._mw_id = self.bind_all("<MouseWheel>", _on_mousewheel)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Нижняя панель: кнопки применения
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(bottom, text="✅ Применить",       command=self._apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="💾 Сохранить в файл", command=self._save_to_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="↩ Сбросить",         command=self._reset).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="✖ Закрыть",          command=self._on_close).pack(side=tk.RIGHT, padx=4)

    def _on_close(self):
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.destroy()

    # ── Строки редактирования ───────────────────────────────────────
    def _populate_rows(self):
        """Создаёт строки для каждого редактируемого параметра."""
        BG = "#1a1a1a"
        self.widgets = {}  # key → (type, widget/var)

        # Заголовок секции
        def section(title):
            tk.Label(
                self.scroll_frame, text=f"  {title}",
                bg="#2a2a2a", fg="#FFD54F",
                font=("Consolas", 9, "bold"),
                anchor="w"
            ).pack(fill=tk.X, pady=(8, 2))

        prev_section = None
        for key, label in self.FIELD_LABELS.items():
            section_name = key[0]
            if section_name != prev_section:
                section(self.SECTION_TITLES.get(section_name, section_name))
                prev_section = section_name

            field = key[2]
            current_val = self._get_cfg_val(key)

            row = tk.Frame(self.scroll_frame, bg=BG)
            row.pack(fill=tk.X, padx=4, pady=1)

            tk.Label(row, text=label, bg=BG, fg="#cccccc",
                     width=40, anchor="w",
                     font=("Consolas", 9)).pack(side=tk.LEFT)

            if field in self.FONT_WEIGHT_FIELDS:
                # Выпадающий список bold/italic/normal
                var = tk.StringVar(value=current_val or "normal")
                cb = ttk.Combobox(row, textvariable=var, width=10,
                                  values=["normal", "bold", "italic", "bold italic"],
                                  state="readonly")
                cb.pack(side=tk.LEFT, padx=4)
                self.widgets[key] = ("combo", var)

            elif field in self.FONT_SIZE_FIELDS:
                # Спиннер: для wraplength диапазон 50-1000, для font_size 6-24
                if field == "wraplength":
                    frm, to = 50, 1000
                else:
                    frm, to = 6, 24
                var = tk.IntVar(value=int(current_val or (350 if field == "wraplength" else 10)))
                sp = ttk.Spinbox(row, from_=frm, to=to, textvariable=var, width=6)
                sp.pack(side=tk.LEFT, padx=4)
                self.widgets[key] = ("spin", var)

            else:
                # Цвет: квадрат-превью + поле ввода + кнопка палитры
                color = current_val or "#ffffff"
                preview = tk.Label(row, bg=color, width=3, relief="solid", bd=1)
                preview.pack(side=tk.LEFT, padx=(0, 4))

                var = tk.StringVar(value=color)

                entry = ttk.Entry(row, textvariable=var, width=10,
                                  font=("Consolas", 9))
                entry.pack(side=tk.LEFT, padx=(0, 4))

                def _on_entry_change(sv=var, lbl=preview):
                    v = sv.get().strip()
                    try:
                        lbl.winfo_rgb(v)  # валидация
                        lbl.config(bg=v)
                    except Exception:
                        pass

                var.trace_add("write", lambda *a, sv=var, lbl=preview: _on_entry_change(sv, lbl))

                def _pick(sv=var, lbl=preview):
                    init = sv.get()
                    try:
                        result = colorchooser.askcolor(color=init, title="Выберите цвет")
                    except Exception:
                        result = (None, None)
                    if result and result[1]:
                        sv.set(result[1])
                        lbl.config(bg=result[1])

                ttk.Button(row, text="🎨", width=3, command=_pick).pack(side=tk.LEFT)
                self.widgets[key] = ("color", var)

    # ── Чтение / запись значений из рабочей копии cfg ──────────────
    def _get_cfg_val(self, key):
        section, subsection, field = key
        try:
            if subsection is None:
                return self.cfg[section].get(field)
            else:
                return self.cfg[section][subsection].get(field)
        except (KeyError, TypeError):
            return None

    def _set_cfg_val(self, key, value):
        section, subsection, field = key
        if subsection is None:
            self.cfg.setdefault(section, {})[field] = value
        else:
            self.cfg.setdefault(section, {}).setdefault(subsection, {})[field] = value

    def _collect_widgets(self):
        """Переносит значения из виджетов в self.cfg."""
        for key, (wtype, var) in self.widgets.items():
            if wtype == "spin":
                self._set_cfg_val(key, int(var.get()))
            else:
                self._set_cfg_val(key, var.get())

    # ── Применить / сохранить / сбросить ───────────────────────────
    def _apply(self):
        self._collect_widgets()
        self.player.log_colors = self.cfg
        self.player.apply_colors()
        self.player.log("🎨 Настройки применены")

    def _save_to_file(self):
        self._collect_widgets()
        try:
            with open(self.player.colors_file, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            self.player.log_colors = self.cfg
            self.player.apply_colors()
            self.player.log(f"💾 Сохранено в {self.player.colors_file}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

    def _reset(self):
        """Перечитать конфиг с диска (отменить несохранённые правки)."""
        import copy
        self.player.load_colors_config()
        self.cfg = copy.deepcopy(self.player.log_colors)
        # Пересоздаём строки
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.widgets = {}
        self._populate_rows()
        self.player.log("↩ Настройки сброшены к файлу")

    # ── Схемы ───────────────────────────────────────────────────────
    def _refresh_schemes(self):
        files = sorted(glob.glob(os.path.join(self.schemes_dir, "*.json")))
        names = [os.path.splitext(os.path.basename(f))[0] for f in files]
        self.scheme_combo["values"] = names
        if names:
            self.scheme_var.set(names[0])

    def _save_scheme(self):
        self._collect_widgets()
        name = simpledialog.askstring(
            "Сохранить схему", "Название схемы:", parent=self)
        if not name:
            return
        # Убираем недопустимые символы для имени файла
        safe = "".join(c for c in name if c not in r'\/:*?"<>|')
        path = os.path.join(self.schemes_dir, f"{safe}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            self._refresh_schemes()
            self.scheme_var.set(safe)
            self.player.log(f"💾 Схема сохранена: {safe}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _load_scheme(self):
        name = self.scheme_var.get()
        if not name:
            return
        path = os.path.join(self.schemes_dir, f"{name}.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                import copy
                self.cfg = json.load(f)
            for w in self.scroll_frame.winfo_children():
                w.destroy()
            self.widgets = {}
            self._populate_rows()
            self.player.log(f"📂 Схема загружена: {name}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _delete_scheme(self):
        name = self.scheme_var.get()
        if not name:
            return
        if not messagebox.askyesno("Удалить?", f"Удалить схему «{name}»?"):
            return
        path = os.path.join(self.schemes_dir, f"{name}.json")
        try:
            os.remove(path)
            self._refresh_schemes()
            self.player.log(f"🗑 Схема удалена: {name}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


if __name__ == "__main__":
    root = ttkbootstrap.Window(themename="darkly")

    app = StaroeRadioPlayer(root)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    root.mainloop()
