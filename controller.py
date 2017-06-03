import hashlib
import telebot
from telebot import types
import shelve
from datetime import datetime

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
    result = '%s - %s (%s)' % (datetime.strftime(datetime_start, '%H:%M'),
                               datetime.strftime(datetime_end, '%H:%M'),
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


def show_main_menu(user_id=None):
    db = SQLighter(db_name)
    if user_id:
        bot.send_message(user_id, 'Выберите пункт меню',
                         reply_markup=get_keyboard(user_id), disable_notification=True)
        return
    users = db.get_all_users()
    for user in users:
        try:
            keyboard = get_keyboard(user['id_user'])
            bot.send_message(user['id_user'], 'Выберите пункт меню',
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
        ['❓ Вопросы и ответы']
    ]
    set_reply_keyboard_markup(keyboard, markup)
    return keyboard


def get_keyboard(user_id):
    db = SQLighter(db_name)
    return admin_keyboard if db.is_admin(user_id) else user_keyboard


admin_keyboard = __get_admin_keyboard()
user_keyboard = __get_user_keyboard()
