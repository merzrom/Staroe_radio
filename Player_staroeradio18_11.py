
import os
import sys
import glob
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, colorchooser, filedialog
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

    def setup_ui(self):
        # ========= PanedWindow для изменяемых границ =========
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#212121", sashwidth=5)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Левая часть — вертикальный PanedWindow (результаты + описание)
        left_paned = tk.PanedWindow(paned_window, orient=tk.VERTICAL, bg="#212121", sashwidth=5)
        paned_window.add(left_paned, width=585)

        # Верхняя левая часть - результаты поиска
        list_frame = tk.LabelFrame(left_paned, text="Результаты поиска", bg="#212121")
        list_frame.config(fg="#5E5C5E")
        left_paned.add(list_frame, height=350)

        # === ПАНЕЛЬ ПОИСКА ===
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        self.search_entry = ttk.Entry(search_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda e: self.search())

        ttk.Button(search_frame, text="🔍", command=self.search).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(search_frame, text="📋", command=self.paste).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(search_frame, text="📻", command=self.load_program, width=4).pack(side=tk.LEFT, padx=(0, 3))
        # ttk.Button(search_frame, text="💾 M3U",  command=self.save_m3u).pack(side=tk.LEFT, padx=(0, 3))
        # ttk.Button(search_frame, text="💿 MP3",  command=self.download_selected_mp3).pack(side=tk.LEFT, padx=(0, 3))
        # ttk.Button(search_frame, text="💿 Скачать все", command=self.download_all_mp3).pack(side=tk.LEFT)

        self.file_count_label = ttk.Label(search_frame, text="")
        self.file_count_label.pack(side=tk.RIGHT, padx=(10, 0))
        # ====================================

        # Список результатов
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        results_hscroll = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        results_hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.results_listbox = tk.Text(
            list_frame,
            yscrollcommand=scrollbar.set,
            xscrollcommand=results_hscroll.set,
            font=("Consolas", 10),
            height=15,
            width=50,
            wrap=tk.NONE
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
        info_frame = tk.LabelFrame(left_paned, text="Описание передачи", bg="#212121")
        info_frame.config(fg="#5E5C5E")
        left_paned.add(info_frame, height=200)

        # Цвета области описания из конфига
        info_colors = self.log_colors.get("track_info", {})
        info_fg = info_colors.get("foreground", "#A7F585")
        info_bg = info_colors.get("background", "#1E1E1E")
        info_link_fg = info_colors.get("link_foreground", "#4ECDC4")

        info_scroll = ttk.Scrollbar(info_frame)
        info_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        font_size = info_colors.get("font_size", 9)
        font_weight = info_colors.get("font_weight", "normal")

        self.info_text = tk.Text(
            info_frame,
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
        control_frame = tk.LabelFrame(right_paned, text="Плеер", bg="#212121")
        control_frame.config(fg="#5E5C5E")
        right_paned.add(control_frame, height=350)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(pady=5)

        ttk.Button(btn_frame, text="⏪", command=self.prev_track).pack(side=tk.LEFT, padx=2)
        # ttk.Button(btn_frame, text="▶️", command=self.play_current).pack(side=tk.LEFT, padx=2)
        self.play_pause_btn = ttk.Button(btn_frame, text="⏸️", command=self.pause)
        self.play_pause_btn.pack(side=tk.LEFT, padx=2)
        # ttk.Button(btn_frame, text="⏹", command=self.stop).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⏩", command=self.next_track).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⭐", command=self.add_to_favorites).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="💾", command=self.download_playing_mp3).pack(side=tk.LEFT, padx=2)


        # Громкость
        vol_frame = ttk.Frame(control_frame)
        vol_frame.pack(pady=10, fill=tk.X)

        ttk.Label(vol_frame, text="🔊", foreground="#5E5C5E", font=("Segoe UI Emoji", 16)).pack(side=tk.LEFT, padx=(0, 5))

        self.volume_var = tk.IntVar(value=80)

        self.volume_slider = ttk.Scale(
            vol_frame,
            from_=0,
            to=100,
            variable=self.volume_var,
            orient=tk.HORIZONTAL,
            command=self.set_volume
        )
        self.volume_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.volume_label = ttk.Label(vol_frame, text="80%", width=5, foreground="#828485")
        self.volume_label.pack(side=tk.LEFT, padx=(5, 0))

        # Прогресс
        progress_frame = ttk.Frame(control_frame)
        progress_frame.pack(fill=tk.X, pady=10)

        self.time_current = ttk.Label(progress_frame, text="00:00", foreground="#828485")
        self.time_current.pack(side=tk.LEFT, padx=(0, 5))

        self.progress_slider = ttk.Scale(
            progress_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL
        )
        self.progress_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.progress_slider.bind("<Button-1>", self.start_seek)
        self.progress_slider.bind("<ButtonRelease-1>", self.end_seek)
        self.progress_slider.bind("<B1-Motion>", self.on_seek_drag)

        self.time_total = ttk.Label(progress_frame, text="00:00", foreground="#828485")
        self.time_total.pack(side=tk.RIGHT, padx=(5, 0))

        # Текущий трек
        player_colors = self.log_colors.get("player_labels", {}).get("current_track", {})
        font_size = player_colors.get("font_size", 10)
        font_weight = player_colors.get("font_weight", "normal")

        self.current_label = ttk.Label(
            control_frame,
            text="Нет трека",
            wraplength=250,
            foreground=player_colors.get("foreground", "#D5B491"),
            background=player_colors.get("background", "#212121"),
            font=("Segoe UI", font_size, font_weight)
        )
        self.current_label.pack(pady=10)

        # ========= Лог =========
        log_frame = tk.LabelFrame(right_paned, text="Лог", bg="#212121")
        log_frame.config(fg="#5E5C5E")
        right_paned.add(log_frame, height=200)

        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        log_hscroll = ttk.Scrollbar(log_frame, orient=tk.HORIZONTAL)
        log_hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.log_text = tk.Text(
            log_frame,
            height=6,
            font=("Consolas", 9),
            yscrollcommand=log_scroll.set,
            xscrollcommand=log_hscroll.set,
            wrap=tk.NONE
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
        if self.current_results and self.current_index > 0:
            self.current_index -= 1
            self._play_and_info()
        else:
            self.log("📋 Это первый трек в списке")

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
        url = "https://staroeradio.ru/program/full"
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
            "log_tags": {
                "timestamp": {
                    "foreground": "#B0BEC5",
                    "description": "Временная метка"
                },
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
            "player_labels": {
                "current_track": {
                    "foreground": "#D5B491",
                    "background": "#212121",
                    "font_size": 11,
                    "font_weight": "italic",
                    "description": "Текущий трек в плеере"
                },
                "volume_label": {
                    "foreground": "#FFD700",
                    "description": "Проценты громкости"
                },
                "time_label": {
                    "foreground": "#4ECDC4",
                    "description": "Время в прогресс-баре"
                }
            },
            "track_info": {
                "foreground": "#64B5F6",
                "background": "#030303",
                "header_foreground": "#FFB74D",
                "link_foreground": "#4ECDC4",
                "font_size": 10,
                "font_weight": "normal",
                "description": "Область описания трека"
            }
        }

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
            # Загружаем существующий конфиг
            try:
                with open(self.colors_file, 'r', encoding='utf-8') as f:
                    self.log_colors = json.load(f)
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
    
        time_str = datetime.now().strftime("%H:%M:%S")
    
        with open(history_file, 'a', encoding='utf-8') as f:
            f.write(f"{time_str}\n")
            f.write(f"{track['id']} -- {track['title']}\n")
            f.write("\n")
    
        self.log(f"📝 Записано в историю: {track['title'][:40]}...")

    def add_to_favorites(self):
        """Записать текущий трек в favorites.txt"""
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

    def on_closing(self):
        self.save_state()
        self.player.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = ttkbootstrap.Window(themename="darkly")

    app = StaroeRadioPlayer(root)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    root.mainloop()
