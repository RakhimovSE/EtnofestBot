# -*- coding: utf-8 -*-
import telebot
from telebot import types
import configparser
import json
import shelve
import dateutil.parser

import controller
from GoogleCalendarApi import GoogleCalendarApi
from SQLighter import SQLighter

config = configparser.ConfigParser()
config.read('config.ini')

bot = telebot.TeleBot(config.get('BOT', 'token'))

db_name = config.get('BOT', 'db_name')
shelve_name = config.get('BOT', 'shelve_name')
with shelve.open(shelve_name) as storage:
    if not 'users' in storage:
        storage['users'] = {}
gcal_api = GoogleCalendarApi()


@bot.message_handler(commands=['start'])
def handle_start_msg(message):
    db = SQLighter(db_name)
    db_user = db.get_user(message.chat.id)
    if not db_user:
        db.insert_user(message.chat.id, message.chat.username,
                       message.chat.first_name, message.chat.last_name)
    bot.send_message(message.chat.id, 'Привет!',
                     reply_markup=controller.get_keyboard(message.chat.id))


@bot.message_handler(commands=['admin'])
def handle_admin_msg(message):
    def process_auth_step(inner_msg):
        db = SQLighter(db_name)
        try:
            message_text = inner_msg.text
            msg_login, msg_password = message_text.split('\n')
            msg_login = msg_login.lower()
            msg_password = msg_password.lower()
            msg_password = controller.get_salted_hash(msg_login, msg_password)
            cfg_login = config.get('ADMIN', 'login')
            cfg_password = config.get('ADMIN', 'password')
            if not (msg_login == cfg_login and msg_password == cfg_password):
                raise Exception('Неправильный логин/пароль')
            db.set_admin(inner_msg.chat.id, 1)
            bot.send_message(inner_msg.chat.id, 'Вы вошли в режим администратора',
                             reply_markup=controller.admin_keyboard)
            controller.send_user_questions(inner_msg.chat.id)
        except Exception as e:
            print(str(e))
            bot.send_message(inner_msg.chat.id, 'Не удалось войти в режим администратора. Проверьте логин и пароль',
                             reply_markup=controller.user_keyboard)

    msg = bot.send_message(message.chat.id, 'Вход в режим администратора:\nВведите логин и пароль на новой строке',
                           reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_auth_step)


def send_calendar_main_msg(message, edit_message=False):
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(text='⭐ Моё расписание', callback_data='schedule_my')
    keyboard.add(button)
    button = types.InlineKeyboardButton(text='Все', callback_data='schedule_getdate_-1')
    keyboard.add(button)
    button = types.InlineKeyboardButton(text='По площадкам', callback_data='schedule_area')
    keyboard.add(button)
    html_links = gcal_api.get_html_links()
    text = 'Выберите площадку, расписание которой вы хотите посмотреть'
    text += '\nТакже вы можете подписаться на календари по площадкам\n'
    text += '\n'.join(html_links)
    if edit_message:
        bot.edit_message_text(text, message.chat.id, message.message_id, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)


@bot.message_handler(func=lambda msg: msg.text == '📆 Расписание')
def handle_webcal_msg(message):
    send_calendar_main_msg(message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('question'))
