import streamlit as st
import json
import os
import sys
import re
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime, timedelta
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
    div[data-testid="stRadio"] > label {
        font-weight: bold;
        font-size: 1rem;
    }
    div[data-testid="stRadio"] > div {
        display: flex;
        gap: 1rem;
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

def make_all_power_on_data(date_label=None):
    """Фолбек: вважаємо що світло є у всіх групах."""
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    return {
        "update_time": now.strftime("%H:%M"),
        "date_label": date_label or now.strftime("%d.%m.%Y"),
        "schedules": {group: [] for group in AVAILABLE_GROUPS}
    }


def get_dynamic_html(url):
    """Завантаження динамічного HTML з сайту."""
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
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return driver.page_source
    except Exception:
        return None
    finally:
        driver.quit()


def parse_schedule_block(paragraphs):
    """
    Парсинг списку параграфів одного блоку розкладу.
    Повертає dict: {"update_time": str|None, "date_label": str|None, "schedules": {...}}
    """
    update_time_pattern = r"станом на (\d{2}:\d{2})\s+(\d{2}\.\d{2}\.\d{4})"
    update_time_pattern_no_date = r"станом на (\d{2}:\d{2})"
    date_header_pattern = r"на (\d{2}\.\d{2}\.\d{4})"
    group_pattern = r"Група\s+(\d\.\d)"
    time_pattern = r"(\d{2}:\d{2})\s+(?:до|по)\s+(\d{2}:\d{2})"

    result = {
        "update_time": None,
        "date_label": None,
        "schedules": {}
    }

    for p in paragraphs:
        text = p.get_text()

        # Час оновлення з датою (напр. "станом на 20:56 19.03.2026")
        update_match = re.search(update_time_pattern, text)
        if update_match:
            result["update_time"] = update_match.group(1)
            # Дата оновлення — не обов'язково дата розкладу, тому не перезаписуємо date_label
            continue

        # Час оновлення без дати
        update_match_simple = re.search(update_time_pattern_no_date, text)
        if update_match_simple and not result["update_time"]:
            result["update_time"] = update_match_simple.group(1)
            continue

        # Дата у заголовку (напр. "Графік погодинних відключень на 19.03.2026")
        date_header_match = re.search(date_header_pattern, text)
        if date_header_match and not result["date_label"]:
            result["date_label"] = date_header_match.group(1)

        # Групи
        group_match = re.search(group_pattern, text)
        if group_match:
            group_name = group_match.group(1)
            times = re.findall(time_pattern, text)
            result["schedules"][group_name] = times if times else []

    return result


def parse_html_to_data(html):
    """
    Парсинг HTML.

    Шукає всі блоки .power-off__text на сторінці.
    Кожен блок — окремий день (сьогодні / завтра).

    Повертає список dict-ів: [{"update_time":..., "date_label":..., "schedules":{...}}, ...]
    Якщо структура сайту змінилась — повертає [фолбек].
    """
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    soup = BeautifulSoup(html, 'html.parser')
    text_containers = soup.find_all('div', class_='power-off__text')

    if not text_containers:
        return [make_all_power_on_data(now.strftime("%d.%m.%Y"))]

    results = []
    for container in text_containers:
        paragraphs = container.find_all('p')
        block = parse_schedule_block(paragraphs)

        # Фолбек якщо нічого не знайдено в блоці
        if not block["schedules"]:
            continue

        if not block["update_time"]:
            block["update_time"] = now.strftime("%H:%M")

        results.append(block)

    if not results:
        return [make_all_power_on_data(now.strftime("%d.%m.%Y"))]

    # Якщо date_label не витягнувся з тексту — проставляємо евристично
    # (перший блок = сьогодні, другий = завтра)
    today_str = now.strftime("%d.%m.%Y")
    tomorrow_str = (now + timedelta(days=1)).strftime("%d.%m.%Y")
    fallback_dates = [today_str, tomorrow_str]

    for i, block in enumerate(results):
        if not block["date_label"] and i < len(fallback_dates):
            block["date_label"] = fallback_dates[i]

    return results


def time_to_float(t_str):
    h, m = map(int, t_str.split(':'))
    return h + m / 60.0


def time_to_min(t_str):
    h, m = map(int, t_str.split(':'))
    return h * 60 + m


def min_to_time(m):
    return f"{int(m // 60):02d}:{int(m % 60):02d}"


# ──────────────────────────────────────────────
# Візуалізація та таблиці
# ──────────────────────────────────────────────

def visualize_schedule(data, target_groups):
    """Візуалізація графіка відключень."""
    all_data = data.get("schedules", {})
    update_time = data.get("update_time", "Невідомо")
    date_label = data.get("date_label", datetime.now().strftime('%d.%m.%Y'))

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
        ax.add_patch(patches.Rectangle((0, i - 0.5), 24, 1, color='#2ecc71', alpha=0.3))

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
    # Синя лінія поточного часу — тільки якщо переглядаємо сьогоднішній графік
    today_str = now.strftime("%d.%m.%Y")
    if date_label == today_str:
        current_time = now.hour + now.minute / 60.0
        ax.axvline(
            x=current_time, color='blue', linestyle='--', linewidth=2,
            label=f'Зараз: {now.strftime("%H:%M")}'
        )
        ax.legend(loc='upper right')

    plt.title(
        f"Графік відключень на {date_label} "
        f"(інформація станом на {update_time})",
        fontsize=14, pad=20
    )
    ax.set_xlabel("Години", fontsize=12)

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

                    emoji_placeholder.markdown("### 🌐")
                    status_placeholder.info("🌐 Підключення до сайту Львівобленерго...")
                    progress_bar.progress(20)

                    url = "https://poweron.loe.lviv.ua/"
                    html = get_dynamic_html(url)

                    if html is None:
                        emoji_placeholder.markdown("### ⚠️")
                        progress_bar.progress(60)
                        status_placeholder.warning(
                            "⚠️ Сайт недоступний. "
                            "Припускаємо, що електроенергія є у всіх групах."
                        )
                        now = datetime.now(ZoneInfo("Europe/Kyiv"))
                        days_data = [make_all_power_on_data(now.strftime("%d.%m.%Y"))]

                    else:
                        emoji_placeholder.markdown("### 📥")
                        status_placeholder.info("📥 Завантаження графіків відключень...")
                        progress_bar.progress(50)

                        emoji_placeholder.markdown("### 🔍")
                        status_placeholder.info("🔍 Аналіз даних по групах...")
                        progress_bar.progress(70)

                        # parse_html_to_data тепер повертає список (1 або 2 дні)
                        days_data = parse_html_to_data(html)

                    emoji_placeholder.markdown("### 💾")
                    status_placeholder.info("💾 Збереження оновлених даних...")
                    progress_bar.progress(90)

                    with open('schedule.json', 'w', encoding='utf-8') as f:
                        json.dump(days_data, f, ensure_ascii=False, indent=4)

                    emoji_placeholder.markdown("### ✅")
                    progress_bar.progress(100)

                    days_count = len(days_data)
                    groups_count = len(days_data[0]["schedules"]) if days_data else 0
                    groups_with_power = sum(
                        1 for v in days_data[0]["schedules"].values() if not v
                    ) if days_data else 0

                    day_word = "день" if days_count == 1 else "дні"

                    if html is not None:
                        status_placeholder.success(
                            f"✅ Готово! Завантажено графіки на {days_count} {day_word}, "
                            f"{groups_count} груп. "
                            + (
                                f"⚡ {groups_with_power} груп зі світлом весь день. "
                                if groups_with_power > 0 else ""
                            )
                            + f"Дані актуальні станом на {days_data[0]['update_time']}"
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
            raw = json.load(f)

        # Підтримка старого формату (dict) і нового (list)
        if isinstance(raw, dict):
            days_data = [raw]
        else:
            days_data = raw

        # ── Вибір дня (тільки якщо є більше одного дня) ──
        if len(days_data) > 1:
            now = datetime.now(ZoneInfo("Europe/Kyiv"))
            today_str = now.strftime("%d.%m.%Y")

            day_labels = []
            for i, day in enumerate(days_data):
                label = day.get("date_label", "")
                if label == today_str:
                    day_labels.append(f"📅 Сьогодні ({label})")
                elif i == 0:
                    day_labels.append(f"📅 {label}" if label else f"📅 День {i+1}")
                else:
                    day_labels.append(f"📅 Завтра ({label})" if label else f"📅 День {i+1}")

            # Дефолт — сьогоднішній день
            default_idx = 0
            for i, day in enumerate(days_data):
                if day.get("date_label", "") == today_str:
                    default_idx = i
                    break

            st.subheader("📆 Оберіть день")
            selected_day_label = st.radio(
                "День розкладу:",
                day_labels,
                index=default_idx,
                horizontal=True,
                label_visibility="collapsed"
            )
            selected_day_idx = day_labels.index(selected_day_label)
            data = days_data[selected_day_idx]
            st.markdown("---")
        else:
            data = days_data[0]

        update_time = data.get("update_time", "Невідомо")
        date_label = data.get("date_label", datetime.now().strftime('%d.%m.%Y'))

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("⏰ Час оновлення", update_time)

        with col2:
            st.metric("📅 Дата графіка", date_label)

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
                    json_export = json.dumps(days_data, ensure_ascii=False, indent=4)
                    st.download_button(
                        label="📥 Завантажити дані (JSON)",
                        data=json_export,
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