import html

import requests               # Библиотека для HTTP-запросов
import telebot               # Основная библиотека для работы с Telegram API
from telebot import formatting as frmt  # Модуль форматирования сообщений
import models                 # Пакет моделей, содержащий бизнес-логику приложения
from models.minecraft_server_info import get_mc_server_info, GetServerInfoError  # Функции для получения информации о серверах Minecraft
from random import randint     # Используется для генерации случайных чисел
import time                   # Работа с датой и временем
from models.orm import MySession, User  # ORM-модели для работы с базой данных
import logging                # Стандартная библиотека Python для ведения логов
import os
from dotenv import load_dotenv
import threading
from flask import Flask

# Загружаем переменные из .env
load_dotenv()

# Получаем токен
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("Токен бота не найден в .env!")

# настройка логгера
logger = logging.getLogger('my_app')
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# логгер для фаилов
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
# логгер для консоли
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def print_fav_servers(fav_servers: dict):
    out = ""
    if fav_servers:
        for k, v in fav_servers.items():
            out += f"{frmt.hcode(k)} - {frmt.hcode(v)}\n"
    else:
        out = "отсутствуют"
    return out


def get_printable_user(from_user, from_chat= None, formatting=False) -> str:
    if formatting:
        return (
                f"{html.escape(from_user.first_name)}"
                f"{'' if not from_user.last_name else f' {html.escape(from_user.last_name)}'}"
                f" ({f'@{from_user.username}, ' if from_user.username else ''}"
                f"<a href=\"{'tg://user?id=' + str(from_user.id)})\">" + str(from_user.id) + "</a>"
                                                                                             f"{(', chat: ' + '<code>' + str(from_chat.id) + '</code>') if not from_chat is None else ''})"

        )
    else:
        return (
            f"{from_user.first_name}"
            f"{'' if not from_user.last_name else f' {from_user.last_name}'}"
            f" ({f'@{from_user.username}, ' if from_user.username else ''}"
            f"{'tg://user?id=' + str(from_user.id)}"
            f"{(', chat_id: ' + str(from_chat.id)) if not from_chat is None else ''})")

def get_printable_time():
    return time.strftime("%H:%M.%S %d.%m.%Y", time.localtime())  # упорядочиваем время в нужный формат


# запись текста в файл
def write_msg(msg):
    with open("msgs.txt", "a+", encoding="utf-8") as f:
        text = f"[{get_printable_time()}] {msg}\n"
        f.write(text)
        print(text, end="")


def on_msg(msg):
    write_msg(f"{get_printable_user(msg.from_user)}: {msg.text}")


write_msg("start")