def callback_question_msg(call):
    # question_{{type}}_{{user_id}}_{{message_id}}
    call_data = controller.get_call_data(call.data)
    db = SQLighter(db_name)
    if call_data[1] == 'answer':
        def process_answer_step(inner_msg):
            if inner_msg.text.lower() == 'отмена':
                controller.show_main_menu(inner_msg.chat.id)
                return
            db = SQLighter(db_name)
            try:
                bot.send_message(call_data[2], inner_msg.text, reply_to_message_id=call_data[3])
                bot.edit_message_text('На вопрос дан ответ', call.message.chat.id, call.message.message_id)
                db.answer_user_question(call_data[2], call_data[3], inner_msg.chat.id, inner_msg.message_id)
            except Exception as e:
                print(str(e))
            controller.show_main_menu(inner_msg.chat.id)

        msg = bot.send_message(call.message.chat.id, 'Напишите ответ на вопрос или введите "отмена"',
                               reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_answer_step)
    elif call_data[1] == 'decline':
        bot.edit_message_text('Вопрос отклонён', call.message.chat.id, call.message.message_id)
    db.answer_user_question(call_data[2], call_data[3], call.message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_getdate'))
def callback_schedule_getdate_msg(call):
    calendar_index = controller.get_call_data(call.data)[2]
    db = SQLighter(db_name)
    calendar = db.get_calendar_by_index(calendar_index)
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for day in range(8, 13):
        callback_data = 'schedule_gettime_%d_%d' % (calendar_index, day)
        button = types.InlineKeyboardButton('%d июня' % day, callback_data=callback_data)
        buttons.append(button)
    callback_data = 'schedule_main' if calendar_index == -1 else 'schedule_area_%d' % calendar_index
    button = types.InlineKeyboardButton(text='↩ Назад', callback_data=callback_data)
    buttons.append(button)
    keyboard.add(*buttons)
    if calendar_index == -1:
        text = 'Вывод расписания по <b>всем</b> площадкам'
    else:
        text = 'Вывод расписания по площадке <b>"%s"</b>' % calendar['name']
    text += '\nКакой день вас интересует?'
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode='HTML', reply_markup=keyboard)


def get_time_inline_keyboard(calendar_index, day):
    result = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for hour_max in range(10, 25, 2):
        hour_min = 0 if hour_max == 10 else hour_max - 2
        text = 'С %d по %d' % (hour_min, hour_max)
        callback_data = 'schedule_printevent_%d_%d_%d_%d' % (calendar_index, day, hour_min, hour_max)
        button = types.InlineKeyboardButton(text, callback_data=callback_data)
        buttons.append(button)
    button = types.InlineKeyboardButton('↩ Назад', callback_data='schedule_getdate_%d' % calendar_index)
    buttons.append(button)
    result.add(*buttons)
    return result


def send_gettime_msg(user_id, calendar_index, day):
    keyboard = get_time_inline_keyboard(calendar_index, day)
    bot.send_message(user_id, 'Выберите время', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_gettime'))
def callback_schedule_gettime_msg(call):
    calendar_index, day = controller.get_call_data(call.data)[2:]
    send_gettime_msg(call.message.chat.id, calendar_index, day)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_insert'))
def callback_schedule_insert_msg(call):
    calendar_index, event_index = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    calendar = db.get_calendar_by_index(calendar_index)
    event = db.get_event_by_index(event_index)
    db.insert_user_event(call.message.chat.id, calendar['id_calendar'], event['id_event'])
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(
        '🗑️Удалить из моего расписания',
        callback_data='schedule_delete_%d_%d' % (calendar_index, event_index))
    keyboard.add(button)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_delete'))
def callback_schedule_delete_msg(call):
    calendar_index, event_index = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    calendar = db.get_calendar_by_index(calendar_index)
    event = db.get_event_by_index(event_index)
    db.delete_user_event(call.message.chat.id, calendar['id_calendar'], event['id_event'])
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(
        '⭐ Добавить в моё расписание',
        callback_data='schedule_insert_%d_%d' % (calendar_index, event_index))
    keyboard.add(button)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_area'))
def callback_schedule_area_msg(call):
    keyboard = types.InlineKeyboardMarkup()
    db = SQLighter(db_name)
    calendars = db.get_calendars()
    for i in range(0, len(calendars)):
        text = calendars[i]['name']
        button = types.InlineKeyboardButton(text=text, callback_data=('schedule_getdate_%d' % i))
        keyboard.add(button)
    button = types.InlineKeyboardButton(text='↩ Назад', callback_data='schedule_main')
    keyboard.add(button)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_my'))
def callback_schedule_my_msg(call):
    db = SQLighter(db_name)
    db_events = [{
        'calendar_id': e['calendar_id'],
        'event_id': e['event_id']
    } for e in db.get_user_events(call.message.chat.id)]
    events = gcal_api.get_events(db_events)
    for event in events:
        callback_data = 'schedule_delete_%d_%d' % (event['calendar_index'], event['event_index'])
        keyboard = types.InlineKeyboardMarkup()
        button = types.InlineKeyboardButton('🗑️Удалить из моего расписания', callback_data=callback_data)
        keyboard.add(button)
        text = '<b>%s</b>\n%s' % (event['name'], event['area'])
        if event['location']:
            text += '\n' + event['location']
        text += '\n' + controller.get_formatted_event_date(event['datetime_start'], event['datetime_end'])
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)
    if not events:
        bot.send_message(call.message.chat.id, 'Мероприятие будет добавлено в ваш календарь '
                                               'после того, как вы нажмете кнопку\n"⭐ Добавить в моё расписание"')


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_main'))
def callback_schedule_main_msg(call):
    send_calendar_main_msg(call.message, True)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_printevent'))
