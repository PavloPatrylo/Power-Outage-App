import streamlit as st
import json
import os
import sys
import re
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime
from io import StringIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

# Налаштування сторінки
st.set_page_config(
    page_title="Графік відключень світла Львів",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Кастомні стилі
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #2ecc71;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        border: none;
    }
    .stButton>button:hover {
        background-color: #27ae60;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #2ecc71;
    }
    h1 {
        color: #2c3e50;
    }
    .stAlert {
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Константи
# ──────────────────────────────────────────────
AVAILABLE_GROUPS = [
    '1.1', '1.2', '2.1', '2.2', '3.1', '3.2',
    '4.1', '4.2', '5.1', '5.2', '6.1', '6.2'
]


# ──────────────────────────────────────────────
# Допоміжні функції
# ──────────────────────────────────────────────

def make_all_power_on_data():
    """Фолбек: вважаємо що світло є у всіх групах."""
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    return {
        "update_time": now.strftime("%H:%M"),
        "schedules": {group: [] for group in AVAILABLE_GROUPS}
    }


def get_dynamic_html(url):
    """Завантаження динамічного HTML з сайту.
    
    Чекає лише на базовий <body>, а не на конкретний клас,
    щоб не плутати помилку мережі зі зміною верстки.
    Повертає рядок HTML або None при мережевій помилці.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36"
    )
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(url)
        # Чекаємо лише на body — щоб відрізнити мережеву помилку від зміни верстки
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return driver.page_source
    except Exception:
        return None
    finally:
        driver.quit()


def parse_html_to_data(html):
    """Парсинг HTML та витягування даних про графіки.

    Якщо структура сайту змінилась і потрібні елементи/регулярні вирази
    не знайдено — повертає фолбек (світло є у всіх групах).
    """
    soup = BeautifulSoup(html, 'html.parser')
    text_container = soup.find('div', class_='power-off__text')

    # ── Структура сайту змінилась: потрібного контейнера немає ──
    if not text_container:
        return make_all_power_on_data()

    update_time_pattern = r"станом на (\d{2}:\d{2})"
    group_pattern = r"Група\s+(\d\.\d)"
    time_pattern = r"(\d{2}:\d{2})\s+(?:до|по)\s+(\d{2}:\d{2})"

    final_result = {
        "update_time": None,
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
            final_result["schedules"][group_name] = times if times else []

    # ── Регулярні вирази не знайшли жодної групи ──
    if not final_result["schedules"]:
        return make_all_power_on_data()

    # ── Час оновлення не знайшли, але групи є ──
    if not final_result["update_time"]:
        final_result["update_time"] = (
            datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")
        )

    return final_result


def time_to_float(t_str):
    """Конвертація часу у float для графіка."""
    h, m = map(int, t_str.split(':'))
    return h + m / 60.0


def time_to_min(t_str):
    """Конвертація часу у хвилини."""
    h, m = map(int, t_str.split(':'))
    return h * 60 + m


def min_to_time(m):
    """Конвертація хвилин у рядок часу."""
    return f"{int(m // 60):02d}:{int(m % 60):02d}"


# ──────────────────────────────────────────────
# Візуалізація та таблиці
# ──────────────────────────────────────────────

def visualize_schedule(data, target_groups):
    """Візуалізація графіка відключень."""
    all_data = data.get("schedules", {})
    update_time = data.get("update_time", "Невідомо")

    display_groups = [g for g in sorted(target_groups, reverse=True) if g in all_data]

    if not display_groups:
        st.warning("Обрані групи не знайдені у даних.")
        return None

    fig, ax = plt.subplots(
        figsize=(15, len(display_groups) * 0.8 + 2),
        facecolor='#f8f9fa'
    )
    ax.set_facecolor('#ffffff')

    for i, group in enumerate(display_groups):
        # Зелений фон (світло є)
        ax.add_patch(patches.Rectangle((0, i - 0.5), 24, 1, color='#2ecc71', alpha=0.3))

        # Червоні зони (відключення)
        if all_data[group]:
            for start_str, end_str in all_data[group]:
                start = time_to_float(start_str)
                end = time_to_float(end_str)
                ax.add_patch(
                    patches.Rectangle(
                        (start, i - 0.5), end - start, 1,
                        color='#e74c3c', alpha=0.8
                    )
                )

    ax.set_yticks(range(len(display_groups)))
    ax.set_yticklabels(display_groups, fontweight='bold', fontsize=11)
    ax.set_yticks([i - 0.5 for i in range(len(display_groups) + 1)], minor=True)
    ax.set_xticks(range(25))

    ax.grid(which='major', axis='x', color='black', linestyle='-', linewidth=0.5, alpha=0.3)
    ax.grid(which='minor', axis='y', color='black', linestyle='-', linewidth=0.8, alpha=0.5)
    ax.tick_params(axis='y', which='major', left=False)

    ax.set_xlim(0, 24)
    ax.set_ylim(-0.5, len(display_groups) - 0.5)

    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    current_time = now.hour + now.minute / 60.0
    ax.axvline(
        x=current_time, color='blue', linestyle='--', linewidth=2,
        label=f'Зараз: {now.strftime("%H:%M")}'
    )

    plt.title(
        f"Графік відключень станом на {update_time} "
        f"(дата: {datetime.now().strftime('%d.%m.%Y')})",
        fontsize=14, pad=20
    )
    ax.set_xlabel("Години", fontsize=12)
    ax.legend(loc='upper right')

    plt.tight_layout()
    return fig


def display_schedule_table(data, target_groups):
    """Вивід розкладу відключень у вигляді таблиці."""
    all_data = data.get("schedules", {})

    if not target_groups:
        return

    st.subheader("📋 Детальний розклад по годинах")

    table_data = []
    for group in sorted(target_groups):
        if group in all_data:
            if all_data[group]:
                intervals = [f"{s} — {e}" for s, e in all_data[group]]
                table_data.append({
                    "Група": group,
                    "Періоди відключень": " | ".join(intervals)
                })
            else:
                table_data.append({
                    "Група": group,
                    "Періоди відключень": "⚡ Електроенергія весь день"
                })

    if table_data:
        st.table(pd.DataFrame(table_data))
    else:
        st.info("Дані для обраних груп відсутні")


def find_common_power_slots(data, target_groups):
    """Пошук спільних годин зі світлом."""
    all_data = data.get("schedules", {})
    all_groups_on_minutes = []

    for group in target_groups:
        if group not in all_data:
            continue

        if not all_data[group]:
            all_groups_on_minutes.append([(0, 1440)])
            continue

        off_slots = sorted(
            [(time_to_min(s), time_to_min(e)) for s, e in all_data[group]]
        )

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
        return []

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

    return [(min_to_time(s), min_to_time(e), (e - s) / 60) for s, e in common_on]


def get_outage_statistics(data):
    """Статистика відключень."""
    all_data = data.get("schedules", {})
    stats = []

    for group, intervals in all_data.items():
        if not intervals:
            stats.append({
                "Група": group,
                "К-сть відключень": 0,
                "Загалом без світла (год)": 0.0,
                "Макс. тривалість (год)": 0.0,
                "Середня тривалість (год)": 0.0,
                "% доби без світла": "0%"
            })
            continue

        total_hours = 0
        durations = []

        for start_str, end_str in intervals:
            duration = time_to_float(end_str) - time_to_float(start_str)
            total_hours += duration
            durations.append(duration)

        stats.append({
            "Група": group,
            "К-сть відключень": len(intervals),
            "Загалом без світла (год)": round(total_hours, 1),
            "Макс. тривалість (год)": round(max(durations), 1),
            "Середня тривалість (год)": round(total_hours / len(intervals), 1),
            "% доби без світла": f"{round((total_hours / 24) * 100)}%"
        })

    return pd.DataFrame(stats).sort_values(by="Група")


# ──────────────────────────────────────────────
# Головна функція
# ──────────────────────────────────────────────

def main():
    st.title("💡 Графік відключень світла у Львові")
    st.markdown("---")

    with st.sidebar:
        st.header("⚙️ Налаштування")

        if st.button("🔄 Оновити дані з сайту", type="primary"):
            progress_placeholder = st.empty()
            status_placeholder = st.empty()
            emoji_placeholder = st.empty()

            old_stderr = sys.stderr
            sys.stderr = StringIO()

            try:
                with progress_placeholder.container():
                    progress_bar = st.progress(0)

                    # Крок 1: Підключення
                    emoji_placeholder.markdown("### 🌐")
                    status_placeholder.info("🌐 Підключення до сайту Львівобленерго...")
                    progress_bar.progress(20)

                    url = "https://poweron.loe.lviv.ua/"
                    html = get_dynamic_html(url)

                    # ── Мережева помилка: сайт взагалі недоступний ──
                    if html is None:
                        emoji_placeholder.markdown("### ⚠️")
                        progress_bar.progress(60)
                        status_placeholder.warning(
                            "⚠️ Сайт недоступний. "
                            "Припускаємо, що електроенергія є у всіх групах."
                        )
                        data = make_all_power_on_data()

                    else:
                        # Крок 2: Завантаження HTML
                        emoji_placeholder.markdown("### 📥")
                        status_placeholder.info("📥 Завантаження графіків відключень...")
                        progress_bar.progress(50)

                        # Крок 3: Парсинг
                        emoji_placeholder.markdown("### 🔍")
                        status_placeholder.info("🔍 Аналіз даних по групах...")
                        progress_bar.progress(70)

                        data = parse_html_to_data(html)

                        # Визначаємо, чи спрацював фолбек всередині parse_html_to_data.
                        # Якщо всі групи мають порожній список і структура сайту відома —
                        # це може бути фолбек. Але ми не можемо відрізнити "дійсно немає
                        # відключень" від "фолбек", тому просто показуємо результат.

                    # Крок 4: Збереження (завжди, навіть для фолбеку)
                    emoji_placeholder.markdown("### 💾")
                    status_placeholder.info("💾 Збереження оновлених даних...")
                    progress_bar.progress(90)

                    with open('schedule.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                    # Крок 5: Завершено
                    emoji_placeholder.markdown("### ✅")
                    progress_bar.progress(100)

                    groups_count = len(data["schedules"])
                    groups_with_power = sum(
                        1 for v in data["schedules"].values() if not v
                    )

                    if html is None:
                        # Повідомлення вже показано вище як warning
                        pass
                    else:
                        status_placeholder.success(
                            f"✅ Готово! Завантажено графіки для {groups_count} груп. "
                            + (
                                f"⚡ {groups_with_power} груп зі світлом весь день. "
                                if groups_with_power > 0 else ""
                            )
                            + f"Дані актуальні станом на {data['update_time']}"
                        )

                    import time
                    time.sleep(3)
                    progress_placeholder.empty()
                    status_placeholder.empty()
                    emoji_placeholder.empty()

            finally:
                sys.stderr = old_stderr

        st.markdown("---")

        st.subheader("📊 Групи для відображення")

        if 'selected_groups' not in st.session_state:
            st.session_state.selected_groups = ['1.1', '4.1', '6.1']

        selected_groups = st.multiselect(
            "Оберіть групи:",
            AVAILABLE_GROUPS,
            default=st.session_state.selected_groups,
            key="groups_selector"
        )
        st.session_state.selected_groups = selected_groups

    # ── Основний контент ──
    if os.path.exists('schedule.json'):
        with open('schedule.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        update_time = data.get("update_time", "Невідомо")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("⏰ Час оновлення", update_time)

        with col2:
            st.metric("📅 Дата", datetime.now().strftime('%d.%m.%Y'))

        with col3:
            total_hours = 0
            total_groups = len(data.get("schedules", {}))
            if total_groups > 0:
                for group, intervals in data.get("schedules", {}).items():
                    for start_str, end_str in intervals:
                        total_hours += time_to_float(end_str) - time_to_float(start_str)
                avg_hours = total_hours / total_groups
                st.metric("⚡ Середньо без світла", f"{avg_hours:.1f} год")
            else:
                st.metric("⚡ Середньо без світла", "0 год")

        st.markdown("---")

        tab1, tab2, tab3 = st.tabs(["📊 Графік", "🔍 Спільні години", "📈 Статистика"])

        with tab1:
            st.subheader("Візуалізація графіка відключень")

            if selected_groups:
                fig = visualize_schedule(data, selected_groups)
                if fig:
                    st.pyplot(fig)
                    plt.close()

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("🟢 **Зелений** - світло є")
                    with col2:
                        st.markdown("🔴 **Червоний** - відключення")
                    with col3:
                        st.markdown("🔵 **Синя лінія** - поточний час")
            else:
                st.info("👆 Оберіть групи у бічній панелі для відображення графіка")

        st.markdown("---")
        display_schedule_table(data, selected_groups)

        with tab2:
            st.subheader("Спільні години зі світлом")

            if 'common_groups' not in st.session_state:
                st.session_state.common_groups = ['1.1']

            common_groups = st.multiselect(
                "Оберіть групи для пошуку спільних годин:",
                AVAILABLE_GROUPS,
                default=st.session_state.common_groups,
                key="common_groups_selector"
            )
            st.session_state.common_groups = common_groups

            if common_groups:
                common_slots = find_common_power_slots(data, common_groups)

                st.info(f"🔎 Аналіз для груп: **{', '.join(common_groups)}**")

                if common_slots:
                    st.success(f"✅ Знайдено **{len(common_slots)}** спільних інтервалів")

                    for i, (start, end, duration) in enumerate(common_slots, 1):
                        col1, col2, col3 = st.columns([2, 2, 1])
                        with col1:
                            st.markdown(f"**{i}. {start} — {end}**")
                        with col2:
                            st.markdown(f"Тривалість: **{duration:.1f}** год")
                        with col3:
                            hours = int(duration)
                            minutes = int((duration - hours) * 60)
                            st.markdown(f"({hours}г {minutes}хв)")

                    total_duration = sum(d for _, _, d in common_slots)
                    st.markdown("---")
                    st.metric(
                        "📊 Загальна тривалість спільних годин",
                        f"{total_duration:.1f} год"
                    )
                else:
                    st.warning(
                        "❌ На жаль, немає спільних годин зі світлом для обраних груп"
                    )
            else:
                st.info("👆 Оберіть групи вище для пошуку спільних годин")

        with tab3:
            st.subheader("Статистика відключень")

            stats_df = get_outage_statistics(data)

            if not stats_df.empty:
                col_left, col_right = st.columns([1, 3])
                with col_left:
                    with open('schedule.json', 'r', encoding='utf-8') as f:
                        json_data = f.read()

                    st.download_button(
                        label="📥 Завантажити дані (JSON)",
                        data=json_data,
                        file_name=f"schedule_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json",
                        use_container_width=True
                    )

                st.markdown("---")

                avg_outages = stats_df["К-сть відключень"].mean()
                avg_hours = stats_df["Загалом без світла (год)"].mean()

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Середня к-сть відключень", f"{avg_outages:.1f}")
                with col2:
                    st.metric("Середньо без світла", f"{avg_hours:.1f} год")
                with col3:
                    max_group = stats_df.loc[
                        stats_df["Загалом без світла (год)"].idxmax(), "Група"
                    ]
                    st.metric("Найбільше відключень", max_group)

                st.markdown("---")

                st.dataframe(stats_df, use_container_width=True, hide_index=True)

                st.subheader("Порівняння груп")
                fig2, ax2 = plt.subplots(figsize=(12, 6))

                groups = stats_df["Група"].tolist()
                hours = stats_df["Загалом без світла (год)"].tolist()
                colors = ['#e74c3c' if h > avg_hours else '#2ecc71' for h in hours]

                ax2.bar(groups, hours, color=colors, alpha=0.7)
                ax2.axhline(
                    y=avg_hours, color='blue', linestyle='--',
                    label=f'Середнє: {avg_hours:.1f} год'
                )
                ax2.set_xlabel("Група")
                ax2.set_ylabel("Години без світла")
                ax2.set_title("Тривалість відключень по групах")
                ax2.legend()
                ax2.grid(axis='y', alpha=0.3)

                st.pyplot(fig2)
                plt.close()
            else:
                st.info("Немає даних для відображення статистики")

    else:
        st.warning(
            "⚠️ Файл з даними не знайдено. "
            "Натисніть 'Оновити дані з сайту' у бічній панелі."
        )

    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #7f8c8d;'>
            <p>💡 Дані з офіційного сайту Львівобленерго</p>
            <p>Розроблено для зручного моніторингу графіків відключень</p>
            <a href='https://github.com/PavloPatrylo' target='_blank'>
                <img src='https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white'
                     style='border-radius: 5px;'/>
            </a>
            <p style='font-size: 0.7rem; margin-top: 10px;'>© 2026 Power Outage App</p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()