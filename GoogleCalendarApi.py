from __future__ import print_function
import httplib2
import os

from apiclient import discovery
from oauth2client import client
from oauth2client import tools as gcal_api_tools
from oauth2client.file import Storage

import datetime
import dateutil.parser
import configparser
from SQLighter import SQLighter


class GoogleCalendarApi:
    def __init__(self):
        self.__config = configparser.ConfigParser()
        self.__config.read('config.ini')
        # If modifying these scopes, delete your previously saved credentials
        # at ~/.credentials/calendar-python-quickstart.json
        self.SCOPES = self.__config.get('GOOGLE_CALENDAR_API', 'scopes')
        self.CLIENT_SECRET_FILE = self.__config.get('GOOGLE_CALENDAR_API', 'client_secret_file')
        self.APPLICATION_NAME = self.__config.get('GOOGLE_CALENDAR_API', 'application_name')

        try:
            import argparse
            self.flags = argparse.ArgumentParser(parents=[gcal_api_tools.argparser]).parse_args()
        except ImportError:
            self.flags = None

        self.service = self.__get_service()

    def __get_credentials(self):
        """Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        Returns:
            Credentials, the obtained credential.
        """
        # home_dir = os.path.expanduser('~')
        home_dir = ''
        credential_dir = os.path.join(home_dir, '.credentials')
        if not os.path.exists(credential_dir):
            os.makedirs(credential_dir)
        credential_path = os.path.join(credential_dir,
                                       'google-calendar-api.json')

        store = Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(self.CLIENT_SECRET_FILE, self.SCOPES)
            flow.user_agent = self.APPLICATION_NAME
            if self.flags:
                credentials = gcal_api_tools.run_flow(flow, store, self.flags)
            else:  # Needed only for compatibility with Python 2.6
                credentials = gcal_api_tools.run(flow, store)
            print('Storing credentials to ' + credential_path)
        return credentials

    def __get_service(self):
        credentials = self.__get_credentials()
        http = credentials.authorize(httplib2.Http())
        service = discovery.build('calendar', 'v3', http=http)
        return service

    def get_html_links(self):
        db = SQLighter(self.__config.get('BOT', 'db_name'))
        calendars = db.get_calendars()
        url_template = self.__config.get('BOT', 'webcal')
        result = []
        for calendar in calendars:
            url = url_template.replace('{{calendar_id}}', calendar['id_calendar'])
            result.append('<a href=\'%s\'>%s</a>' % (url, calendar['name']))
        return result

    def get_event(self, calendar_id, event_id):
        response = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        if response['status'] != 'confirmed':
            return None
        db = SQLighter(self.__config.get('BOT', 'db_name'))
        calendar = db.get_calendar_by_id(calendar_id)
        event = db.get_event_by_id(calendar_id, event_id)
        response['calendar_id'] = calendar_id
        response['calendar_index'] = calendar['index']
        result = {
            'calendar_id': response['calendar_id'],
            'calendar_index': response['calendar_index'],
            'id': response['id'],
            'event_index': event['index'],
            'area': calendar['name'],
            'name': response['summary'],
            'location': response.get('location', ''),
            'datetime_start': dateutil.parser.parse(response['start'].get('dateTime', response['start'].get('date'))),
            'datetime_end': dateutil.parser.parse(response['end'].get('dateTime', response['end'].get('date')))
        }
        return result

    def get_events(self, events):
        result = [self.get_event(e['calendar_id'], e['event_id']) for e in events]
        result = [x for x in result if x]
        result.sort(key=lambda e: e['datetime_start'])
        return result

    def get_calendar_events(self, calendar_id=None, time_min=None, time_max=None):
        if time_min:
            time_min = time_min.isoformat() + '+05:00'
        if time_max:
            time_max = time_max.isoformat() + '+05:00'
        responses = []
        db = SQLighter(self.__config.get('BOT', 'db_name'))
        calendars = db.get_calendars()
        if not calendar_id:
            for calendar in calendars:
                response = self.service.events().list(
                    calendarId=calendar['id_calendar'], timeMin=time_min, timeMax=time_max,
                    singleEvents=True, orderBy='startTime').execute()
                [db.insert_event(calendar['id_calendar'], event['id']) for event in response['items']]
                response['calendar_id'] = calendar['id_calendar']
                response['calendar_index'] = calendar['index']
                responses.append(response)
        else:
            response = self.service.events().list(
                calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy='startTime').execute()
            [db.insert_event(calendar_id, event['id']) for event in response['items']]
            response['calendar_id'] = calendar_id
            calendar = db.get_calendar_by_id(calendar_id)
            response['calendar_index'] = calendar['index']
            responses.append(response)
        events = []
        for response in responses:
            events.extend([{
                'calendar_id': response['calendar_id'],
                'calendar_index': response['calendar_index'],
                'id': event['id'],
                'event_index': db.get_event_by_id(response['calendar_id'], event['id'])['index'],
                'area': response['summary'],
                'name': event['summary'],
                'location': event.get('location', ''),
                'datetime_start': dateutil.parser.parse(event['start'].get('dateTime', event['start'].get('date'))),
                'datetime_end': dateutil.parser.parse(event['end'].get('dateTime', event['end'].get('date')))
            } for event in response['items']])
        events.sort(key=lambda e: e['datetime_start'])
        return events

    def close(self):
        pass
