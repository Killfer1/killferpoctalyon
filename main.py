import os
import random
import sqlite3
from collections import defaultdict
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
import sqlite3
from collections import defaultdict
import sqlite3
from aiogram.fsm.state import State
import sqlite3
import os
from pathlib import Path

DB_PATH = Path('game_data.db')


def init_db():
    """Инициализация базы данных """
    if not DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        #
        cursor.execute('''
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            health INTEGER DEFAULT 100,
            karma INTEGER DEFAULT 0,
            game_state TEXT DEFAULT 'MAIN_MENU'
        )
        ''')

        #  стат
        cursor.execute('''
        CREATE TABLE stats (
            user_id INTEGER,
            stat_name TEXT,
            stat_value INTEGER,
            PRIMARY KEY (user_id, stat_name),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')

        #  инвентарь
        cursor.execute('''
        CREATE TABLE inventory (
            user_id INTEGER,
            item_name TEXT,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''')

        conn.commit()
        conn.close()
        print("База данных успешно создана")
    else:
        print("База данных уже существует")


def get_user_data(user_id: int) -> dict:
    """Получение ВСЕХ данных пользователя с инициализацией при первом обращении"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Создаем пользователя если не существует
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()

    # Получаем основные данные
    cursor.execute('SELECT health, karma, game_state FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()

    # Получаем статистику
    cursor.execute('SELECT stat_name, stat_value FROM stats WHERE user_id = ?', (user_id,))
    stats = {row[0]: row[1] for row in cursor.fetchall()}

    # Получаем инвентарь
    cursor.execute('SELECT item_name, quantity FROM inventory WHERE user_id = ?', (user_id,))
    inventory = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    # Инициализация стандартных значений
    if not user_data:
        health, karma, game_state = 100, 0, 'MAIN_MENU'
    else:
        health, karma, game_state = user_data

    # Стандартные значения статистики
    default_stats = {
        'letters_delivered': 0,
        'letters_read': 0,
        'deaths': 0
    }

    # Стандартный инвентарь
    default_inventory = {
        'Аптечка': 1,
        'Фонарик': 1,
        'Нож': 1
    }

    return {
        'user_id': user_id,
        'health': health,
        'karma': karma,
        'game_state': game_state,
        'stats': {**default_stats, **stats},
        'inventory': {**default_inventory, **inventory}
    }

# Обновление данных пользователя
def update_user_data(user_id: int, user_data: dict):
    """Полное обновление всех данных пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Преобразуем game_state в строку (если это State)
        game_state = str(user_data.get('game_state', 'MAIN_MENU'))

        # Обновляем основные данные
        cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, health, karma, game_state)
        VALUES (?, ?, ?, ?)
        ''', (
            user_id,
            int(user_data.get('health', 100)),  # Явное преобразование в int
            int(user_data.get('karma', 0)),  # Явное преобразование в int
            game_state
        ))

        # Обновляем статистику (убедимся что значения - числа)
        cursor.execute('DELETE FROM stats WHERE user_id = ?', (user_id,))
        for stat, value in user_data.get('stats', {}).items():
            cursor.execute('''
            INSERT INTO stats (user_id, stat_name, stat_value)
            VALUES (?, ?, ?)
            ''', (
                user_id,
                str(stat),  # Преобразуем название в строку
                int(value)  # Преобразуем значение в число
            ))

        # Обновляем инвентарь
        cursor.execute('DELETE FROM inventory WHERE user_id = ?', (user_id,))
        for item, quantity in user_data.get('inventory', {}).items():
            cursor.execute('''
            INSERT INTO inventory (user_id, item_name, quantity)
            VALUES (?, ?, ?)
            ''', (
                user_id,
                str(item),  # Название предмета как строка
                int(quantity)  # Количество как число
            ))

        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")
        conn.rollback()
        raise  # Пробрасываем исключение дальше для отладки
    finally:
        conn.close()

# Инициализируем БД при старте
init_db()



BOT_TOKEN = "8291907114:AAFLfDnLIjjBf8miACJQSRhFE2j4NGz1pO8"

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Состояния игры
class GameStates(StatesGroup):
    MAIN_MENU = State()
    DELIVERY = State()
    READ_LETTER = State()
    AFTER_READ = State()
    PRESIDENT_CHOICE = State()
    ROAD_EVENT = State()
    INVENTORY = State()
    DEATH = State()

# База данных игры
CITIES = {
    "Новый Уренгой": {"danger": 0.7, "description": "Нефтяная столица с военизированной охраной",
                      "faction": "Корпорации"},
    "Арзамас-16": {"danger": 0.9, "description": "Закрытый научный город с секретными лабораториями",
                   "faction": "Ученые"},
    "Полярные Зори": {"danger": 0.6, "description": "Город при атомной станции", "faction": "Технократы"},
    "Мирный": {"danger": 0.8, "description": "Космодром с военным режимом", "faction": "Военные"},
    "Горняк": {"danger": 0.5, "description": "Шахтерский поселок, контролируемый мафией", "faction": "Преступники"},
    "Звездный": {"danger": 0.4, "description": "Бывший военный городок", "faction": "Изгои"},
    "Радужный": {"danger": 0.3, "description": "Химический комбинат с мутировавшим населением", "faction": "Мутанты"},
    "Светлогорск": {"danger": 0.2, "description": "Курортный город, превратившийся в ловушку", "faction": "Культисты"},
    "Краснознаменск": {"danger": 0.85, "description": "Центр кибернетических экспериментов", "faction": "Кибернетики"},
    "Озерск": {"danger": 0.95, "description": "Хранилище ядерных отходов", "faction": "Выжившие"},
    "Верхоянск": {"danger": 0.4, "description": "Самое холодное поселение", "faction": "Сепаратисты"},
    "Дзержинск": {"danger": 0.7, "description": "Город-призрак с токсичной атмосферой", "faction": "Маргиналы"},
    "Железногорск": {"danger": 0.75, "description": "Секретный объект по производству оружия", "faction": "Оружейники"},
    "Североморск": {"danger": 0.65, "description": "База подводных лодок", "faction": "Моряки"},
    "Байконур": {"danger": 0.55, "description": "Космический город в пустыне", "faction": "Космонавты"}
}

PROFESSIONS = {
    "Депутат": {"power": 0.8, "hint": "Конверт с гербовой печатью", "risk": 0.9},
    "Врач": {"power": 0.3, "hint": "Пахнет медикаментами", "risk": 0.2},
    "Ученый": {"power": 0.4, "hint": "Технические чертежи внутри", "risk": 0.4},
    "Военный": {"power": 0.7, "hint": "Штамп 'Секретно'", "risk": 0.7},
    "Президент": {"power": 0.95, "hint": "Конверт с золотой печатью", "risk": 0.05},
    "Банкир": {"power": 0.6, "hint": "Дорогая бумага", "risk": 0.5},
    "Журналист": {"power": 0.2, "hint": "Вырезки газет внутри", "risk": 0.3},
    "Судья": {"power": 0.75, "hint": "Судебная печать", "risk": 0.8},
    "Детектив": {"power": 0.5, "hint": "Фотоснимки внутри", "risk": 0.6},
    "Священник": {"power": 0.35, "hint": "Религиозные символы", "risk": 0.25},
    "Шахтер": {"power": 0.15, "hint": "Пыльный и тяжелый", "risk": 0.1},
    "Учитель": {"power": 0.1, "hint": "Детские рисунки внутри", "risk": 0.05},
    "Повар": {"power": 0.05, "hint": "Пятна еды на конверте", "risk": 0.01},
    "Хакер": {"power": 0.45, "hint": "USB-накопитель внутри", "risk": 0.55},
    "Архитектор": {"power": 0.25, "hint": "Чертежи зданий", "risk": 0.15}
}

LETTERS = [
    {"id": 1, "type": "личное", "content": "Признание в измене. Если прочитают - убьют отправителя."},
    {"id": 2, "type": "тайное", "content": "Координаты склада с едой. Но это ловушка."},
    {"id": 3, "type": "медицинское", "content": "Рецепт лекарства от нового штамма вируса."},
    {"id": 4, "type": "политическое", "content": "Доказательства коррупции высших чинов."},
    {"id": 5, "type": "военное", "content": "План операции по захвату города."},
    {"id": 6, "type": "научное", "content": "Исследования запрещенного биологического оружия."},
    {"id": 7, "type": "финансовое", "content": "Номера счетов в офшорных банках."},
    {"id": 8, "type": "религиозное", "content": "Пророчество о конце света."},
    {"id": 9, "type": "личное", "content": "Письмо от матери к сыну, которого уже нет в живых."},
    {"id": 10, "type": "коммерческое", "content": "Договор о продаже людей в рабство."}
]

ROAD_EVENTS = {
    "Бандиты": {
        "description": "Группа вооруженных людей перекрыла дорогу.",
        "options": [
            {"text": "Попробовать обойти", "risk": 0.6, "success": "Вы незаметно обошли бандитов",
             "fail": "Вас заметили и ограбили"},
            {"text": "Заплатить (потерять 1 предмет)", "risk": 0.1, "success": "Бандиты пропустили вас",
             "fail": "Бандиты взяли деньги и побили вас"}
        ]
    },
    "Радиация": {
        "description": "Ваш путь лежит через зараженную территорию.",
        "options": [
            {"text": "Идти быстро", "risk": 0.5, "success": "Вы быстро преодолели опасную зону",
             "fail": "Вы получили дозу радиации"},
            {"text": "Искать обход", "risk": 0.3, "success": "Вы нашли безопасный путь", "fail": "Вы заблудились"}
        ]
    }
}

# Хранение данных пользователей
user_data = {}


def get_user_data(user_id: int) -> dict:
    """Получение данных пользователя с преобразованием defaultdict"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем данные из БД
    cursor.execute('SELECT health, karma, game_state FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()

    # Получаем статистику
    cursor.execute('SELECT stat_name, stat_value FROM stats WHERE user_id = ?', (user_id,))
    stats = dict(cursor.fetchall())  # Явное преобразование в dict

    # Получаем инвентарь
    cursor.execute('SELECT item_name, quantity FROM inventory WHERE user_id = ?', (user_id,))
    inventory = dict(cursor.fetchall())  # Явное преобразование в dict

    conn.close()

    # Возвращаем обычный dict, а не defaultdict
    return {
        'user_id': user_id,
        'health': user_data[0] if user_data else 100,
        'karma': user_data[1] if user_data else 0,
        'game_state': user_data[2] if user_data else 'MAIN_MENU',
        'stats': stats,
        'inventory': inventory
    }

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = get_user_data(message.from_user.id)
    await state.set_state(GameStates.MAIN_MENU)

    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Взять новое письмо", callback_data="new_letter"))
    kb.add(InlineKeyboardButton(text="Инвентарь", callback_data="inventory"))
    kb.add(InlineKeyboardButton(text="Статистика", callback_data="stats"))
    kb.adjust(1)

    await message.answer(
        f"📮 *Почтальон Апокалипсиса*\n"
        f"Здоровье: {user['health']}% | Карма: {user['karma']}\n"
        f"Доставлено: {user['stats'].get('letters_delivered', 0)} | "
        f"Прочитано: {user['stats'].get('letters_read', 0)}\n\n"
        "Вы - последний почтальон в разрушенном мире. Ваша задача - доставлять письма, "
        "но каждое решение имеет последствия...",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "continue")
async def continue_game(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Продолжить' - возвращает в главное меню без сброса данных"""
    user = get_user_data(callback.from_user.id)
    await state.set_state(GameStates.MAIN_MENU)

    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Взять новое письмо", callback_data="new_letter"))
    kb.add(InlineKeyboardButton(text="Инвентарь", callback_data="inventory"))
    kb.add(InlineKeyboardButton(text="Статистика", callback_data="stats"))
    kb.adjust(1)

    await callback.message.edit_text(
        f"📮 *Почтальон Апокалипсиса*\n"
        f"Здоровье: {user['health']}% | Карма: {user['karma']}\n"
        f"Доставлено: {user['stats']['letters_delivered']} | Прочитано: {user['stats']['letters_read']}\n\n"
        "Выберите действие:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "restart")
async def restart_game(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Начать заново' - полностью сбрасывает прогресс игрока"""
    user_id = callback.from_user.id
    if user_id in user_data:
        del user_data[user_id]  # Полностью удаляем данные игрока

    # Создаем новую запись с начальными значениями
    user = get_user_data(user_id)
    await state.set_state(GameStates.MAIN_MENU)

    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Взять новое письмо", callback_data="new_letter"))
    kb.add(InlineKeyboardButton(text="Инвентарь", callback_data="inventory"))
    kb.add(InlineKeyboardButton(text="Статистика", callback_data="stats"))
    kb.adjust(1)

    await callback.message.edit_text(
        "♻️ *Игра начата заново*\n\n"
        f"📮 *Почтальон Апокалипсиса*\n"
        f"Здоровье: {user['health']}% | Карма: {user['karma']}\n"
        f"Доставлено: {user['stats']['letters_delivered']} | Прочитано: {user['stats']['letters_read']}\n\n"
        "Все данные сброшены. Выберите действие:",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "inventory")
async def show_inventory(callback: types.CallbackQuery, state: FSMContext):
    user = get_user_data(callback.from_user.id)

    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Продолжить", callback_data="continue"))
    kb.add(InlineKeyboardButton(text="Начать заново", callback_data="restart"))

    inventory_text = "\n".join(user['inventory']) if user['inventory'] else "Инвентарь пуст"

    await callback.message.edit_text(
        f"🎒 *Ваш инвентарь*\n\n{inventory_text}",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    user = get_user_data(callback.from_user.id)

    # Получаем топ профессий
    top_professions = user.get('top_professions', [])

    stats_text = (
        f"📊 Статистика:\n"
        f"Здоровье: {user['health']}%\n"
        f"Карма: {user['karma']}\n"
        f"Доставлено: {user['stats'].get('letters_delivered', 0)}\n"
        f"Прочитано: {user['stats'].get('letters_read', 0)}\n\n"
    )

    if top_professions:
        stats_text += "\n".join([f"{prof}: {count}" for prof, count in top_professions])
    else:
        stats_text += "Нет данных"

    await callback.message.answer(stats_text)


@dp.callback_query(F.data == "read", GameStates.DELIVERY)
async def read_letter(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        user = get_user_data(user_id)
        data = await state.get_data()
        profession = data['current_profession']
        letter_type = data['current_letter']['type']

        # Полные тексты писем без форматирования
        LETTER_TEXTS = {
            "Врач": {
                "медицинское": [
                    "Экстренное сообщение из больницы: требуется консультация по сложному случаю. Пациент 42 лет с температурой 39.5°C и сыпью на груди.",
                    "Дорогой коллега, прилагаю результаты анализов пациента К. - лейкоциты 15.3, СОЭ 42. Рекомендую начать терапию антибиотиками."
                ],
                "личное": [
                    "Доктор, мне срочно нужна ваша помощь! Мой сын упал с велосипеда и жалуется на сильную боль в левом предплечье.",
                    "Спасибо за вашу поддержку в трудный момент. Благодаря вашему профессионализму моя мама пошла на поправку."
                ]
            },
            "Военный": {
                "военное": [
                    "Срочное донесение: противник сосредотачивает силы в квадрате 42-15. Подготовьте оборонительные позиции.",
                    "Приказ №247: подразделению 'Ягуар' выдвинуться к точке сбора Альфа к 06:30. Полное боевое снаряжение."
                ],
                "тайное": [
                    "Операция 'Чёрный лебедь': внедренный агент передал схему подземных ходов штаб-квартиры противника.",
                    "Ваше задание: под видом гражданского специалиста проникнуть на завод в Донецке."
                ]
            },
            "Учитель": {
                "личное": [
                    "Уважаемая Марья Ивановна, ваш ученик Петров снова не сделал домашнее задание. Говорит, что болел.",
                    "Спасибо вам за ваше терпение! Благодаря вам мой сын наконец-то полюбил литературу."
                ],
                "научное": [
                    "Результаты школьной олимпиады: 1 место - Сидоров (98 баллов), 2 место - Козлова (95 баллов).",
                    "Новая методичка по преподаванию алгебры в 8 классе. Обратите внимание на главу 4."
                ]
            },
            "default": {
                "медицинское": "Медицинская справка №284 от 15.03.2023. Диагноз: ОРВИ. Рекомендации: постельный режим.",
                "военное": "Секретный пакет документов. Категория доступа: B-4. Только для служебного пользования.",
                "личное": "Дорогой друг, давно не виделись! Как твои дела? Надеюсь, у тебя всё хорошо.",
                "религиозное": "Благословение от отца Николая. Текст молитвы: 'Господи, помилуй и сохрани раба твоего'.",
                "политическое": "Протокол заседания №148. Рассматриваемый вопрос: о повышении налогов на недвижимость.",
                "коммерческое": "Договор поставки №4512 на сумму 125 000 руб. Срок поставки: 30 календарных дней."
            }
        }

        # Выбираем текст письма
        if profession in LETTER_TEXTS and letter_type in LETTER_TEXTS[profession]:
            content = random.choice(LETTER_TEXTS[profession][letter_type])
        else:
            content = LETTER_TEXTS['default'].get(letter_type, "Стандартное письмо без специального содержания.")

        # Эффекты от чтения
        effects = {
            "Врач": {
                "медицинское": {"karma": +10, "msg": "💊 Вы выполнили профессиональный долг"},
                "личное": {"karma": +5, "msg": "❤ Вы проявили сострадание"}
            },
            "Военный": {
                "военное": {"karma": +5, "msg": "🎖️ Вы ознакомились с приказом"},
                "тайное": {"karma": -10, "msg": "🔐 Вы раскрыли секретные данные"}
            },
            "default": {
                "default": {"karma": -5, "msg": "ℹ Вы прочитали чужое письмо"}
            }
        }

        # Получаем эффект
        effect = effects.get(profession, {}).get(letter_type, effects["default"]["default"])

        # Обновляем данные пользователя
        user['karma'] += effect['karma']
        user['stats']['letters_read'] = user['stats'].get('letters_read', 0) + 1
        update_user_data(user_id, user)

        # Формируем сообщение
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="📨 Доставить", callback_data="deliver"),
            InlineKeyboardButton(text="🗑️ Выбросить", callback_data="throw"),
            width=2
        )

        await callback.message.edit_text(
            f"📜 *Письмо от {profession}*\n"
            f"🔖 Тип: {letter_type}\n\n"
            f"✉ *Содержание:*\n{content}\n\n"
            f"⚡ *Последствия:*\n"
            f"{effect['msg']}\n"
            f"▸ Изменение кармы: {effect['karma']:+d}\n\n"
            f"💠 *Текущая карма:* {user['karma']}",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        await callback.answer()

    except Exception as e:
        print(f"Ошибка чтения: {str(e)}")
        await callback.answer("⚠ Произошла ошибка при чтении письма", show_alert=True)


@dp.callback_query(F.data == "throw", GameStates.DELIVERY)
async def throw_letter(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        user = get_user_data(user_id)  # Получаем данные пользователя

        data = await state.get_data()
        letter_type = data.get('current_letter', {}).get('type', 'unknown')

        # Определяем последствия
        karma_penalty = {
            'медицинское': -15,
            'военное': -10,
            'личное': -8,
            'политическое': -20,
            'религиозное': -25
        }.get(letter_type, -5)

        user['karma'] = user.get('karma', 0) + karma_penalty

        # Обновляем статистику
        if 'letters_thrown' not in user['stats']:
            user['stats']['letters_thrown'] = 0
        user['stats']['letters_thrown'] += 1

        # Исправленная строка - передаем user_id напрямую
        update_user_data(user_id, user)

        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="📮 Взять новое письмо", callback_data="new_letter"))

        await callback.message.edit_text(
            f"🗑️ *Письмо уничтожено!*\n\n"
            f"▪ Тип: {letter_type}\n"
            f"▪ Потеряно кармы: {karma_penalty}\n"
            f"▪ Текущая карма: {user['karma']}",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        await callback.answer()
        await state.set_state(GameStates.MAIN_MENU)

    except Exception as e:
        print(f"Ошибка выбрасывания: {str(e)}")
        await callback.answer("⚠ Ошибка при выбрасывании", show_alert=True)


@dp.callback_query(F.data == "new_letter", GameStates.MAIN_MENU)
async def handle_new_letter(callback: types.CallbackQuery, state: FSMContext):
    try:
        # 1. Получаем данные пользователя
        user = get_user_data(callback.from_user.id)

        # 2. Выбираем случайные данные для письма
        city_from, city_to = random.sample(list(CITIES.keys()), 2)
        profession = random.choice(list(PROFESSIONS.keys()))
        letter = random.choice(LETTERS)

        # 3. Сохраняем данные в состоянии
        await state.update_data(
            current_city_from=city_from,
            current_city_to=city_to,
            current_profession=profession,
            current_letter=letter
        )

        # 4. Формируем текст сообщения
        message_text = (
            f"✉️ *Новое письмо для доставки*\n\n"
            f"▪️ От: {profession} из {city_from}\n"
            f"▪️ Куда: {city_to}\n"
            f"▪️ Тип: {letter['type']}\n"
            f"▪️ Опасность: {CITIES[city_from]['danger'] * 100:.0f}%\n\n"
            f"Подсказка: {PROFESSIONS[profession]['hint']}"
        )

        # 5. Создаем клавиатуру
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="📨 Доставить", callback_data="deliver"),
            InlineKeyboardButton(text="👀 Прочитать", callback_data="read"),
            width=2
        )
        kb.row(InlineKeyboardButton(text="🗑️ Выбросить", callback_data="throw"))

        # 6. Отправляем сообщение
        await callback.message.edit_text(
            text=message_text,
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )

        # 7. Меняем состояние
        await state.set_state(GameStates.DELIVERY)

        # 8. Подтверждаем обработку callback
        await callback.answer()

    except Exception as e:
        print(f"Ошибка в handle_new_letter: {e}")
        await callback.answer("⚠️ Ошибка при создании письма", show_alert=True)
        await state.set_state(GameStates.MAIN_MENU)


@dp.callback_query(F.data == "deliver", GameStates.DELIVERY)
async def deliver_letter(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        user = get_user_data(user_id)

        # Функция для рекурсивного преобразования defaultdict в dict
        def convert_defaultdict(obj):
            if isinstance(obj, defaultdict):
                return {k: convert_defaultdict(v) for k, v in obj.items()}
            elif isinstance(obj, dict):
                return {k: convert_defaultdict(v) for k, v in obj.items()}
            return obj

        # Преобразуем все defaultdict
        user = convert_defaultdict(user)

        # Обновляем статистику с проверкой значений
        user.setdefault('stats', {})
        user['stats']['letters_delivered'] = int(user['stats'].get('letters_delivered', 0)) + 1
        user['karma'] = int(user.get('karma', 0)) + 10

        # Подготавливаем данные для сохранения
        data_to_save = {
            'user_id': user_id,
            'health': int(user.get('health', 100)),
            'karma': int(user['karma']),
            'game_state': str(GameStates.MAIN_MENU),
            'stats': {
                'letters_delivered': int(user['stats']['letters_delivered']),
                # Добавьте другие необходимые статистики
            },
            'inventory': {str(k): int(v) for k, v in user.get('inventory', {}).items()}
        }

        # Сохраняем данные
        update_user_data(user_id, data_to_save)

        # Уведомление о доставке
        await callback.answer("✅ Письмо доставлено! +10 кармы", show_alert=True)

        # Возвращаем в главное меню
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="Взять новое письмо", callback_data="new_letter"))
        kb.add(InlineKeyboardButton(text="Инвентарь", callback_data="inventory"))
        kb.add(InlineKeyboardButton(text="Статистика", callback_data="stats"))
        kb.adjust(1)

        await callback.message.edit_text(
            "🏠 Главное меню:",
            reply_markup=kb.as_markup()
        )

        await state.set_state(GameStates.MAIN_MENU)

    except Exception as e:
        print(f"Ошибка в deliver_letter: {str(e)}")
        await callback.answer("⚠️ Ошибка при доставке письма", show_alert=True)
        await state.set_state(GameStates.MAIN_MENU)

async def trigger_road_event(callback: types.CallbackQuery, state: FSMContext):
    user = get_user_data(callback.from_user.id)
    event_name, event_data = random.choice(list(ROAD_EVENTS.items()))

    kb = InlineKeyboardBuilder()
    for option in event_data["options"]:
        kb.add(InlineKeyboardButton(text=option["text"], callback_data=f"event_{option['risk']}"))
    kb.adjust(1)

    await callback.message.edit_text(
        f"⚠️ *ОПАСНОСТЬ НА ПУТИ: {event_name}*\n\n"
        f"{event_data['description']}",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data.startswith("event_"), GameStates.ROAD_EVENT)
async def handle_road_event(callback: types.CallbackQuery, state: FSMContext):
    user = get_user_data(callback.from_user.id)
    risk = float(callback.data.replace("event_", ""))

    if random.random() > risk:
        result = "Вы успешно преодолели препятствие!"
        user['health'] -= 10
    else:
        result = "Вы не справились с препятствием!"
        user['health'] -= 30
        if random.random() > 0.5 and len(user['inventory']) > 0:
            lost_item = random.choice(user['inventory'])
            user['inventory'].remove(lost_item)
            result += f"\nВы потеряли: {lost_item}"

    user['karma'] += 5

    if user['health'] <= 0:
        user['stats']['deaths'] += 1
        await state.set_state(GameStates.DEATH)

        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="Начать заново", callback_data="restart"))

        await callback.message.edit_text(
            f"💀 ВЫ ПОГИБЛИ!\n\n"
            f"Причина: {result}\n\n"
            f"Ваша статистика:\n"
            f"Доставлено писем: {user['stats']['letters_delivered']}\n"
            f"Прочитано писем: {user['stats']['letters_read']}\n"
            f"Посещено городов: {len(user['stats']['cities_visited'])}",
            reply_markup=kb.as_markup()
        )
    else:
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="Продолжить", callback_data="continue"))

        await callback.message.edit_text(
            f"{result}\n\n"
            f"Текущее здоровье: {user['health']}%\n"
            f"Карма: {user['karma']}",
            reply_markup=kb.as_markup()
        )


        await state.set_state(GameStates.MAIN_MENU)


# Запуск бота
async def main():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
