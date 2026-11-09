import os
import re
import json
import datetime
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

CONFIG_FILE = "video_muxer_config.json"

# -------------------- Тёмная тема --------------------
DARK_BG = "#1e1e1e"
DARK_FG = "#dcdcdc"
DARK_ENTRY_BG = "#2d2d2d"
DARK_BTN_BG = "#3c3c3c"
LIGHT_BG = "#f0f0f0"
LIGHT_FG = "#000000"

# -------------------- Утилиты --------------------

def browse_file(entry, filetypes):
    filename = filedialog.askopenfilename(filetypes=filetypes)
    if filename:
        entry.delete(0, tk.END)
        entry.insert(0, filename)

def browse_save(entry):
    filename = filedialog.asksaveasfilename(
        defaultextension=".mp4",
        filetypes=[("MP4 files", "*.mp4"), ("MKV files", "*.mkv"),
                   ("MOV files", "*.mov"), ("AVI files", "*.avi"),
                   ("WEBM files", "*.webm"), ("All files", "*.*")]
    )
    if filename:
        entry.delete(0, tk.END)
        entry.insert(0, filename)

def browse_ffmpeg(entry):
    filename = filedialog.askopenfilename(
        filetypes=[("ffmpeg.exe", "ffmpeg.exe"), ("All files", "*.*")]
    )
    if filename:
        entry.delete(0, tk.END)
        entry.insert(0, filename)

def open_folder(path):
    folder = os.path.dirname(path) if os.path.isfile(path) else path
    if folder and os.path.isdir(folder):
        os.startfile(folder)

def auto_output_name(video_path):
    """Создаёт <имя_видео>_dual.<ext> в той же папке."""
    if not video_path:
        return ""
    base, ext = os.path.splitext(video_path)
    return f"{base}_dual{ext}"


# -------------------- Основной класс --------------------

