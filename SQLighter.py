# -*- coding: utf-8 -*-
import sqlite3


class SQLighter:
    def __init__(self, database):
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

    def get_all_users(self):
        with self.connection:
            return self.cursor.execute('SELECT * FROM user').fetchall()

    def get_user(self, user_id):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user WHERE id_user = ?', (user_id,)).fetchall()
            return result[0] if result else None

    def get_clients(self):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user WHERE admin = 0').fetchall()
            return result

    def get_newsletter_users(self):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user WHERE newsletter = 1').fetchall()
            return result

    def insert_user(self, user_id, username, first_name, last_name):
        with self.connection:
            self.cursor.execute('INSERT INTO user (id_user, username, first_name, last_name) VALUES (?, ?, ?, ?)',
                                (user_id, username, first_name, last_name,))

    def insert_user_question(self, user_id, message_id):
        with self.connection:
            self.cursor.execute('INSERT INTO user_question (id_question, user_id) VALUES (?, ?)',
                                (message_id, user_id,))

    def get_user_questions(self, admin_id=None, only_unanswered=True):
        with self.connection:
            if admin_id:
                admin = self.get_user(admin_id)
                if only_unanswered:
                    result = self.cursor.execute(
                        'SELECT * FROM user_question WHERE '
                        '"timestamp" BETWEEN IFNULL(?, 0) AND ? AND answer_user_id IS NULL',
                        (admin['signout_timestamp'], admin['signin_timestamp'],)).fetchall()
                else:
                    result = self.cursor.execute(
                        'SELECT * FROM user_question WHERE '
                        '"timestamp" BETWEEN IFNULL(?, 0) AND ?',
                        (admin['signout_timestamp'], admin['signin_timestamp'],)).fetchall()
            else:
                if only_unanswered:
                    result = self.cursor.execute('SELECT * FROM user_question WHERE answer_user_id IS NULL').fetchall()
                else:
                    result = self.cursor.execute('SELECT * FROM user_question').fetchall()
            return result

    def answer_user_question(self, user_id, question_id, answer_user_id, answer_message_id=None):
        with self.connection:
            self.cursor.execute('UPDATE user_question SET answer_user_id = ?, answer_message_id = ?'
                                'WHERE user_id = ? AND id_question = ?',
                                (answer_user_id, answer_message_id, user_id, question_id,))

    def get_user_events(self, user_id):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user_event WHERE user_id = ?', (user_id,)).fetchall()
            return result

    def insert_user_event(self, user_id, calendar_id, event_id):
        with self.connection:
            try:
                self.cursor.execute('INSERT INTO user_event (user_id, calendar_id, event_id) VALUES (?, ?, ?)',
                                    (user_id, calendar_id, event_id,))
            except:
                pass

    def get_event_liked_count(self, calendar_id, event_id):
        with self.connection:
            result = self.cursor.execute('SELECT COUNT(*) AS "count" FROM user_event WHERE'
                                         ' calendar_id = ? AND event_id = ?', (calendar_id, event_id,)).fetchone()
            return result['count']

    def delete_user_event(self, user_id, calendar_id, event_id):
        with self.connection:
            self.cursor.execute('DELETE FROM user_event WHERE user_id = ? AND calendar_id = ? AND event_id = ?',
                                (user_id, calendar_id, event_id,))

    def __set_admin_timestamp(self, user_id, admin):
        with self.connection:
            if admin:
                self.cursor.execute('UPDATE user SET signin_timestamp = datetime(\'now\',\'utc\') WHERE id_user = ?',
                                    (user_id,)).fetchall()
            else:
                self.cursor.execute('UPDATE user SET signout_timestamp = datetime(\'now\',\'utc\') WHERE id_user = ?',
                                    (user_id,)).fetchall()

    def set_admin(self, user_id, admin):
        with self.connection:
            self.cursor.execute('UPDATE user SET admin = ? WHERE id_user = ?', (admin, user_id,))
        self.__set_admin_timestamp(user_id, admin)

    def is_admin(self, user_id):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user WHERE id_user = ?', (user_id,)).fetchone()
            return result and result['admin']

    def get_admins(self):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user WHERE admin = 1').fetchall()
            return result

    def get_calendars(self):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM calendar').fetchall()
            return result

    def get_calendar_by_index(self, calendar_index):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM calendar WHERE "index" = ?', (calendar_index,)).fetchone()
            return result

    def get_calendar_by_id(self, calendar_id):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM calendar WHERE id_calendar = ?', (calendar_id,)).fetchone()
            return result

    def get_event_by_index(self, event_index):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM event WHERE "index" = ?', (event_index,)).fetchone()
            return result

    def get_event_by_id(self, calendar_id, event_id):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM event WHERE calendar_id = ? AND id_event = ?',
                                         (calendar_id, event_id,)).fetchone()
            return result

    def insert_event(self, calendar_id, event_id):
        with self.connection:
            if not self.get_event_by_id(calendar_id, event_id):
                result = self.cursor.execute('INSERT INTO event (calendar_id, id_event) VALUES (?, ?)',
                                            (calendar_id, event_id,))

    def set_user_first_time(self, user_id, first_time):
        with self.connection:
            self.cursor.execute('UPDATE user SET first_time = ? WHERE id_user = ?', (first_time, user_id,))

    def set_user_send_questions(self, user_id, send_questions):
        with self.connection:
            self.cursor.execute('UPDATE user SET send_questions = ? WHERE id_user = ?', (send_questions, user_id,))

    def insert_user_day(self, user_id, day, visit=False):
        with self.connection:
            try:
                self.cursor.execute('INSERT INTO user_days (user_id, "day", visit) VALUES (?, ?, ?)',
                                    (user_id, day, visit,))
            except:
                pass

    def user_visits_day(self, user_id, day):
        with self.connection:
            result = self.cursor.execute('SELECT visit FROM user_days WHERE user_id = ? AND "day" = ?',
                                         (user_id, day,)).fetchone()
            if not result:
                self.insert_user_day(user_id, day)
                return False
            return result['visit']

    def set_user_visit_day(self, user_id, day, visit):
        with self.connection:
            self.cursor.execute('UPDATE user_days SET visit = ? WHERE user_id = ? AND "day" = ?',
                                (visit, user_id, day,))

    def set_user_gender(self, user_id, male):
        with self.connection:
            self.cursor.execute('UPDATE user SET male = ? WHERE id_user = ?', (male, user_id,))

    def set_user_age(self, user_id, age):
        with self.connection:
            self.cursor.execute('UPDATE user SET age = ? WHERE id_user = ?', (age, user_id,))

    def close(self):
        self.connection.close()
