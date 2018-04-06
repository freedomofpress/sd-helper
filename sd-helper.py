#!/usr/bin/env python3

# A Gitter bot to automatically post message(s) on the SecureDrop room. It can post
# message(s) on any day of the week, at any specified time value(s). Authorized users
# can stop the bot from posting on certain day(s) by mentioning it followed by a valid
# command. The behaviour of the bot can be configured in 'data.yml'. It can be used in
# any other Gitter room as well.

import calendar
import datetime
import functools
import json
import os
import requests
import schedule
import time
import traceback
import yaml

from dateutil.parser import parse
from multiprocessing import Pool

# Room id of "https://gitter.im/freedomofpress/securedrop".
sd_room_id = '53bb302d107e137846ba5db7'

target_url = 'https://api.gitter.im/v1/rooms/' + sd_room_id + '/chatMessages'
stream_url = 'https://stream.gitter.im/v1/rooms/' + sd_room_id + '/chatMessages'
reply_url = target_url


# A function which defines a decorator for handling exceptions that may happen
# during job (which is posting scheduled messages) execution.
def catch_exceptions(cancel_on_failure=False):
    def decorator(job_func):
        @functools.wraps(job_func)
        def wrapper(*args, **kwargs):
            try:
                return job_func(*args, **kwargs)
            except:
                print(traceback.format_exc())
                if cancel_on_failure:
                    return schedule.CancelJob
        return wrapper
    return decorator


# Read the API Token from external file.
def get_api_token():
    with open("auth.yml", 'r') as auth_ymlfile:
        try:
            c = yaml.load(auth_ymlfile)
        except yaml.YAMLError as exc_a:
            print(exc_a)
    api_token = c['apitoken']
    return api_token


# Read the IDs of users who are allowed to blacklist days by posting a
# message in the SecureDrop room. Returns a list of IDs.
def get_approved_users():
    approved_users = []
    with open("approved_users.yml", 'r') as users_ymlfile:
        try:
            u = yaml.load(users_ymlfile)
        except yaml.YAMLError as exc_u:
            print(exc_u)
    
    for user_id in u:
        approved_users.append(user_id)
    return approved_users


# Read blacklisted days from an external file generated by reading the
# messages which mention '@sd-helper' on SecureDrop Gitter room.
def get_blacklist():
    current_blacklist = []
    with open("blacklist.yml", 'a+') as bl_ymlfile:
        if os.stat("blacklist.yml").st_size == 0:
            return current_blacklist
        bl_ymlfile.seek(0)
        try:
            bl = yaml.load(bl_ymlfile)
        except yaml.YAMLError as exc_b:
            print(exc_b)
    
    for bl_date in bl:
        current_blacklist.append(bl_date)
    return current_blacklist


# Read the message to be posted along with the day(s) and time value(s)
# from 'data.yml'. Returns a list of all tasks (a task is a particular
# message to be posted), in which each task itself is a list of 3 items.
def get_data():
    task = []
    list_of_tasks = []
    with open("data.yml", 'r') as data_ymlfile:
        try:
            cfg = yaml.load(data_ymlfile)
        except yaml.YAMLError as exc_d:
            print(exc_d)

    for section in cfg:
        task.extend([cfg[section]['message'],
                sorted(cfg[section]['day']),
                sorted(cfg[section]['time'])])
        new_task = list(task)
        list_of_tasks.append(new_task)
        task.clear()
    return list_of_tasks


# Send a reply to messages/commands received by authorized users
def send_reply(msg):
    api_token = get_api_token()
    headers = {'Content-Type': 'application/json',
           'Accept': 'application/json',
           'Authorization': 'Bearer {0}'.format(api_token)}
    data = {'text': msg}
    try:
        response = requests.post(reply_url, headers=headers, json=data)
    except requests.exceptions.RequestException as exc_rep:
        print("An exception occured while posting a reply.")
        print(exc_rep)