def callback_schedule_printevent_msg(call):
    # call.data = 'schedule_{{type}}_{{calendar_index}}_{{day}}_{{time_min}}_{{time_max}}'
    calendar_index, day, hour_min, hour_max = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    calendar_id = None if calendar_index == -1 else db.get_calendar_by_index(calendar_index)['id_calendar']
    time_min = dateutil.parser.parse('2017-06-%dT%d:00:00' % (day, hour_min))
    if hour_max < 24:
        time_max = dateutil.parser.parse('2017-06-%dT%d:00:00' % (day, hour_max))
    else:
        time_max = dateutil.parser.parse('2017-06-%dT00:00:00' % (day + 1))
    events = gcal_api.get_calendar_events(calendar_id=calendar_id, time_min=time_min, time_max=time_max)
    db = SQLighter(db_name)
    db_events = db.get_user_events(call.message.chat.id)
    for event in events:
        keyboard = types.InlineKeyboardMarkup()
        if not any(x for x in db_events
                   if x['user_id'] == call.message.chat.id
                   and x['calendar_id'] == event['calendar_id']
                   and x['event_id'] == event['id']):
            callback_data = 'schedule_insert_%d_%d' % (event['calendar_index'], event['event_index'])
            button = types.InlineKeyboardButton('⭐ Добавить в моё расписание', callback_data=callback_data)
        else:
            callback_data = 'schedule_delete_%d_%d' % (event['calendar_index'], event['event_index'])
            button = types.InlineKeyboardButton('🗑️Удалить из моего расписания', callback_data=callback_data)
        keyboard.add(button)
        text = '<b>%s</b>\n%s' % (event['name'], event['area'])
        if event['location']:
            text += '\n' + event['location']
        text += '\n' + controller.get_formatted_event_date(event['datetime_start'], event['datetime_end'])
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)
    if events:
        send_gettime_msg(call.message.chat.id, calendar_index, day)
    else:
        text = 'С %d:00 по %d:00 не запланировано мероприятий\n' % (hour_min, hour_max)
        keyboard = get_time_inline_keyboard(calendar_index, day)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)


