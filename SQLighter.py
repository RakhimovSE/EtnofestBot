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

    def get_user_questions(self, admin_id = None):
        with self.connection:
            if admin_id:
                admin = self.get_user(admin_id)
                result = self.cursor.execute('SELECT * FROM user_question WHERE '
                                             '"timestamp" BETWEEN IFNULL(?, 0) AND ? AND answered = 0',
                                             (admin['signout_timestamp'], admin['signin_timestamp'],)).fetchall()
            else:
                result = self.cursor.execute('SELECT * FROM user_question WHERE answered = 0').fetchall()
            return result

    def answer_user_question(self, user_id, question_id, answered = 1):
        with self.connection:
            self.cursor.execute('UPDATE user_question SET answered = ? WHERE user_id = ? AND id_question = ?',
                                (answered, user_id, question_id,))

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
            result = self.cursor.execute('SELECT * FROM user WHERE id_user = ?', (user_id,)).fetchall()
            return True if result and result[0]['admin'] == 1 else False

    def get_admins(self):
        with self.connection:
            result = self.cursor.execute('SELECT * FROM user WHERE admin = 1').fetchall()
            return result

    def close(self):
        self.connection.close()