# Use the streaming API to listen to messages in the SecureDrop room, and
# write a date to 'blacklist.yml' if correct format of blacklisting dates is
# encountered. Otherwise post an informative (and sometimes slightly humorous)
# message.
def stream_sd():
    api_token = get_api_token()
    headers = {'Accept': 'application/json',
           'Authorization': 'Bearer {0}'.format(api_token)}

    try:
        stream_response = requests.get(stream_url, headers=headers, stream=True)
    except requests.exceptions.RequestException as exc_req:
        print(exc_req)

    if stream_response.status_code == 200:
        lines = stream_response.iter_lines()
        for line in lines:
            response_str = line.decode('utf-8')
            # Next if condition is to handle occasional extra newline characters
            # placed between messages. These characters are sent as periodic 
            # "keep-alive" messages to tell clients and NAT firewalls that the 
            # connection is still alive during low message volume periods.
            if response_str.splitlines() != [' ']:
                dm_data = json.loads(response_str)
                message_info = dm_data['text']
                from_user = dm_data['fromUser']['displayName']
                from_user_id = dm_data['fromUser']['id']
                approved_users = get_approved_users()

                if message_info.startswith('@sd-helper') and from_user_id in approved_users:
                    message_info = message_info[11:]
                    if message_info.startswith('blacklist:'):
                        message_info = message_info[10:]
                        try:
                            new_date = str(parse(message_info).date())
                            # Don't accept past dates. What's the point in blacklisting them.
                            if parse(message_info).date() < datetime.datetime.now().date():
                                send_reply(":heavy_exclamation_mark: I'm afraid that date has"
                                           " already passed. Can't really do much about it!")
                            else:
                                # Don't accept same date to be blacklisted again.
                                already_bl_dates = get_blacklist()
                                if new_date in already_bl_dates:
                                    send_reply(":heavy_exclamation_mark: The date {0} is already"
                                               " blacklisted. Doing it again will only make it"
                                               " feel worse.".format(new_date))
                                else:
                                    with open('blacklist.yml', 'a') as f:
                                        f.write("- '" + new_date + "'" + '\n')
                                    send_reply(":white_check_mark: **Success**! No further"
                                               " messages will be posted on {0}. This action was"
                                               " initiated by **{1}**.".format(new_date, from_user))
                        except ValueError:
                            send_reply(":x: Something was wrong with the specified date."
                                       " Try again maybe.")

    else:
        print('An error occured while using the streaming API.'
            ' Status code [{0}]'.format(stream_response.status_code))


# The job of the bot, making a POST request with the headers and data.
@catch_exceptions(cancel_on_failure=True)
def job(msg):
    api_token = get_api_token()
    headers = {'Content-Type': 'application/json',
           'Accept': 'application/json',
           'Authorization': 'Bearer {0}'.format(api_token)}
    data = {'text': msg}
    print('On {0} at {1}:{2}'.format(datetime.datetime.now().date(),
                                str(datetime.datetime.now().time().hour).zfill(2),
                                str(datetime.datetime.now().time().minute).zfill(2)))
    response = requests.post(target_url, headers=headers, json=data)

    if response.status_code >= 500:
        print('[{0}] Server Error.'.format(response.status_code))
    elif response.status_code == 404:
        print('[{0}] URL not found: [{1}]'.format(response.status_code, target_url))
    elif response.status_code == 401:
        print('[{0}] Authentication Failed.'.format(response.status_code))
    elif response.status_code >= 400:
        print('[{0}] Bad Request.'.format(response.status_code))
    elif response.status_code >= 300:
        print('[{0}] Unexpected redirect.'.format(response.status_code))
    elif response.status_code == 200:
        print('[{0}] The request succeeded.\n'.format(response.status_code))
        print('Posted the following message: \n{0}\n'.format(msg))
        print('Received the following response: \n{0}\n\n\n'.format(response.json()))
    else:
        print('Unexpected Error: [HTTP {0}]: Content: {1}'.format(response.status_code,
                                                                  response.content))


def main_job():
    all_days = list(calendar.day_name)
    list_of_tasks = get_data()
    
    for task in list_of_tasks:
        for day_of_week in task[1]:
            for this_time in task[2]:
                getattr(schedule.every(),
                        str(all_days[day_of_week]).lower()).at(this_time).do(job, msg = task[0])

    while True:
        current_blacklist = get_blacklist()
        if str(datetime.datetime.now().date()) not in current_blacklist:
            schedule.run_pending()
        time.sleep(5)


def main():
    pool = Pool(processes=2)
    
    pool.apply_async(main_job)
    pool.apply_async(stream_sd)
    pool.close()
    pool.join()


if __name__ == '__main__':
    main()