@bot.message_handler(func=lambda msg: msg.text == '❓ Вопросы и ответы')
def handle_faq_msg(message):
    with open('faq.json', 'r', encoding='utf-8') as f:
        faq = json.load(f)

    def process_question_step(inner_msg):
        def process_custom_question_step(inner_msg2):
            if inner_msg2.text.lower() == 'отмена':
                handle_faq_msg(inner_msg2)
                return
            controller.add_user_question(inner_msg2.chat.id, inner_msg2.message_id)
            bot.send_message(inner_msg2.chat.id, 'Ваш вопрос отправлен. Я отвечу на него в ближайшее время!')
            handle_faq_msg(inner_msg2)

        if inner_msg.text == '❓ Задать свой вопрос':
            keyboard = types.ReplyKeyboardRemove()
            msg = bot.send_message(inner_msg.chat.id, 'Напишите вопрос или введите \'Отмена\'', reply_markup=keyboard)
            bot.register_next_step_handler(msg, process_custom_question_step)
            return
        if inner_msg.text == '↩ Вернуться в меню':
            controller.show_main_menu(inner_msg.chat.id)
            return
        with open('faq.json', 'r', encoding='utf-8') as f:
            faq = json.load(f)
        question = list(filter(lambda q: q['question'] == inner_msg.text, faq))
        if not question:
            msg = bot.send_message(inner_msg.chat.id, 'Не удалось распознать команду')
            bot.register_next_step_handler(msg, process_question_step)
            return
        question = question[0]
        # TODO Добавить обработку вложений
        inline_keyboard = None
        if question['inline_keyboard_urls']:
            inline_keyboard = types.InlineKeyboardMarkup()
            for url in question['inline_keyboard_urls']:
                button = types.InlineKeyboardButton(text=url['text'], url=url['url'])
                inline_keyboard.add(button)
        msg = bot.send_message(inner_msg.chat.id, question['answer'], reply_markup=inline_keyboard)
        bot.register_next_step_handler(msg, process_question_step)

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup = []
    for question in faq:
        markup.append([question['question']])
    markup.append(['❓ Задать свой вопрос'])
    markup.append(['↩ Вернуться в меню'])
    controller.set_reply_keyboard_markup(keyboard, markup)
    msg = bot.send_message(message.chat.id, 'Выберите вопрос', reply_markup=keyboard)
    bot.register_next_step_handler(msg, process_question_step)


@bot.message_handler(func=lambda msg: msg.text == '👤 Режим пользователя')
def handle_logout_msg(message):
    db = SQLighter(db_name)
    db.set_admin(message.chat.id, 0)
    bot.send_message(message.chat.id, 'Вы вышли из режима администратора',
                     reply_markup=controller.user_keyboard)


@bot.message_handler(func=lambda msg: msg.text == '❓ Ответить на вопросы')
def handle_answer_user_questions_msg(message):
    controller.send_user_questions(message.chat.id, False)


@bot.message_handler(func=lambda msg: msg.text == '📧 Рассылка')
def handle_newsletter_msg(message):
    def process_newsletter_step(inner_msg):
        def process_newsletter_answer_step(inner_msg2):
            if inner_msg2.text == '✔ Отправить':
                controller.send_newsletter(inner_msg2.chat.id)
                bot.send_message(inner_msg2.chat.id, 'Рассылка отправлена!',
                                 reply_markup=controller.admin_keyboard)
                return
            if inner_msg2.text == '➕ Добавить':
                msg = bot.send_message(inner_msg2.chat.id, 'Введите текст рассылки или выберите файл',
                                       reply_markup=types.ReplyKeyboardRemove())
                bot.register_next_step_handler(msg, process_newsletter_step)
                return
            if inner_msg2.text == '❌ Отменить':
                bot.send_message(inner_msg2.chat.id, 'Рассылка отменена',
                                 reply_markup=controller.admin_keyboard)
                return
            msg = bot.send_message(inner_msg2.chat.id, 'Не удалось распознать команду')
            bot.register_next_step_handler(msg, process_newsletter_answer_step)

        with shelve.open(shelve_name) as storage:
            user_dict = storage['users']
            user_dict[str(inner_msg.chat.id)]['newsletter_messages'].append(inner_msg)
            storage['users'] = user_dict

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup = [
            ['✔ Отправить'],
            ['➕ Добавить', '❌ Отменить']
        ]
        controller.set_reply_keyboard_markup(keyboard, markup)
        msg = bot.send_message(inner_msg.chat.id, 'Сообщение включено в рассылку', reply_markup=keyboard)
        bot.register_next_step_handler(msg, process_newsletter_answer_step)

    with shelve.open(shelve_name) as storage:
        user_dict = storage['users']
        user_dict[str(message.chat.id)] = {'newsletter_messages': []}
        storage['users'] = user_dict
    msg = bot.send_message(message.chat.id, 'Введите текст рассылки или выберите файл',
                           reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_newsletter_step)


def main():
    controller.show_main_menu()
    bot.polling(none_stop=True)


if __name__ == '__main__':
    main()
