import hashlib
from telebot import types
import shelve
from datetime import datetime
import json

from SQLighter import SQLighter
from main import db_name, shelve_name, bot

content_types_handler = {
    'text': lambda uid, m: bot.send_message(uid, m.text),
    'photo': lambda uid, m: bot.send_photo(uid, m.photo[0].file_id) if len(m.photo) else None,
    'audio': lambda uid, m: bot.send_audio(uid, m.audio.file_id),
    'document': lambda uid, m: bot.send_document(uid, m.document.file_id),
    'sticker': lambda uid, m: bot.send_sticker(uid, m.sticker.file_id),
    'video': lambda uid, m: bot.send_video(uid, m.video.file_id),
    'voice': lambda uid, m: bot.send_voice(uid, m.voice.file_id),
    'video_note': lambda uid, m: bot.send_video_note(uid, m.video_note.file_id),
    'location': lambda uid, m: bot.send_location(uid, m.location.latitude, m.location.longitude),
    'venue': lambda uid, m: bot.send_venue(uid, m.venue.location.latitude, m.venue.location.longitude,
                                           m.venue.title, m.venue.address, m.venue.foursquare_id),
    'contact': lambda uid, m: bot.send_contact(uid, m.contact.phone_number,
                                               m.contact.first_name, m.contact.last_name)
}


def get_salted_hash(login, password):
    return get_md5(login + get_md5(password))


def get_md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def get_formatted_event_date(datetime_start, datetime_end):
    if datetime_start != datetime_end:
        result = '%s - %s (%s)' % (datetime.strftime(datetime_start, '%H:%M'),
                                   datetime.strftime(datetime_end, '%H:%M'),
                                   datetime.strftime(datetime_start, '%d.%m'))
    else:
        result = '%s (%s)' % (datetime.strftime(datetime_start, '%H:%M'),
                              datetime.strftime(datetime_start, '%d.%m'))
    return result


def is_digit(n):
    try:
        int(n)
        return True
    except ValueError:
        return False


def send_event(user_id, event_id):
    pass


def send_user_question(admin_id, user_id, question_id):
    try:
        bot.forward_message(admin_id, user_id, question_id)
        keyboard = types.InlineKeyboardMarkup()
        callback_data = 'question_answer_%d_%d' % (user_id, question_id)
        buttons = []
        buttons.append(types.InlineKeyboardButton('📢 Ответить', callback_data=callback_data))
        callback_data = 'question_decline_%d_%d' % (user_id, question_id)
        buttons.append(types.InlineKeyboardButton('❌ Отклонить', callback_data=callback_data))
        keyboard.add(*buttons)
        bot.send_message(admin_id, 'Выберите действие', reply_markup=keyboard)
        return True
    except Exception as e:
        # db.answer_user_question(question['user_id'], question['id_question'])
        return False


def get_time_inline_keyboard(calendar_index, day):
    result = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    callback_data = 'schedule_printevent_%d_%d_0_24' % (calendar_index, day)
    button = types.InlineKeyboardButton('Весь день', callback_data=callback_data)
    result.add(button)
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


def send_gettime_msg(call, calendar_index, day, new_message = True):
    keyboard = get_time_inline_keyboard(calendar_index, day)
    if calendar_index != -1:
        db = SQLighter(db_name)
        calendar = db.get_calendar_by_index(calendar_index)
        text = 'Площадка <b>"%s"</b>' % calendar['name']
    else:
        text = '<b>Все</b> площадки'
    text += '\n<i>%d июня</i>\n\nКакое время тебя интересует?' % day
    if new_message:
        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode='HTML', reply_markup=keyboard)


def get_faq_inline_keyboard(user_id):
    with open('faq.json', 'r', encoding='utf-8') as f:
        faq = json.load(f)
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    buttons = []
    for i, question in enumerate(faq):
        callback_data = 'question_show_%d' % i
        button = types.InlineKeyboardButton(question['abbr'], callback_data=callback_data)
        buttons.append(button)
    button = types.InlineKeyboardButton('❓ Задать свой вопрос', callback_data='question_custom')
    buttons.append(button)
    keyboard.add(*buttons)
    return keyboard


def send_faq_msg(user_id):
    keyboard = get_faq_inline_keyboard(user_id)
    msg = bot.send_message(user_id, 'Выбери вопрос или задай свой, если не нашел ответ!', reply_markup=keyboard)


