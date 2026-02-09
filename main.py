import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import re
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import pandas as pd

class PowerOutageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📊 Графік відключень електроенергії у Львові")
        self.root.geometry("1200x800")
        self.root.configure(bg='#f0f0f0')
        
        # Стиль для ttk віджетів
        self.setup_styles()
        
        # Дані
        self.data = None
        self.all_groups = ['1.1', '1.2', '1.3', '2.1', '2.2', '2.3', '3.1', '3.2', '3.3', 
                          '4.1', '4.2', '4.3', '5.1', '5.2', '5.3', '6.1', '6.2', '6.3']
        
        # Створення інтерфейсу
        self.create_widgets()
        
        # Спроба завантажити існуючі дані
        self.load_existing_data()
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Кастомні стилі
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'), background='#f0f0f0')
        style.configure('Status.TLabel', font=('Arial', 10), background='#f0f0f0')
        style.configure('Action.TButton', font=('Arial', 10, 'bold'), padding=10)
        
    def create_widgets(self):
        # Головний контейнер
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Налаштування розтягування
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # === ВЕРХНЯ ПАНЕЛЬ ===
        header_frame = ttk.LabelFrame(main_frame, text="🔄 Оновлення даних", padding="10")
        header_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)
        
        # Кнопка завантаження
        self.load_btn = ttk.Button(header_frame, text="🌐 Завантажити актуальні дані", 
                                  command=self.load_data_thread, style='Action.TButton')
        self.load_btn.grid(row=0, column=0, padx=(0, 10))
        
        # Статус
        self.status_label = ttk.Label(header_frame, text="Готовий до завантаження...", 
                                     style='Status.TLabel')
        self.status_label.grid(row=0, column=1, sticky=(tk.W))
        
        # Прогрес-бар
        self.progress = ttk.Progressbar(header_frame, mode='indeterminate')
        self.progress.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # === ЛІВА ПАНЕЛЬ - НАЛАШТУВАННЯ ===
        settings_frame = ttk.LabelFrame(main_frame, text="⚙️ Налаштування", padding="10", width=300)
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        settings_frame.grid_propagate(False)
        
        # Вибір груп для відображення
        ttk.Label(settings_frame, text="📈 Групи для графіка:", style='Header.TLabel').pack(anchor='w', pady=(0, 5))
        
        # Фрейм для чекбоксів груп
        groups_frame = ttk.Frame(settings_frame)
        groups_frame.pack(fill='both', pady=(0, 10))
        
        self.group_vars = {}
        for i, group in enumerate(self.all_groups):
            var = tk.BooleanVar(value=group in ['1.1', '1.2', '2.1', '2.2', '3.1', '3.2'])
            self.group_vars[group] = var
            cb = ttk.Checkbutton(groups_frame, text=f"Група {group}", variable=var,
                               command=self.update_visualization)
            cb.grid(row=i//3, column=i%3, sticky='w', padx=5, pady=2)
        
        # Кнопки керування групами
        group_controls = ttk.Frame(settings_frame)
        group_controls.pack(fill='x', pady=(0, 10))
        
        ttk.Button(group_controls, text="✓ Всі", 
                  command=self.select_all_groups).pack(side='left', padx=(0, 5))
        ttk.Button(group_controls, text="✗ Очистити", 
                  command=self.clear_all_groups).pack(side='left')
        
        # Спільні години
        ttk.Label(settings_frame, text="🤝 Спільні години зі світлом:", style='Header.TLabel').pack(anchor='w', pady=(10, 5))
        
        self.common_text = tk.Text(settings_frame, height=6, font=('Consolas', 9))
        self.common_text.pack(fill='both', pady=(0, 10))
        
        ttk.Button(settings_frame, text="🔍 Знайти спільні години", 
                  command=self.find_common_hours).pack(fill='x', pady=(0, 10))
        
        # Статистика
        ttk.Button(settings_frame, text="📊 Показати статистику", 
                  command=self.show_statistics).pack(fill='x')
        
        # === ПРАВА ПАНЕЛЬ - ГРАФІК ===
        viz_frame = ttk.LabelFrame(main_frame, text="📊 Графік відключень", padding="10")
        viz_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        viz_frame.rowconfigure(0, weight=1)
        viz_frame.columnconfigure(0, weight=1)
        
        # Canvas для matplotlib
        self.canvas_frame = ttk.Frame(viz_frame)
        self.canvas_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.canvas_frame.rowconfigure(0, weight=1)
        self.canvas_frame.columnconfigure(0, weight=1)
        
        # Початкове повідомлення
        self.placeholder_label = ttk.Label(self.canvas_frame, 
                                         text="Завантажте дані для відображення графіка",
                                         font=('Arial', 12))
        self.placeholder_label.grid(row=0, column=0)
        
        # === НИЖНЯ ПАНЕЛЬ - СТАТУС ===
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.update_time_label = ttk.Label(status_frame, text="", style='Status.TLabel')
        self.update_time_label.grid(row=0, column=0, sticky='w')
        
        ttk.Button(status_frame, text="💾 Зберегти графік", 
                  command=self.save_chart).grid(row=0, column=1, sticky='e')
    
    def get_dynamic_html(self, url):
        """Завантаження HTML з використанням Selenium"""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "power-off__text"))
            )
            return driver.page_source
        except Exception as e:
            raise Exception(f"Помилка Selenium: {e}")
        finally:
            driver.quit()
    
    def parse_html_to_data(self, html):
        """Парсинг HTML для отримання даних про відключення"""
        soup = BeautifulSoup(html, 'html.parser')
        text_container = soup.find('div', class_='power-off__text')
        
        if not text_container:
            return None

        update_time_pattern = r"станом на (\d{2}:\d{2})"
        group_pattern = r"Група\s+(\d\.\d)"
        time_pattern = r"(\d{2}:\d{2})\s+(?:до|по)\s+(\d{2}:\d{2})"
        
        final_result = {
            "update_time": "Невідомо",
            "schedules": {}
        }
        
        paragraphs = text_container.find_all('p')
        
        for p in paragraphs:
            text = p.get_text()
            
            update_match = re.search(update_time_pattern, text)
            if update_match:
                final_result["update_time"] = update_match.group(1)
            
            group_match = re.search(group_pattern, text)
            if group_match:
                group_name = group_match.group(1)
                times = re.findall(time_pattern, text)
                if times:
                    final_result["schedules"][group_name] = times
                    
        return final_result
    
    def load_data_thread(self):
        """Запуск завантаження в окремому потоці"""
        self.load_btn.config(state='disabled')
        self.progress.start()
        self.status_label.config(text="Завантаження даних...")
        
        thread = threading.Thread(target=self.load_data_worker)
        thread.daemon = True
        thread.start()
    
    def load_data_worker(self):
        """Робочий метод для завантаження даних"""
        try:
            url = "https://poweron.loe.lviv.ua/"
            html = self.get_dynamic_html(url)
            
            if html:
                data = self.parse_html_to_data(html)
                if data and data["schedules"]:
                    # Збереження у файл
                    with open('schedule.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    
                    self.data = data
                    
                    # Оновлення інтерфейсу в головному потоці
                    self.root.after(0, self.on_data_loaded_success)
                else:
                    self.root.after(0, lambda: self.on_data_loaded_error("Не вдалося знайти дані на сторінці"))
            else:
                self.root.after(0, lambda: self.on_data_loaded_error("Не вдалося завантажити сторінку"))
                
        except Exception as e:
            self.root.after(0, lambda: self.on_data_loaded_error(str(e)))
    
    def on_data_loaded_success(self):
        """Обробка успішного завантаження"""
        self.progress.stop()
        self.load_btn.config(state='normal')
        self.status_label.config(text=f"✅ Дані завантажено успішно!")
        self.update_time_label.config(text=f"Останнє оновлення: {self.data['update_time']}")
        
        # Оновлення чекбоксів груп
        available_groups = list(self.data['schedules'].keys())
        for group, var in self.group_vars.items():
            if group not in available_groups:
                var.set(False)
        
        self.update_visualization()
        messagebox.showinfo("Успіх", "Дані успішно завантажено та збережено!")
    
    def on_data_loaded_error(self, error_msg):
        """Обробка помилки завантаження"""
        self.progress.stop()
        self.load_btn.config(state='normal')
        self.status_label.config(text=f"❌ Помилка: {error_msg}")
        messagebox.showerror("Помилка", f"Не вдалося завантажити дані:\n{error_msg}")
    
    def load_existing_data(self):
        """Завантаження існуючих даних з файлу"""
        try:
            if os.path.exists('schedule.json'):
                with open('schedule.json', 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                self.status_label.config(text="Завантажено дані з файлу")
                self.update_time_label.config(text=f"Останнє оновлення: {self.data['update_time']}")
                self.update_visualization()
        except Exception as e:
            print(f"Не вдалося завантажити існуючі дані: {e}")
    
    def select_all_groups(self):
        """Вибрати всі групи"""
        for var in self.group_vars.values():
            var.set(True)
        self.update_visualization()
    
    def clear_all_groups(self):
        """Очистити всі групи"""
        for var in self.group_vars.values():
            var.set(False)
        self.update_visualization()
    
    def get_selected_groups(self):
        """Отримати список вибраних груп"""
        return [group for group, var in self.group_vars.items() if var.get()]
    
    def update_visualization(self):
        """Оновлення візуалізації"""
        if not self.data:
            return
        
        selected_groups = self.get_selected_groups()
        if not selected_groups:
            self.clear_canvas()
            return
        
        try:
            self.create_visualization(selected_groups)
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка при створенні графіка: {e}")
    
    def clear_canvas(self):
        """Очищення canvas"""
        for widget in self.canvas_frame.winfo_children():
            widget.destroy()
        
        self.placeholder_label = ttk.Label(self.canvas_frame, 
                                         text="Виберіть групи для відображення",
                                         font=('Arial', 12))
        self.placeholder_label.grid(row=0, column=0)
    
    def create_visualization(self, selected_groups):
        """Створення графіка відключень"""
        # Очищення canvas
        for widget in self.canvas_frame.winfo_children():
            widget.destroy()
        
        def time_to_float(t_str):
            h, m = map(int, t_str.split(':'))
            return h + m / 60.0
        
        # Фільтрація та сортування груп
        available_groups = [g for g in sorted(selected_groups, reverse=True) 
                           if g in self.data['schedules']]
        
        if not available_groups:
            return
        
        # Створення matplotlib фігури
        fig, ax = plt.subplots(figsize=(12, len(available_groups) * 0.6 + 2), 
                              facecolor='#f8f9fa', dpi=100)
        ax.set_facecolor('#ffffff')
        
        # Малювання графіка
        for i, group in enumerate(available_groups):
            # Зелений фон (світло є)
            ax.add_patch(patches.Rectangle((0, i - 0.4), 24, 0.8, 
                                         color='#2ecc71', alpha=0.3))
            
            # Червоні зони (відключення)
            for start_str, end_str in self.data['schedules'][group]:
                start = time_to_float(start_str)
                end = time_to_float(end_str)
                ax.add_patch(patches.Rectangle((start, i - 0.4), end - start, 0.8, 
                                             color='#e74c3c', alpha=0.8))
        
        # Налаштування сітки та осей
        ax.set_yticks(range(len(available_groups)))
        ax.set_yticklabels([f"Група {g}" for g in available_groups], 
                          fontweight='bold', fontsize=10)
        ax.set_xticks(range(0, 25, 2))
        ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)])
        
        ax.grid(which='major', axis='x', color='gray', linestyle='-', 
               linewidth=0.5, alpha=0.3)
        ax.grid(which='major', axis='y', color='gray', linestyle='-', 
               linewidth=0.5, alpha=0.3)
        
        # Поточний час
        now = datetime.now()
        current_time = now.hour + now.minute / 60.0
        ax.axvline(x=current_time, color='blue', linestyle='--', linewidth=2, 
                  label=f'Зараз: {now.strftime("%H:%M")}')
        
        # Оформлення
        ax.set_xlim(0, 24)
        ax.set_ylim(-0.5, len(available_groups) - 0.5)
        ax.set_xlabel("Час", fontsize=11)
        ax.set_title(f"Графік відключень станом на {self.data['update_time']} "
                    f"({datetime.now().strftime('%d.%m.%Y')})", 
                    fontsize=12, pad=15)
        
        ax.legend(loc='upper right')
        
        # Легенда
        legend_elements = [
            patches.Patch(color='#2ecc71', alpha=0.3, label='Світло є'),
            patches.Patch(color='#e74c3c', alpha=0.8, label='Відключення')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
        
        plt.tight_layout()
        
        # Вставка в tkinter
        canvas = FigureCanvasTkAgg(fig, self.canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Зберігаємо посилання на фігуру для збереження
        self.current_fig = fig
    
    def find_common_hours(self):
        """Знаходження спільних годин зі світлом"""
        if not self.data:
            messagebox.showwarning("Увага", "Спочатку завантажте дані!")
            return
        
        selected_groups = self.get_selected_groups()
        if len(selected_groups) < 2:
            messagebox.showwarning("Увага", "Виберіть принаймні 2 групи!")
            return
        
        def time_to_min(t_str):
            h, m = map(int, t_str.split(':'))
            return h * 60 + m

        def min_to_time(m):
            return f"{int(m // 60):02d}:{int(m % 60):02d}"
        
        # Обчислення спільних годин
        all_groups_on_minutes = []
        
        for group in selected_groups:
            if group not in self.data['schedules']:
                continue
            
            off_slots = sorted([(time_to_min(s), time_to_min(e)) 
                               for s, e in self.data['schedules'][group]])
            
            on_slots = []
            last_end = 0
            for start, end in off_slots:
                if start > last_end:
                    on_slots.append((last_end, start))
                last_end = max(last_end, end)
            if last_end < 1440:
                on_slots.append((last_end, 1440))
            
            all_groups_on_minutes.append(on_slots)
        
        if not all_groups_on_minutes:
            self.common_text.delete(1.0, tk.END)
            self.common_text.insert(tk.END, "Дані для обраних груп відсутні.")
            return
        
        # Знаходження перетину
        common_on = all_groups_on_minutes[0]
        for next_group_on in all_groups_on_minutes[1:]:
            new_intersection = []
            for s1, e1 in common_on:
                for s2, e2 in next_group_on:
                    start = max(s1, s2)
                    end = min(e1, e2)
                    if start < end:
                        new_intersection.append((start, end))
            common_on = new_intersection
        
        # Виведення результату
        self.common_text.delete(1.0, tk.END)
        result_text = f"Спільні години для груп {', '.join(selected_groups)}:\n\n"
        
        if not common_on:
            result_text += "❌ Немає спільних годин зі світлом для всіх вибраних груп."
        else:
            total_duration = 0
            for s, e in common_on:
                duration = (e - s) / 60
                total_duration += duration
                result_text += f"✅ {min_to_time(s)} — {min_to_time(e)} ({duration:.1f} год)\n"
            result_text += f"\nЗагальна тривалість: {total_duration:.1f} год"
        
        self.common_text.insert(tk.END, result_text)
    
    def show_statistics(self):
        """Показати статистику відключень"""
        if not self.data:
            messagebox.showwarning("Увага", "Спочатку завантажте дані!")
            return
        
        def time_to_float(t_str):
            h, m = map(int, t_str.split(':'))
            return h + m / 60.0
        
        # Створення вікна статистики
        stats_window = tk.Toplevel(self.root)
        stats_window.title("📊 Статистика відключень")
        stats_window.geometry("800x500")
        
        # Таблиця статистики
        columns = ('Група', 'Кількість відключень', 'Загалом без світла (год)', 
                  'Макс. тривалість (год)', 'Середня тривалість (год)', '% доби без світла')
        
        tree = ttk.Treeview(stats_window, columns=columns, show='headings', height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor='center')
        
        # Заповнення даних
        for group, intervals in sorted(self.data['schedules'].items()):
            total_hours = 0
            durations = []
            
            for start_str, end_str in intervals:
                duration = time_to_float(end_str) - time_to_float(start_str)
                total_hours += duration
                durations.append(duration)
            
            count = len(intervals)
            max_duration = max(durations) if durations else 0
            avg_duration = total_hours / count if count > 0 else 0
            percent = (total_hours / 24) * 100
            
            tree.insert('', tk.END, values=(
                f"Група {group}",
                count,
                f"{total_hours:.1f}",
                f"{max_duration:.1f}",
                f"{avg_duration:.1f}",
                f"{percent:.0f}%"
            ))
        
        # Scrollbar для таблиці
        scrollbar = ttk.Scrollbar(stats_window, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Розміщення
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
    
    def save_chart(self):
        """Збереження графіка"""
        if not hasattr(self, 'current_fig'):
            messagebox.showwarning("Увага", "Немає графіка для збереження!")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("PDF files", "*.pdf"), ("All files", "*.*")],
            title="Зберегти графік"
        )
        
        if filename:
            try:
                self.current_fig.savefig(filename, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Успіх", f"Графік збережено: {filename}")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося зберегти файл: {e}")

def main():
    root = tk.Tk()
    app = PowerOutageApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