class Bot():
    MAX_FAV_SERVERS = 10
    HELP_TEXT = (frmt.hbold("Get Minecraft Servers Information Bot") + "\n\n" +
                """Я бот, который позволяет получать информацию о серверах Minecraft
Просто напиши мне адрес (IP) сервера и я напишу тебе информацию о нём (онлайн, описание, и проч.)

Доступные команды:
• <code>/stats ADDRESS</code> - получение информация о сервере с адресом ADDRESS
• /help - получение справка
• /fav - изменение и просмотр избранных серверов:
    • /fav - просмотр ваших избранных серверов
    • <code>/fav add 2b2t.org</code> - добавить сервер с адресом 2b2t.org в избранные сервера (имя в избранных совпадает с адресом)
    • <code>/fav add 2b2t.org bestServer</code> - добавить сервер с адресом 2b2t.org в избранные под именем bestServer
    • <code>/fav del 2b2t.org</code> - удаляет сервер с именем 2b2t.org из избранного
    """)
    INVILID_CMD_USE = "Неверное использование команды\nДля получения справки: /help"

    def __init__(self):
        self.bot = telebot.TeleBot(TOKEN)
        self.session = MySession()

    def generate_server_description(self, address: str) -> str:
        """Описание сервера"""
        try:
            data = get_mc_server_info(address)  # попытка пингануть данные сервера по данному (address)
            if data["ping"]:
                if len(data['players_list']) > 0:
                    pl_list = f"\n• Список игроков: {(', '.join(frmt.hcode(p['name']) for p in data['players_list']) if data['players_list'] else '-')}"
                else:
                    pl_list = ""

                motd_text = '\n'.join(data['motd'])
                return f"""{'🟢' if data['is_online'] else "⚫"} {frmt.hbold('Сервер')} {frmt.hcode(address)} 

• Запрос: {frmt.hcode(address)}
• Цифровой IP: {frmt.hcode(data['address'])}
• Описание: 
{frmt.hpre(motd_text, language="motd")}
• Версия: {frmt.hcode(data['version'])}
• Онлайн игроков: {data['players']} / {data['max_players']}{pl_list} 
"""
            else:
                raise GetServerInfoError(f'Произошла ошибка. Нет ответа от сервера {address}')  # если пинг провалился

        except requests.exceptions.Timeout:
            raise GetServerInfoError(
                f'Превышено время ожидания ответа от сервера {address}')  # если произошёл таймаут

        except KeyError as e:
            telebot.logger.error("Missing key in data: %s", str(e))
            return frmt.hbold("⚠️ Ошибка формирования данных") # неправильно указанны данные

        except ConnectionError:
            raise GetServerInfoError("Ошибка подключения!") # нету интернета

    def get_markup(self, user_id):
        fav_servers = self.session.get_fav_servers(user_id)
        names = fav_servers.keys()
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for i in names:
            keyboard.add(
                telebot.types.KeyboardButton(text=f"{i}"))  # создаём кнопку на каждый выданный пользователь сервер

        return keyboard

    def get_inline_preview(self, inline_query, address, name=""):
        try:
            r1 = telebot.types.InlineQueryResultArticle(
                id=f"{int(time.time())}_{randint(0, 10000)}",
                title=f"🟢 {name} • {address}",
                description="Нажмите здесь получения информации о сервере",
                input_message_content=telebot.types.InputTextMessageContent(
                    self.generate_server_description(address),  # генерируем описание данного сервера
                    parse_mode="HTML"
                )
            )
        except models.minecraft_server_info.GetServerInfoError as ex:
            r1 = telebot.types.InlineQueryResultArticle(
                id=f"{address}_{name}_{int(time.time())}_{randint(0, 10000)}",
                title=f"🔴 {address} • {name}",
                description=f"{ex}",
                input_message_content=telebot.types.InputTextMessageContent(  # отправляем сообщение об ошибке
                    "нет данных",
                    parse_mode="HTML"  # Явно указываем HTML
                )
            )
        return r1

    def add_fav_server(self, msg, address, name):
        # получаем существующие избранные сервера пользователя
        fav_servers = self.session.get_fav_servers(msg.from_user.id)
        if len(fav_servers) > self.MAX_FAV_SERVERS:
            self.bot.send_message(msg.chat.id,
                                  f"Не удалось добавить сервер в избранные. \nПревышено максимальное количество избранных серверов: {self.MAX_FAV_SERVERS}",
                                  reply_to_message_id=msg.id,
                                  reply_markup=self.get_markup(msg.from_user.id))
            return
        fav_servers[f"{name}"] = address  # добавляем новый сервер
        self.session.set_fav_servers(msg.from_user.id, fav_servers)
        self.bot.send_message(msg.chat.id, f"Добавили сервер {frmt.hcode(html.escape(name))} в избранные", reply_to_message_id=msg.id,
                              reply_markup=self.get_markup(msg.from_user.id), parse_mode="html")  # отправляем сообщение если всё хорошо

    def mainloop(self):
        try:
            bot = self.bot

            # обработчик всех сообщений не начинающихся с '/'
            @bot.message_handler(regexp=r"^((?!\/).|\n)+$")
            def handle_other_messages(message: telebot.types.Message) -> None:
                # регистрируем нового пользователя в базе данных
                new_user = User(id=message.from_user.id)
                self.session.add_user(new_user)
                on_msg(message)
                # получаем список избранных серверов пользователя
                fav_servers = self.session.get_fav_servers(message.from_user.id)
                if message.text in fav_servers.keys():
                    try:
                        bot.reply_to(message, self.generate_server_description(fav_servers[message.text]),
                                     parse_mode="HTML", reply_markup=self.get_markup(message.from_user.id))
                    except GetServerInfoError:
                        bot.reply_to(message, "Ошибка!", parse_mode="HTML",
                                     reply_markup=self.get_markup(message.from_user.id))
                else:
                    handle_stats(message)


            @bot.message_handler(commands=['start'])
            def handle_start(message: telebot.types.Message) -> None:
                """Команда /start"""
                # регистрируем нового пользователя
                new_user = User(id=message.from_user.id)
                self.session.add_user(new_user)
                # логаем входящее сообщение
                on_msg(message)
                # приветственное сообщение пользователю
                bot.send_message(message.chat.id, f"Добро пожаловать, {message.from_user.first_name}!\n"
                                                  f"\n"
                                                  f"Я бот, который позволяет получать различную информацию о Minecraft серверах\n"
                                                  f"Для получения справки: /help",
                                 reply_markup=self.get_markup(message.from_user.id))

            @bot.message_handler(commands=['fav'])
            def handle_fav(message: telebot.types.Message) -> None:
                """Команда /fav"""
                # регистрируем нового пользователя
                new_user = User(id=message.from_user.id)
                self.session.add_user(new_user)
                # логаем входящее сообщение
                on_msg(message)
                ls = message.text.split()
                # если команда без аргументов (/fav), показываем список избранных серверов
                if len(ls) == 1:
                    fav_servers = self.session.get_fav_servers(message.from_user.id)
                    bot.send_message(message.chat.id, f"Ваши избранные сервера:\n{print_fav_servers(fav_servers)}",
                                     parse_mode="HTML", reply_markup=self.get_markup(message.from_user.id))
                # если указано два параметра (/fav add server-address), добавляем сервер
                elif len(ls) == 3:
                    if ls[1] in ["add", "a", "+"]:
                        self.add_fav_server(message, ls[2], ls[2])
                    # если указано два параметра (/fav del server-name), удаляем сервер
                    elif ls[1] in ["del", "remove", "-"]:
                        fav_servers = self.session.get_fav_servers(message.from_user.id)
                        try:
                            del fav_servers[ls[2]]
                            self.session.set_fav_servers(message.from_user.id, fav_servers)
                            bot.send_message(message.chat.id, f"Удалил сервер", reply_to_message_id=message.id)
                        except:
                            bot.send_message(message.chat.id, f"Сервер не найден", reply_to_message_id=message.id)
                    else:
                        bot.send_message(message.chat.id, self.INVILID_CMD_USE,
                                         reply_to_message_id=message.id)

                elif len(ls) == 4:
                    if ls[1] in ["add", "a", "+"]:
                        self.add_fav_server(message, ls[2], ls[3])
                    else:
                        bot.send_message(message.chat.id, self.INVILID_CMD_USE,
                                         reply_to_message_id=message.id)

                else:
                    bot.send_message(message.chat.id, self.INVILID_CMD_USE, reply_to_message_id=message.id)

            @bot.message_handler(commands=['help'])
            def handle_help(message: telebot.types.Message) -> None:
                """Команда /help"""
                # регистрируем нового пользователя
                new_user = User(id=message.from_user.id)
                self.session.add_user(new_user)
                # логаем входящее сообщение
                on_msg(message)
                # отсылаем справочный текст
                bot.send_message(message.chat.id, self.HELP_TEXT, parse_mode='html',
                                 reply_markup=self.get_markup(message.from_user.id))

            def send_data(message):
                """Запрос информации о сервере"""
                try:
                    args = message.text.split()
                    if message.text[0] == "/":
                        if len(args) < 2:
                            raise ValueError

                        ip = args[1]
                    else:
                        ip = args[0]

                    response = self.generate_server_description(ip)

                except ValueError:
                    # если не указан IP-адрес
                    error_msg = f"{frmt.hbold('Ошибка:')} Не указан IP-адрес сервера!\n\nПример использования: {frmt.hcode('/stats 2b2t.org')}"
                    bot.reply_to(message, error_msg, parse_mode='html')
                except GetServerInfoError as ex:
                    error_msg = f"{frmt.hbold('Ошибка:')} {ex}"
                    bot.reply_to(message, error_msg, parse_mode='html')
                except ConnectionError as e:
                    # обрабатываем проблемы с соединением
                    bot.reply_to(message, frmt.hbold(f"⚠️ Ошибка подключения: {str(e)}"), parse_mode='html')

                else:
                    # отправляем информацию о сервере
                    bot.send_message(message.chat.id, response, parse_mode='html', reply_to_message_id=message.id)
                    # фиксируем запрос в статистике пользователя
                    self.session.add_request(message.from_user.id)

            # обработчики команд для получения статистики
            @bot.message_handler(commands=['stats', 'info'])
            def handle_stats(message: telebot.types.Message) -> None:
                new_user = User(id=message.from_user.id)
                self.session.add_user(new_user)
                send_data(message)

            @bot.inline_handler(lambda query: True)
            def handle_inline_query(inline_query):
                try:
                    # Логируем запрос
                    logger.info(f"Inline query from {inline_query.from_user.id}: {inline_query.query}")

                    # Создаём пользователя если его нет
                    new_user = User(id=inline_query.from_user.id)
                    self.session.add_user(new_user)

                    results = []
                    query = inline_query.query.strip()

                    if not query:
                        # Если запрос пустой - показываем подсказку
                        item = telebot.types.InlineQueryResultArticle(
                            id='1',
                            title="Введите адрес сервера Minecraft",
                            description="Например: mc.example.com",
                            input_message_content=telebot.types.InputTextMessageContent(
                                message_text="Введите адрес сервера Minecraft для получения информации",
                                parse_mode="HTML"
                            )
                        )
                        results.append(item)
                    else:
                        # Обрабатываем запрос
                        try:
                            server_info = self.generate_server_description(query)
                            item = telebot.types.InlineQueryResultArticle(
                                id=query,
                                title=f"Информация о сервере {query}",
                                description="Нажмите чтобы отправить информацию",
                                input_message_content=telebot.types.InputTextMessageContent(
                                    message_text=server_info,
                                    parse_mode="HTML"
                                )
                            )
                            results.append(item)
                        except GetServerInfoError as e:
                            item = telebot.types.InlineQueryResultArticle(
                                id='error',
                                title="Ошибка",
                                description=str(e),
                                input_message_content=telebot.types.InputTextMessageContent(
                                    message_text=f"Ошибка: {str(e)}",
                                    parse_mode="HTML"
                                )
                            )
                            results.append(item)

                    # Отправляем ответ
                    bot.answer_inline_query(inline_query.id, results, cache_time=1)

                except Exception as e:
                    logger.error(f"Error in inline handler: {str(e)}")

            try:
                bot.remove_webhook()
                bot.polling(non_stop=True, interval=1, timeout=30)
            except telebot.apihelper.ApiTelegramException:
                print("telebot.apihelper.ApiTelegramException 95747")
        except requests.exceptions.ConnectionError as ex:
            logging.error(f"ConnectionError: {ex}")

        except telebot.apihelper.ApiTelegramException:
            print("telebot.apihelper.ApiTelegramException 95747")


if __name__ == '__main__':
    b = Bot()
    b.mainloop()