# -*- coding: utf-8 -*-
import telebot
from telebot import types
import configparser
import json
import shelve
import dateutil.parser
# import httplib2shim

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
# httplib2shim.patch()
gcal_api = GoogleCalendarApi()



@bot.message_handler(commands=['start'])
def handle_start_msg(message):
    db = SQLighter(db_name)
    db_user = db.get_user(message.chat.id)
    if not db_user:
        db.insert_user(message.chat.id, message.chat.username,
                       message.chat.first_name, message.chat.last_name)
    controller.show_main_menu(message.chat.id)


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
    buttons = []
    button = types.InlineKeyboardButton(text='Все', callback_data='schedule_getdate_-1')
    buttons.append(button)
    button = types.InlineKeyboardButton(text='По площадкам', callback_data='schedule_area')
    buttons.append(button)
    keyboard.add(*buttons)
    html_links = gcal_api.get_html_links()
    text = 'Выбери площадку, расписание которой ты хочешь посмотреть'
    text += '\nЕще ты можешь подписаться на календари по площадкам. Они появятся в твоем календаре на телефоне ' \
            '<i>(функция может работать не поддерживаться на некоторых устройствах)</i>.\n'
    text += '\n'.join(html_links)
    if edit_message:
        bot.edit_message_text(text, message.chat.id, message.message_id, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)


@bot.message_handler(func=lambda msg: msg.text == '📆 Расписание')
def handle_webcal_msg(message):
    send_calendar_main_msg(message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('question_answer'))
def callback_question_answer_msg(call):
    def process_answer_step(inner_msg):
        if inner_msg.text.lower() == 'отмена':
            controller.show_main_menu(inner_msg.chat.id)
            return
        db = SQLighter(db_name)
        try:
            with shelve.open(shelve_name) as storage:
                shelve_users = storage['users']
                user_id = shelve_users[inner_msg.chat.id]['answer']['user_id']
                question_id = shelve_users[inner_msg.chat.id]['answer']['question_id']
                del shelve_users[inner_msg.chat.id]['answer']
                storage['users'] = shelve_users
            text = '<i>Помнишь, ты задавал мне вопрос? ' \
                   'Я хорошенько подумал, и вот мой ответ:</i>\n\n%s' % inner_msg.text
            bot.send_message(user_id, text, reply_to_message_id=question_id, parse_mode='HTML')
            bot.edit_message_text('Вы ответили на вопрос', call.message.chat.id, call.message.message_id)
            db.answer_user_question(user_id, question_id, inner_msg.chat.id, inner_msg.message_id)
        except Exception as e:
            print(str(e))
        controller.show_main_menu(inner_msg.chat.id)

    user_id, question_id = controller.get_call_data(call.data)[2:]
    with shelve.open(shelve_name) as storage:
        shelve_users = storage['users']
        if call.message.chat.id not in shelve_users:
            shelve_users[call.message.chat.id] = {}
        shelve_users[call.message.chat.id]['answer'] = {
            'user_id': user_id,
            'question_id': question_id
        }
        storage['users'] = shelve_users
    msg = bot.send_message(call.message.chat.id, 'Напишите ответ на вопрос или введите "Отмена"',
                           reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_answer_step)


@bot.callback_query_handler(func=lambda call: call.data.startswith('question_decline'))
def callback_question_decline_msg(call):
    user_id, question_id = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    bot.edit_message_text('Вы отклонили вопрос', call.message.chat.id, call.message.message_id)
    db.answer_user_question(user_id, question_id, call.message.chat.id)
    text = 'Помнишь, ты задавал этот вопрос? Я подумал... И решил на него не отвечать 😄 ' \
           'Если хочешь, можешь задать другой вопрос или переформулировать этот 😊'
    keyboard = types.InlineKeyboardMarkup()
    callback_data = 'question_custom_%d_%d' % (user_id, question_id)
    button = types.InlineKeyboardButton('Задать вопрос', callback_data=callback_data)
    keyboard.add(button)
    bot.send_message(user_id, text, reply_to_message_id=question_id, reply_markup=keyboard)


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
        text = '<b>Все</b> площадки'
    else:
        text = 'Площадка <b>"%s"</b>' % calendar['name']
    text += '\n\nКакой день тебя интересует?'
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode='HTML', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_gettime'))
def callback_schedule_gettime_msg(call):
    calendar_index, day = controller.get_call_data(call.data)[2:]
    controller.send_gettime_msg(call, calendar_index, day, False)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_insert'))
def callback_schedule_insert_msg(call):
    calendar_index, event_index = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    calendar = db.get_calendar_by_index(calendar_index)
    event = db.get_event_by_index(event_index)
    event_count = db.get_event_liked_count(event['calendar_id'], event['id_event'])
    db.insert_user_event(call.message.chat.id, calendar['id_calendar'], event['id_event'])
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(
        '🗑️Удалить %d' % (event_count + 1),
        callback_data='schedule_delete_%d_%d' % (calendar_index, event_index))
    keyboard.add(button)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_delete'))