class MuxerApp:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.worker = None
        self.stop_flag = False
        self.queue = []
        self.dark_mode = False

        root.title("Продвинутый мультиплексор аудиодорожек (FFmpeg GUI)")
        root.geometry("1000x900")
        root.resizable(True, True)

        font_label = ("Segoe UI", 10)
        pad_x, pad_y = 10, 5

        # -------------------- Меню --------------------
        menubar = tk.Menu(root)
        root.config(menu=menubar)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        self.dark_var = tk.BooleanVar(value=False)
        settings_menu.add_checkbutton(label="Тёмная тема", variable=self.dark_var, command=self.toggle_theme)
        settings_menu.add_separator()
        settings_menu.add_command(label="Сохранить конфиг", command=self.save_config)
        settings_menu.add_command(label="Загрузить конфиг", command=self.load_config)
        settings_menu.add_separator()
        settings_menu.add_command(label="Экспорт лога в файл", command=self.export_log)
        settings_menu.add_command(label="Выход", command=self.on_close)

        # -------------------- Основной контейнер --------------------
        main = tk.Frame(root)
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # --- Параметры обработки ---
        frame_top = tk.LabelFrame(main, text="Параметры обработки", font=("Segoe UI", 10, "bold"))
        frame_top.pack(fill="x", pady=5)

        # Исходное видео
        tk.Label(frame_top, text="Исходное видео:", font=font_label).grid(row=0, column=0, sticky="w", padx=pad_x, pady=pad_y)
        self.entry_video = tk.Entry(frame_top, width=55)
        self.entry_video.grid(row=0, column=1, padx=pad_x, pady=pad_y)
        tk.Button(frame_top, text="Обзор...", command=lambda: browse_file(self.entry_video,
            [("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"), ("All files", "*.*")])
        ).grid(row=0, column=2, padx=pad_x, pady=pad_y)
        tk.Button(frame_top, text="Автоимя", command=self.set_auto_output).grid(row=0, column=3, padx=pad_x, pady=pad_y)

        # Аудиодорожка
        tk.Label(frame_top, text="Аудиодорожка:", font=font_label).grid(row=1, column=0, sticky="w", padx=pad_x, pady=pad_y)
        self.entry_audio = tk.Entry(frame_top, width=55)
        self.entry_audio.grid(row=1, column=1, padx=pad_x, pady=pad_y)
        tk.Button(frame_top, text="Обзор...", command=lambda: browse_file(self.entry_audio,
            [("Audio files", "*.mp3 *.aac *.wav *.m4a *.flac *.ogg *.opus"), ("All files", "*.*")])
        ).grid(row=1, column=2, padx=pad_x, pady=pad_y)

        # Выходной файл
        tk.Label(frame_top, text="Сохранить как:", font=font_label).grid(row=2, column=0, sticky="w", padx=pad_x, pady=pad_y)
        self.entry_output = tk.Entry(frame_top, width=55)
        self.entry_output.grid(row=2, column=1, padx=pad_x, pady=pad_y)
        tk.Button(frame_top, text="Обзор...", command=lambda: browse_save(self.entry_output)).grid(row=2, column=2, padx=pad_x, pady=pad_y)
        tk.Button(frame_top, text="Автоимя", command=self.set_auto_output).grid(row=2, column=3, padx=pad_x, pady=pad_y)

        # Языки и названия
        tk.Label(frame_top, text="Язык исх. дорожки:", font=font_label).grid(row=3, column=0, sticky="w", padx=pad_x, pady=pad_y)
        self.entry_lang1 = tk.Entry(frame_top, width=10)
        self.entry_lang1.insert(0, "rus")
        self.entry_lang1.grid(row=3, column=1, sticky="w", padx=pad_x, pady=pad_y)

        tk.Label(frame_top, text="Название:", font=font_label).grid(row=3, column=1, sticky="e", padx=(180, 5), pady=pad_y)
        self.entry_name1 = tk.Entry(frame_top, width=20)
        self.entry_name1.insert(0, "Русский")
        self.entry_name1.grid(row=3, column=1, sticky="e", padx=(250, 10), pady=pad_y)

        tk.Label(frame_top, text="Язык новой дорожки:", font=font_label).grid(row=4, column=0, sticky="w", padx=pad_x, pady=pad_y)
        self.entry_lang2 = tk.Entry(frame_top, width=10)
        self.entry_lang2.insert(0, "eng")
        self.entry_lang2.grid(row=4, column=1, sticky="w", padx=pad_x, pady=pad_y)

        tk.Label(frame_top, text="Название:", font=font_label).grid(row=4, column=1, sticky="e", padx=(180, 5), pady=pad_y)
        self.entry_name2 = tk.Entry(frame_top, width=20)
        self.entry_name2.insert(0, "English")
        self.entry_name2.grid(row=4, column=1, sticky="e", padx=(250, 10), pady=pad_y)

        # -------------------- Пресеты качества --------------------
        frame_codec = tk.LabelFrame(main, text="Качество аудио", font=("Segoe UI", 10, "bold"))
        frame_codec.pack(fill="x", pady=5)

        tk.Label(frame_codec, text="Пресет:", font=font_label).grid(row=0, column=0, sticky="w", padx=pad_x, pady=pad_y)
        self.preset_var = tk.StringVar(value="Стандарт (192k)")
        presets = [
            "Высокое (320k)",
            "Хорошее (256k)",
            "Стандарт (192k)",
            "Эконом (128k)",
            "Минимум (96k)",
            "Без потерь (FLAC)",
            "Без потерь (PCM)"
        ]
        self.preset_menu = ttk.Combobox(frame_codec, textvariable=self.preset_var, values=presets, state="readonly", width=22)
        self.preset_menu.grid(row=0, column=1, sticky="w", padx=pad_x, pady=pad_y)
        self.preset_menu.bind("<<ComboboxSelected>>", self.on_preset_changed)

        # Кодек и битрейт
        tk.Label(frame_codec, text="Кодек:", font=font_label).grid(row=0, column=2, sticky="e", padx=(40, 5), pady=pad_y)
        self.codec_var = tk.StringVar(value="aac")
        codecs = ["aac", "libmp3lame", "libopus", "ac3", "flac", "pcm_s16le"]
        self.codec_menu = ttk.Combobox(frame_codec, textvariable=self.codec_var, values=codecs, state="readonly", width=12)
        self.codec_menu.grid(row=0, column=3, sticky="w", padx=5, pady=pad_y)
        self.codec_menu.bind("<<ComboboxSelected>>", self.on_codec_changed)

        tk.Label(frame_codec, text="Битрейт:", font=font_label).grid(row=0, column=4, sticky="e", padx=(30, 5), pady=pad_y)
        self.bitrate_var = tk.StringVar(value="192k")
        self.bitrate_menu = ttk.Combobox(frame_codec, textvariable=self.bitrate_var,
            values=["96k", "128k", "160k", "192k", "256k", "320k"], width=8)
        self.bitrate_menu.grid(row=0, column=5, sticky="w", padx=5, pady=pad_y)

        self.bitrate_hint = tk.Label(frame_codec, text="", font=("Segoe UI", 8), fg="gray")
        self.bitrate_hint.grid(row=1, column=0, columnspan=6, sticky="w", padx=pad_x, pady=(0, 5))

        # -------------------- FFmpeg --------------------
        frame_ff = tk.Frame(main)
        frame_ff.pack(fill="x", pady=5)
        tk.Label(frame_ff, text="FFmpeg (если не в PATH):", font=font_label).pack(side="left")
        self.entry_ffmpeg = tk.Entry(frame_ff, width=50)
        self.entry_ffmpeg.insert(0, "ffmpeg.exe")
        self.entry_ffmpeg.pack(side="left", padx=10)
        tk.Button(frame_ff, text="Обзор...", command=lambda: browse_ffmpeg(self.entry_ffmpeg)).pack(side="left")

        # -------------------- Очередь --------------------
        frame_queue = tk.LabelFrame(main, text="Очередь задач", font=("Segoe UI", 10, "bold"))
        frame_queue.pack(fill="both", expand=True, pady=5)

        columns = ("video", "audio", "output", "codec")
        self.tree = ttk.Treeview(frame_queue, columns=columns, show="headings", height=5)
        self.tree.heading("video", text="Исходное видео")
        self.tree.heading("audio", text="Аудио")
        self.tree.heading("output", text="Результат")
        self.tree.heading("codec", text="Кодек")
        for col, w in zip(columns, [200, 200, 200, 80]):
            self.tree.column(col, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        scroll_tree = tk.Scrollbar(frame_queue, command=self.tree.yview)
        scroll_tree.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll_tree.set)

        btn_queue = tk.Frame(frame_queue)
        btn_queue.pack(side="right", fill="y", padx=5)
        tk.Button(btn_queue, text="Добавить в очередь", width=20, command=self.add_to_queue).pack(pady=2)
        tk.Button(btn_queue, text="Удалить выбранное", width=20, command=self.remove_from_queue).pack(pady=2)
        tk.Button(btn_queue, text="Очистить очередь", width=20, command=self.clear_queue).pack(pady=2)

        # -------------------- Прогресс --------------------
        self.progress = ttk.Progressbar(main, orient="horizontal", length=800, mode="determinate")
        self.progress.pack(fill="x", pady=(5, 0))

        self.status_var = tk.StringVar(value="Готов к работе")
        tk.Label(main, textvariable=self.status_var, font=("Segoe UI", 9), anchor="w").pack(fill="x")

        # -------------------- Лог --------------------
        self.log_text = tk.Text(main, height=8, wrap="word", state="disabled",
                                bg=DARK_BG if self.dark_mode else "#ffffff",
                                fg=DARK_FG if self.dark_mode else "#000000",
                                font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, pady=5)

        # -------------------- Кнопки --------------------
        btn_frame = tk.Frame(main)
        btn_frame.pack(fill="x", pady=5)

        self.btn_start = tk.Button(btn_frame, text="▶ Запустить обработку", width=22, command=self.start_queue)
        self.btn_start.pack(side="left", padx=5)

        self.btn_cancel = tk.Button(btn_frame, text="⏹ Отмена", width=12, state="disabled", command=self.cancel_process)
        self.btn_cancel.pack(side="left", padx=5)

        tk.Button(btn_frame, text="💾 Сохранить настройки", width=20, command=self.save_config).pack(side="left", padx=5)
        tk.Button(btn_frame, text="📂 Загрузить настройки", width=20, command=self.load_config).pack(side="left", padx=5)
        tk.Button(btn_frame, text="📤 Экспорт лога", width=16, command=self.export_log).pack(side="left", padx=5)

        self.btn_theme = tk.Button(btn_frame, text="🌙 Тёмная тема", width=16, command=self.toggle_theme)
        self.btn_theme.pack(side="left", padx=5)

        tk.Button(btn_frame, text="📁 Открыть папку", width=14,
                  command=lambda: open_folder(self.entry_output.get())).pack(side="left", padx=5)
        tk.Button(btn_frame, text="✖ Закрыть", width=10, command=self.on_close).pack(side="right", padx=5)

        # Применяем тему при старте (светлая по умолчанию)
        self.apply_theme()

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Инициализация подсказки
        self.on_preset_changed()

    # -------------------- Автоимя --------------------

    def set_auto_output(self):
        video = self.entry_video.get().strip()
        if not video:
            messagebox.showwarning("Внимание", "Сначала выберите исходное видео.")
            return
        auto = auto_output_name(video)
        self.entry_output.delete(0, tk.END)
        self.entry_output.insert(0, auto)
        self.log(f"[i] Автоматическое имя: {os.path.basename(auto)}")

    # -------------------- Пресеты и кодек --------------------

    def on_preset_changed(self, event=None):
        preset = self.preset_var.get()
        mapping = {
            "Высокое (320k)": ("aac", "320k"),
            "Хорошее (256k)": ("aac", "256k"),
            "Стандарт (192k)": ("aac", "192k"),
            "Эконом (128k)": ("aac", "128k"),
            "Минимум (96k)": ("aac", "96k"),
            "Без потерь (FLAC)": ("flac", ""),
            "Без потерь (PCM)": ("pcm_s16le", ""),
        }
        codec, bitrate = mapping.get(preset, ("aac", "192k"))
        self.codec_var.set(codec)
        self.bitrate_var.set(bitrate)
        self.on_codec_changed()

    def on_codec_changed(self, event=None):
        codec = self.codec_var.get()
        if codec in ("flac", "pcm_s16le"):
            self.bitrate_menu.config(state="disabled")
            self.bitrate_hint.config(text="Для этого кодека битрейт игнорируется (lossless/PCM)")
        else:
            self.bitrate_menu.config(state="normal")
            self.bitrate_hint.config(text="")

    # -------------------- Конфиг --------------------

    def save_config(self):
        data = {
            "lang1": self.entry_lang1.get(),
            "name1": self.entry_name1.get(),
            "lang2": self.entry_lang2.get(),
            "name2": self.entry_name2.get(),
            "ffmpeg": self.entry_ffmpeg.get(),
            "codec": self.codec_var.get(),
            "bitrate": self.bitrate_var.get(),
            "preset": self.preset_var.get(),
            "dark_mode": self.dark_mode,
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Готово", f"Настройки сохранены в {CONFIG_FILE}")
            self.log(f"[✓] Конфиг сохранён: {CONFIG_FILE}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")

    def load_config(self):
        if not os.path.isfile(CONFIG_FILE):
            messagebox.showwarning("Внимание", "Файл конфигурации не найден.")
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.entry_lang1.delete(0, tk.END); self.entry_lang1.insert(0, data.get("lang1", "rus"))
            self.entry_name1.delete(0, tk.END); self.entry_name1.insert(0, data.get("name1", "Русский"))
            self.entry_lang2.delete(0, tk.END); self.entry_lang2.insert(0, data.get("lang2", "eng"))
            self.entry_name2.delete(0, tk.END); self.entry_name2.insert(0, data.get("name2", "English"))
            self.entry_ffmpeg.delete(0, tk.END); self.entry_ffmpeg.insert(0, data.get("ffmpeg", "ffmpeg.exe"))
            self.codec_var.set(data.get("codec", "aac"))
            self.bitrate_var.set(data.get("bitrate", "192k"))
            self.preset_var.set(data.get("preset", "Стандарт (192k)"))
            self.dark_mode = data.get("dark_mode", False)
            self.dark_var.set(self.dark_mode)
            self.apply_theme()
            self.on_codec_changed()
            self.log(f"[✓] Конфиг загружен: {CONFIG_FILE}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить: {e}")

    # -------------------- Экспорт лога --------------------

    def export_log(self):
        content = self.log_text.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Экспорт", "Лог пуст.")
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content + "\n")
                messagebox.showinfo("Готово", f"Лог сохранён:\n{filename}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить лог: {e}")

    # -------------------- Тема --------------------

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.dark_var.set(self.dark_mode)
        self.apply_theme()

    def apply_theme(self):
        bg = DARK_BG if self.dark_mode else LIGHT_BG
        fg = DARK_FG if self.dark_mode else LIGHT_FG
        entry_bg = DARK_ENTRY_BG if self.dark_mode else "#ffffff"
        btn_bg = DARK_BTN_BG if self.dark_mode else "SystemButtonFace"
        btn_fg = DARK_FG if self.dark_mode else LIGHT_FG
        log_bg = "#111111" if self.dark_mode else "#ffffff"
        log_fg = "#dcdcdc" if self.dark_mode else "#000000"

        def walk(w):
            try:
                w.configure(bg=bg, fg=fg)
            except tk.TclError:
                pass
            if isinstance(w, (tk.Entry, tk.Text)):
                try:
                    w.configure(bg=entry_bg, fg=fg, insertbackground=fg)
                except tk.TclError:
                    pass
            if isinstance(w, tk.Button):
                try:
                    w.configure(bg=btn_bg, fg=btn_fg, activebackground=btn_bg,
                                activeforeground=btn_fg, highlightbackground=bg)
                except tk.TclError:
                    pass
            for child in w.winfo_children():
                walk(child)

        walk(self.root)
        self.log_text.configure(bg=log_bg, fg=log_fg, insertbackground=log_fg)
        self.btn_theme.config(text="☀ Светлая тема" if self.dark_mode else "🌙 Тёмная тема")

    # -------------------- Очередь --------------------

    def add_to_queue(self):
        video = self.entry_video.get().strip()
        audio = self.entry_audio.get().strip()
        output = self.entry_output.get().strip()
        if not output and video:
            output = auto_output_name(video)

        if not video or not os.path.isfile(video):
            messagebox.showerror("Ошибка", "Укажите существующий исходный видеофайл.")
            return
        if not audio or not os.path.isfile(audio):
            messagebox.showerror("Ошибка", "Укажите существующий файл аудиодорожки.")
            return
        if not output:
            messagebox.showerror("Ошибка", "Укажите путь для сохранения результата.")
            return

        self.queue.append({
            "video": video, "audio": audio, "output": output,
            "lang1": self.entry_lang1.get().strip(), "name1": self.entry_name1.get().strip(),
            "lang2": self.entry_lang2.get().strip(), "name2": self.entry_name2.get().strip(),
            "codec": self.codec_var.get(), "bitrate": self.bitrate_var.get()
        })
        self.tree.insert("", "end", values=(os.path.basename(video), os.path.basename(audio),
                                            os.path.basename(output), self.codec_var.get()))
        self.log(f"[+] Добавлено в очередь: {os.path.basename(video)}")

    def remove_from_queue(self):
        selected = self.tree.selection()
        if not selected:
            return
        for idx_str in selected:
            idx = self.tree.index(idx_str)
            del self.queue[idx]
            self.tree.delete(idx_str)

    def clear_queue(self):
        if messagebox.askyesno("Очистить", "Удалить все задачи из очереди?"):
            self.queue.clear()
            for item in self.tree.get_children():
                self.tree.delete(item)

    # -------------------- Запуск --------------------

    def start_queue(self):
        if not self.queue:
            messagebox.showinfo("Очередь пуста", "Сначала добавьте хотя бы одну задачу в очередь.")
            return
        self.stop_flag = False
        self.btn_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.worker = threading.Thread(target=self.process_queue, daemon=True)
        self.worker.start()

    def process_queue(self):
        total = len(self.queue)
        for i, task in enumerate(self.queue, start=1):
            if self.stop_flag:
                self.log("[!] Обработка остановлена пользователем.")
                break
            self.log(f"\n=== Задача {i}/{total}: {os.path.basename(task['video'])} ===")
            self.set_status(f"Задача {i}/{total}: {os.path.basename(task['video'])}")
            self.progress["value"] = 0

            ffmpeg_path = self.entry_ffmpeg.get().strip() or "ffmpeg.exe"
            if not self.check_ffmpeg(ffmpeg_path):
                self.log("[!] ffmpeg не найден. Пропуск задачи.")
                continue

            duration = self.get_duration(ffmpeg_path, task["video"])
            self.log(f"[i] Длительность: {duration:.2f} сек.")

            cmd = self.build_cmd(ffmpeg_path, task)
            self.log("[>] " + " ".join(cmd))

            ok = self.run_ffmpeg(cmd, duration)
            if not ok:
                self.log(f"[✗] Ошибка в задаче: {os.path.basename(task['video'])}")

        self.set_status("Обработка очереди завершена ✅")
        self.btn_start.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self.process = None
        messagebox.showinfo("Готово", "Обработка очереди завершена.")

    def build_cmd(self, ffmpeg_path, task):
        cmd = [
            ffmpeg_path, "-y",
            "-i", task["video"],
            "-i", task["audio"],
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", task["codec"],
        ]
        if task["codec"] not in ("flac", "pcm_s16le") and task["bitrate"]:
            cmd += ["-b:a", task["bitrate"]]
        cmd += [
            "-metadata:s:a:0", f"language={task['lang1']}",
            "-metadata:s:a:0", f"title={task['name1']}",
            "-metadata:s:a:1", f"language={task['lang2']}",
            "-metadata:s:a:1", f"title={task['name2']}",
            "-shortest",
            "-progress", "pipe:1",
            "-nostats",
            task["output"]
        ]
        return cmd

    def check_ffmpeg(self, ffmpeg_path):
        try:
            subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            return False

    def get_duration(self, ffmpeg_path, video_path):
        ffprobe = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe") if ffmpeg_path != "ffmpeg.exe" else "ffprobe.exe"
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, check=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return float(result.stdout.strip())
        except Exception as e:
            self.log(f"[!] Не удалось определить длительность: {e}")
            return 0.0

    def run_ffmpeg(self, cmd, duration):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            time_re = re.compile(r"out_time_ms=(\d+)")

            for line in self.process.stdout:
                if self.stop_flag:
                    self.process.terminate()
                    break
                line = line.rstrip()
                m = time_re.search(line)
                if m and duration > 0:
                    seconds = int(m.group(1)) / 1_000_000
                    percent = min(100, seconds / duration * 100)
                    self.progress["value"] = percent
                    self.set_status(f"Обработка: {percent:.1f}% ({seconds:.1f}/{duration:.1f} сек.)")
                    continue
                if line.strip():
                    self.log(line)

            self.process.wait()
            return self.process.returncode == 0
        except Exception as e:
            self.log(f"[!] Ошибка выполнения: {e}")
            return False
        finally:
            self.process = None

    def cancel_process(self):
        if self.process and self.process.poll() is None:
            self.log("[!] Отмена текущего процесса...")
            self.stop_flag = True
            try:
                self.process.terminate()
            except Exception:
                pass
        self.btn_cancel.config(state="disabled")

    # -------------------- Логирование --------------------

    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_status(self, text):
        self.status_var.set(text)

    def on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Выход", "Процесс ещё выполняется. Прервать и выйти?"):
                return
            self.stop_flag = True
            self.process.terminate()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MuxerApp(root)
    root.mainloop()