def send_user_questions(admin_id, from_last_signout = True, only_unanswered = True):
    db = SQLighter(db_name)
    questions = db.get_user_questions(admin_id if from_last_signout else None, only_unanswered)
    if questions and from_last_signout:
        bot.send_message(admin_id, 'Поступили новые вопросы от пользователей')
    sended_questions = 0
    for question in questions:
        if send_user_question(admin_id, question['user_id'], question['id_question']):
            sended_questions += 1
    if sended_questions == 0 and not from_last_signout:
        bot.send_message(admin_id, 'Новых вопросов не поступало')


def add_user_question(user_id, question_id):
    db = SQLighter(db_name)
    db.insert_user_question(user_id, question_id)
    admins = db.get_admins()
    for admin in admins:
        try:
            bot.send_message(admin['id_user'], 'Поступил новый вопрос от пользователя')
            send_user_question(admin['id_user'], user_id, question_id)
        except:
            pass


def send_newsletter(from_user_id):
    with shelve.open(shelve_name) as storage:
        messages = storage['users'][str(from_user_id)]['newsletter_messages']
        del storage['users'][str(from_user_id)]['newsletter_messages']
    db = SQLighter(db_name)
    users = db.get_newsletter_users()
    for user in users:
        if user['id_user'] == from_user_id:
            continue
        for message in messages:
            try:
                if message.content_type in content_types_handler:
                    content_types_handler[message.content_type](user['id_user'], message)
                else:
                    bot.forward_message(user['id_user'], message.chat.id, message.message_id)
            except Exception as e:
                print(str(e))


def get_call_data(data):
    result = data.split('_')
    result = [int(el) if is_digit(el) else el for el in result]
    return result


def send_networking_users(request_user_id, users):
    for user in users:
        if user['last_name']:
            text = '%s %s, возраст: %d' % (user['first_name'], user['last_name'], user['age'])
        else:
            text = '%s, возраст: %d' % (user['first_name'], user['age'])
        keyboard = types.InlineKeyboardMarkup()
        buttons = [
            types.InlineKeyboardButton('👍', callback_data='networking_like_%d' % user['id_user']),
            types.InlineKeyboardButton('👎', callback_data='networking_dislike_%d' % user['id_user'])
        ]
        keyboard.add(*buttons)
        photo_id = get_user_profile_photo_id(user['id_user'])
        if photo_id:
            bot.send_photo(request_user_id, photo_id, caption=text, reply_markup=keyboard)
        else:
            bot.send_message(request_user_id, text, reply_markup=keyboard)
    if not users:
        text = 'Пока что я не могу кого-то тебе посоветовать 🤔 ' \
               'Попробуй чуть позже, когда со мной познакомятся новые люди 😊'
        bot.send_message(request_user_id, text)


def get_user_profile_photo_id(user_id):
    photo = bot.get_user_profile_photos(user_id, limit=1)
    return photo.photos[0][0].file_id if photo.total_count > 0 else None


def show_main_menu(user_id=None):
    db = SQLighter(db_name)
    text = 'Привет! Как я могу тебе помочь?'
    if user_id:
        bot.send_message(user_id, text,
                         reply_markup=get_keyboard(user_id), disable_notification=True)
        return
    users = db.get_all_users()
    for user in users:
        try:
            keyboard = get_keyboard(user['id_user'])
            bot.send_message(user['id_user'], text,
                             reply_markup=keyboard, disable_notification=True)
        except Exception as e:
            print(str(e))


def set_reply_keyboard_markup(keyboard, markup):
    for row in markup:
        keyboard.add(*row)


def __get_admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup = [
        ['📧 Рассылка'],
        ['❓ Ответить на вопросы'],
        ['👤 Режим пользователя']
    ]
    set_reply_keyboard_markup(keyboard, markup)
    return keyboard


def __get_user_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup = [
        ['📆 Расписание'],
        ['👫 Познакомиться'],
        ['❓ Вопросы и ответы']
    ]
    set_reply_keyboard_markup(keyboard, markup)
    return keyboard


def get_keyboard(user_id):
    db = SQLighter(db_name)
    return admin_keyboard if db.is_admin(user_id) else user_keyboard


admin_keyboard = __get_admin_keyboard()
user_keyboard = __get_user_keyboard()