def callback_schedule_delete_msg(call):
    calendar_index, event_index = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    calendar = db.get_calendar_by_index(calendar_index)
    event = db.get_event_by_index(event_index)
    event_count = db.get_event_liked_count(event['calendar_id'], event['id_event'])
    db.delete_user_event(call.message.chat.id, calendar['id_calendar'], event['id_event'])
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(
        '⭐ Добавить %d' % (event_count - 1),
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
        event_count = db.get_event_liked_count(event['calendar_id'], event['id'])
        button = types.InlineKeyboardButton('🗑️Удалить %d' % event_count, callback_data=callback_data)
        keyboard.add(button)
        text = '<b>%s</b>\nПлощадка <i>"%s"</i>' % (event['name'], event['area'])
        if event['location']:
            text += '\n' + event['location']
        text += '\n' + controller.get_formatted_event_date(event['datetime_start'], event['datetime_end'])
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)
    if not events:
        bot.send_message(call.message.chat.id, 'Я добавлю мероприятие в твой календарь '
                                               'после того, как ты нажмешь кнопку\n"⭐ Добавить"')


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_main'))
def callback_schedule_main_msg(call):
    send_calendar_main_msg(call.message, True)


@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_printevent'))
def callback_schedule_printevent_msg(call):
    # call.data = 'schedule_{{type}}_{{calendar_index}}_{{day}}_{{time_min}}_{{time_max}}'
    calendar_index, day, hour_min, hour_max = controller.get_call_data(call.data)[2:]
    db = SQLighter(db_name)
    calendar = db.get_calendar_by_index(calendar_index)
    calendar_id = None if calendar_index == -1 else calendar['id_calendar']
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
        event_count = db.get_event_liked_count(event['calendar_id'], event['id'])
        if not any(x for x in db_events
                   if x['user_id'] == call.message.chat.id
                   and x['calendar_id'] == event['calendar_id']
                   and x['event_id'] == event['id']):
            callback_data = 'schedule_insert_%d_%d' % (event['calendar_index'], event['event_index'])
            button = types.InlineKeyboardButton('⭐ Добавить %d' % event_count, callback_data=callback_data)
        else:
            callback_data = 'schedule_delete_%d_%d' % (event['calendar_index'], event['event_index'])
            button = types.InlineKeyboardButton('🗑️Удалить %d' % event_count, callback_data=callback_data)
        keyboard.add(button)
        text = '<b>%s</b>\nПлощадка <i>"%s"</i>' % (event['name'], event['area'])
        if event['location']:
            text += '\n' + event['location']
        text += '\n' + controller.get_formatted_event_date(event['datetime_start'], event['datetime_end'])
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)
    if events:
        controller.send_gettime_msg(call, calendar_index, day)
    else:
        if calendar:
            text = 'В календаре <b>"%s"</b> с <b>%d:00</b> по <b>%d:00</b> не запланировано мероприятий' % \
                   (calendar['name'], hour_min, hour_max)
        else:
            text = 'С <b>%d:00</b> по <b>%d:00</b> не запланировано мероприятий' % (hour_min, hour_max)
        keyboard = controller.get_time_inline_keyboard(calendar_index, day)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode='HTML', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('question_show'))
def callback_question_show_msg(call):
    question_index = controller.get_call_data(call.data)[2]
    with open('faq.json', 'r', encoding='utf-8') as f:
        faq = json.load(f)
    question = faq[question_index]
    text = '<b>ВОПРОС:</b>\n%s\n\n<b>ОТВЕТ:</b>\n%s' % (question['question'], question['answer'])
    keyboard = None
    if question['inline_keyboard_urls']:
        keyboard = types.InlineKeyboardMarkup()
        for url in question['inline_keyboard_urls']:
            button = types.InlineKeyboardButton(text=url['text'], url=url['url'])
            keyboard.add(button)
    with shelve.open(shelve_name) as storage:
        shelve_users = storage['users']
        message_id = shelve_users[call.message.chat.id]['faq_message_id']
        if not message_id:
            msg = bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)
            shelve_users[call.message.chat.id]['faq_message_id'] = msg.message_id
            storage['users'] = shelve_users
        else:
            bot.edit_message_text(text, call.message.chat.id, message_id, parse_mode='HTML', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('question_custom'))
def callback_question_custom_msg(call):
    def process_custom_question_step(inner_msg):
        if inner_msg.text and inner_msg.text.lower() == 'отмена':
            controller.show_main_menu(inner_msg.chat.id)
            return
        controller.add_user_question(inner_msg.chat.id, inner_msg.message_id)
        bot.send_message(inner_msg.chat.id, 'Хмм, интересный вопрос! Дай мне немного времени над ним подумать 😊')
        controller.show_main_menu(inner_msg.chat.id)

    keyboard = types.ReplyKeyboardRemove()
    text = 'Напиши свой вопрос или введи "Отмена"'
    msg = bot.send_message(call.message.chat.id, text, reply_markup=keyboard)
    bot.register_next_step_handler(msg, process_custom_question_step)


@bot.message_handler(func=lambda msg: msg.text == '❓ Вопросы и ответы')
def handle_faq_msg(message):
    with shelve.open(shelve_name) as storage:
        shelve_users = storage['users']
        if message.chat.id not in shelve_users:
            shelve_users[message.chat.id] = {}
        shelve_users[message.chat.id]['faq_message_id'] = None
        storage['users'] = shelve_users
    controller.send_faq_msg(message.chat.id)


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


# @bot.message_handler(func=lambda msg: True)
# def handle_any_msg(message):
#     controller.show_main_menu(message.chat.id)


def main():
    # controller.show_main_menu()
    bot.polling(none_stop=True)


if __name__ == '__main__':
    main()
