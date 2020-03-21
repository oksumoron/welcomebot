#!/usr/bin/env python3
import configparser
import logging
import random
from datetime import timezone, tzinfo, datetime, timedelta
from os.path import dirname, realpath, join
from time import sleep
import traceback
import sys
from html import escape

from telegram import ParseMode, TelegramError, Update, MessageEntity
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters
from telegram.ext.dispatcher import run_async
from emoji import emojize
#from telegram.contrib.botan import Botan

import python3pickledb as pickledb

# Configuration

def get_settings(block, name):
    rootdir = dirname(realpath(__file__))
    settings = configparser.ConfigParser()
    settings.read(join(rootdir, 'token.ini'))
    return settings.get(block, name)


BOTNAME = get_settings("Bot", "name")
TOKEN = get_settings("Bot", "token")
BOTAN_TOKEN = 'BOTANTOKEN'

REQUEST_KWARGS={
    # "USERNAME:PASSWORD@" is optional, if you need authentication:
    'proxy_url': 'http://51.158.123.35:8811',
}
#https://173.249.42.83:3128
#https://136.243.14.107:8090
#http://207.154.231.212:1080

help_text = 'Welcomes everyone that enters a group chat that this bot is a ' \
            'part of. By default, only the person who invited the bot into ' \
            'the group is able to change settings.\nCommands:\n\n' \
            '/welcome - Set welcome message\n' \
            '/goodbye - Set goodbye message\n' \
            '/disable\\_goodbye - Disable the goodbye message\n' \
            '/lock - Only the person who invited the bot can change messages\n' \
            '/unlock - Everyone can change messages\n' \
            '/quiet - Disable "Sorry, only the person who..." ' \
            '& help messages\n' \
            '/unquiet - Enable "Sorry, only the person who..." ' \
            '& help messages\n\n' \
            'You can use _$username_ and _$title_ as placeholders when setting' \
            ' messages. [HTML formatting]' \
            '(https://core.telegram.org/bots/api#formatting-options) ' \
            'is also supported.\n'
'''
Create database object
Database schema:
<chat_id> -> welcome message
<chat_id>_bye -> goodbye message
<chat_id>_adm -> user id of the user who invited the bot
<chat_id>_lck -> boolean if the bot is locked or unlocked
<chat_id>_quiet -> boolean if the bot is quieted

chats -> list of chat ids where the bot has received messages in.
'''
# Create database object
db = pickledb.load('bot.db', True)

if not db.get('chats'):
    db.set('chats', [])

# Set up logging
root = logging.getLogger()
root.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, filename='example.log',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)


@run_async
def send_async(bot, *args, **kwargs):
    bot.sendMessage(*args, **kwargs)


def check(bot, update, override_lock=None):
    """
    Perform some checks on the update. If checks were successful, returns True,
    else sends an error message to the chat and returns False.
    """

    chat_id = update.message.chat_id
    chat_str = str(chat_id)

    if chat_id > 0:
        send_async(bot, chat_id=chat_id,
                   text='Please add me to a group first!')
        return False

    locked = override_lock if override_lock is not None \
        else db.get(chat_str + '_lck')

    if locked and db.get(chat_str + '_adm') != update.message.from_user.id:
        if not db.get(chat_str + '_quiet'):
            send_async(bot, chat_id=chat_id, text='Sorry, only the person who '
                                                  'invited me can do that.')
        return False

    return True


# Welcome a user to the chat
def welcome(bot, update):
    """ Welcomes a user to the chat """

    message = update.message
    chat_id = message.chat.id
    logger.info('%s joined to chat %d (%s)'
                 % (escape(message.new_chat_members[0].first_name),
                    chat_id,
                    escape(message.chat.title)))

    # Pull the custom message for this chat from the database
    text = db.get(str(chat_id))

    # Use default message if there's no custom one set
    if text is None:
        text = 'Hello $username! Welcome to $title %s' \
                  % emojize(":grinning_face_with_smiling_eyes:")

    # Replace placeholders and send message
    text = text.replace('$username','<a href="tg://user?id={}">{}</a>'.format(
                        message.new_chat_members[0].id,message.new_chat_members[0].first_name))\
        .replace('$title', message.chat.title)
    send_async(bot, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# Welcome a user to the chat
def goodbye(bot, update):
    """ Sends goodbye message when a user left the chat """

    message = update.message
    chat_id = message.chat.id
    logger.info('%s left chat %d (%s)'
                 % (escape(message.left_chat_member.first_name),
                    chat_id,
                    escape(message.chat.title)))

    # Pull the custom message for this chat from the database
    text = db.get(str(chat_id) + '_bye')

    # Goodbye was disabled
    if text is False:
        return

    # Use default message if there's no custom one set
    if text is None:
        text = 'Goodbye, $username!'

    # Replace placeholders and send message
    text = text.replace('$username',
                        message.left_chat_member.first_name)\
        .replace('$title', message.chat.title)
    send_async(bot, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# Introduce the bot to a chat its been added to
def introduce(bot, update):
    """
    Introduces the bot to a chat its been added to and saves the user id of the
    user who invited us.
    """

    chat_id = update.message.chat.id
    invited = update.message.from_user.id

    logger.info('Invited by %s to chat %d (%s)'
                % (invited, chat_id, update.message.chat.title))

    db.set(str(chat_id) + '_adm', invited)
    db.set(str(chat_id) + '_lck', True)

    text = 'Hello %s! I will now greet anyone who joins this chat with a' \
           ' nice message %s \nCheck the /help command for more info!'\
           % (update.message.chat.title,
              emojize(":grinning_face_with_smiling_eyes:"))
    send_async(bot, chat_id=chat_id, text=text)


# Print help text
def help(bot, update):
    """ Prints help text """

    chat_id = update.message.chat.id
    chat_str = str(chat_id)
    if (not db.get(chat_str + '_quiet') or db.get(chat_str + '_adm') ==
            update.message.from_user.id):
        send_async(bot, chat_id=chat_id,
                   text=help_text,
                   parse_mode=ParseMode.MARKDOWN,
                   disable_web_page_preview=True)


# Set custom message
def set_welcome(bot, update, args):
    """ Sets custom welcome message """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update):
        return

    # Split message into words and remove mentions of the bot
    message = ' '.join(args).replace("\\n", "\n")

    # Only continue if there's a message
    if not message:
        send_async(bot, chat_id=chat_id, 
                   text='You need to send a message, too! For example:\n'
                        '<code>/welcome Hello $username, welcome to '
                        '$title!</code>',
                   parse_mode=ParseMode.HTML)
        return

    # Put message into database
    db.set(str(chat_id), message)

    send_async(bot, chat_id=chat_id, text='Got it!')


# Set custom message
def set_goodbye(bot, update, args):
    """ Enables and sets custom goodbye message """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update):
        return

    # Split message into words and remove mentions of the bot
    message = ' '.join(args)

    # Only continue if there's a message
    if not message:
        send_async(bot, chat_id=chat_id, 
                   text='You need to send a message, too! For example:\n'
                        '<code>/goodbye Goodbye, $username!</code>',
                   parse_mode=ParseMode.HTML)
        return

    # Put message into database
    db.set(str(chat_id) + '_bye', message)

    send_async(bot, chat_id=chat_id, text='Got it!')


def disable_goodbye(bot, update):
    """ Disables the goodbye message """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update):
        return

    # Disable goodbye message
    db.set(str(chat_id) + '_bye', False)

    send_async(bot, chat_id=chat_id, text='Got it!')


def enable_goodbye(bot, update):
    """ Disables the goodbye message """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update):
        return

    # Disable goodbye message
    db.set(str(chat_id) + '_bye', True)

    send_async(bot, chat_id=chat_id, text='Got it!')


def lock(bot, update):
    """ Locks the chat, so only the invitee can change settings """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update, override_lock=True):
        return

    # Lock the bot for this chat
    db.set(str(chat_id) + '_lck', True)

    send_async(bot, chat_id=chat_id, text='Got it!')


def quiet(bot, update):
    """ Quiets the chat, so no error messages will be sent """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update, override_lock=True):
        return

    # Lock the bot for this chat
    db.set(str(chat_id) + '_quiet', True)

    send_async(bot, chat_id=chat_id, text='Got it!')


def unquiet(bot, update):
    """ Unquiets the chat """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update, override_lock=True):
        return

    # Lock the bot for this chat
    db.set(str(chat_id) + '_quiet', False)

    send_async(bot, chat_id=chat_id, text='Got it!')


def unlock(bot, update):
    """ Unlocks the chat, so everyone can change settings """

    chat_id = update.message.chat.id

    # Check admin privilege and group context
    if not check(bot, update):
        return

    # Unlock the bot for this chat
    db.set(str(chat_id) + '_lck', False)

    send_async(bot, chat_id=chat_id, text='Got it!')


def empty_message(bot, update):
    """
    Empty messages could be status messages, so we check them if there is a new
    group member, someone left the chat or if the bot has been added somewhere.
    """

    # Keep chatlist
    chats = db.get('chats')

    if update.message.chat.id not in chats:
        chats.append(update.message.chat.id)
        db.set('chats', chats)
        logger.info("I have been added to %d chats" % len(chats))

    if len(update.message.new_chat_members) > 0:
        # Bot was added to a group chat
        if update.message.new_chat_members[0].username == BOTNAME:
            return introduce(bot, update)
        # Another user joined the chat
        else:
            return welcome(bot, update)

    # Someone left the chat
    elif update.message.left_chat_member is not None:
        if update.message.left_chat_member.username != BOTNAME:
            return goodbye(bot, update)


family_chat = -1001186177604
test_chat = -313765365


def send_test_chat_msg(bot, update):
    chat_id = update.message.chat_id
    if chat_id > 0:
        send_async(bot, chat_id=test_chat, text='{}'.format(update.message.text.split(" ", 1)[1]))


def send_family_chat_msg(bot, update):
    chat_id = update.message.chat_id
    if chat_id > 0:
        send_async(bot, chat_id=family_chat, text='{}'.format(update.message.text.split(" ", 1)[1]))


def bis_bald(bot, update):
    chats = db.get('chats')
    if update.message.chat.id not in chats:
        chats.append(update.message.chat.id)
        db.set('chats', chats)
        logger.info("I have been added to %d chats" % len(chats))
    logger.info("id: {}, name: {}".format(update.message.from_user.id, update.message.from_user.first_name))

    if update.message.text is not None:
        msg = update.message.text.lower()
        characters = ["Jonas", "David", "Abdi", "Carlos", "Omar", "Essam", "Mohammed", "Stefan",
                      "Kiki", "Sam", "Alex", "Sara", "Leonie", "Laura", "Hans",
                      "Linn", "Rentier", "Farid"]
        mains = ["Matteo", "Hanna", "Mia", "Amira"]

        if bot.name.lower() in msg and bot.name.lower() != msg:
            return at_handler(bot, update)

        if "bis" in msg and "bald" in msg:
            msgs = [emojize("Bis bald you back, {} :red_heart:"),
                    emojize("{}, :police_car_light:")]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])
        if "sommer 2020" in msg or "summer 2020" in msg:
            msgs = ["{}, can summer come already?!",
                    emojize("Summer 2020? Can't wait! :smiling_face_with_smiling_eyes:"),
                   emojize("{}, :police_car_light: :police_car_light: :police_car_light:")]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])
        """if "sad" in msg or "traurigkeit" in msg:
            msgs = ['Who said "sad"? I\'m calling positive police! <a href="tg://user?id={}">{}</a>',
                    emojize("Wee woo wee woo! :oncoming_police_car:"),
                    "{}, this is the positive police, we don't use word \"sad\" in this chat",
                    "{}, sad spelled backwards is das and das not good."]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])
        if " s a d " in msg or "s*d" in msg or "s a d" == msg:
            msgs = [emojize('{}, are you trying to mask word sad? :thinking_face:'),
                    emojize("{}, I see what you're trying to do :eyes:"),
                    "{}, nice try"]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])"""
        if "family" in msg and "chat" in msg:
            msgs = [emojize('That\'s right, we\'re all family here :red_heart:')]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])

        if "lonely" in msg:
            return echo(bot, update, "Lonely like island Ibiza", reply=True)

        if "hollandaise" in msg and "pizza" in msg:
            return echo(bot, update, "{}, I want a pizza margherita with extra tzatziki", reply=True)

        if "pineapple pizza" in msg or "mint chocolate" in msg or "toast hawaii" in msg:
            msgs = [emojize('Oh nooo, no food debates!'),
                    "Here we go again",
                    "{}, food discussions are important but first, let me make some tea"]
            return echo(bot, update, msgs[random.randint(0, len(msgs) - 1)])

        if "hawaii toast" in msg or "hawaii sandwich" in msg:
            return send_photo(bot, update, "hawaii.jpg", caption=";)", reply=True)

        if "food discussion" in msg or "food debate" in msg or "here we go again" in msg:
            return send_photo(bot, update, "gta.jpg", caption="", reply=True)

        #if "wtfock" in msg or "wtfrick" in msg:
        #    return send_sticker(bot, update, bot.get_sticker_set("Druckfamilyquotes").stickers[19], True)

        if "daddy" in msg:
            msgs = [emojize('{}, papa'), emojize("Papa :index_pointing_up:"),
                    "You need to stop using word \"daddy\", otherwise you'll become lonely. And other things will become your friends."]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)], reply=True)

        if "bjorn" in msg or "bj*rn" in msg or "björn" in msg:
            msgs = [emojize('Ugh, Bj*rn :face_vomiting:')]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])

        if "missing" in msg and "hours" in msg:
            msgs = [emojize('Agree'), "Always.", "Every hour is missing {} hour".format(msg.split("missing ")[1].split(" hours")[0])]
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)], reply=True)

        if ("rentier" in msg and not bot.name.lower() in msg) or (msg == bot.name.lower()): #exclude mention
            msgs = [emojize('Psss, want some weed?'),
                    "Someone's called me?",
                    "{}, password?",
                    "{}, listen, every person is an island.",
                    "{}, coffee?",
                    "Yeah?"]
            if update.message.from_user.id == 909049413:
                msgs.append(emojize("{}, I know you don't like me, but I like you and that's enough! :red_heart:"))
                msgs.append(emojize("Why you don't like me, {}? :disappointed_face:"))
                msgs.append("I'm here to annoy Angelika")
            return echo(bot, update, msgs[random.randint(0, len(msgs)-1)])

        if "reindeer" == msg:
            msgs = ["{}, I changed this password 3 months ago."]
            return echo(bot, update, msgs[random.randint(0, len(msgs) - 1)])

        if "superior" in msg:
            return send_sticker(bot, update, bot.get_sticker_set("water81818").stickers[10], True)

        if update.message.reply_to_message is not None:
            if update.message.reply_to_message.from_user.id == bot.id:
                if "coffee" in update.message.reply_to_message.text.lower():
                    return coffee_reply(bot, update)


def coffee_reply(bot, update):
    if "yes" in update.message.text.lower():
        return send_photo(bot, update, "rentier_coffee.jpg", "Here!", reply=True)
    if "no" in update.message.text.lower():
        return echo(bot, update, 'Okay, maybe some tea then?', reply=True)


def send_photo(bot, update, photo, caption, reply=False):
    f = join(dirname(realpath(__file__)), "resources", "photos", photo)
    if reply:
        bot.send_photo(update.message.chat.id, open(f, 'rb'), caption, reply_to_message=update.message.message_id)
    else:
        bot.send_photo(update.message.chat.id, open(f, 'rb'), caption)

def at_handler(bot, update):
    msg = update.message.text.lower()
    if bot.name.lower() in msg and "coffee" in msg:
        photo = join(dirname(realpath(__file__)), "resources", "photos", "rentier_coffee.jpg")
        return bot.send_photo(update.message.chat.id, open(photo, 'rb'), "Here!",
                       reply_to_message=update.message.message_id)

    if bot.name.lower() in msg and ("days till" in msg or "days until" in msg) and (
            "druck" in msg or "season 5" in msg):
        date_from = datetime(2020, 6, 22, 13, 0, tzinfo=timezone.utc)
        date_now = datetime.now(tz=timezone.utc)
        days = (date_from - date_now).days
        return echo(bot, update, "Days until druck: {}".format(days))

    if bot.name.lower() in msg and "shakshuka" in msg:
        photo = join(dirname(realpath(__file__)), "resources", "photos", "shakshuka.jpg")
        return bot.send_photo(update.message.chat.id, open(photo, 'rb'), "Bon Appetit!",
                              reply_to_message=update.message.message_id)

    if bot.name.lower() in msg and "sandwich" in msg:
        photo = join(dirname(realpath(__file__)), "resources", "photos", "sandwiches.jpg")
        return bot.send_photo(update.message.chat.id, open(photo, 'rb'), "Here!",
                              reply_to_message=update.message.message_id)

    if bot.name.lower() in msg and "pancake" in msg:
        photo = join(dirname(realpath(__file__)), "resources", "photos", "pancake.jpg")
        return bot.send_photo(update.message.chat.id, open(photo, 'rb'), ";)",
                              reply_to_message=update.message.message_id)

    if bot.name.lower() in msg and " cake" in msg:
        photo = join(dirname(realpath(__file__)), "resources", "photos", "cake.jpg")
        return bot.send_photo(update.message.chat.id, open(photo, 'rb'), ";)",
                              reply_to_message=update.message.message_id)

    if bot.name.lower() in msg and "muffin" in msg:
        photo = join(dirname(realpath(__file__)), "resources", "photos", "muffins.jpg")
        return bot.send_photo(update.message.chat.id, open(photo, 'rb'), ";)",
                              reply_to_message=update.message.message_id)



def echo(bot, update, msg, reply=False):
    message = update.message
    chat_id = message.chat.id

    # Replace placeholders and send message
    text = msg.format('<a href="tg://user?id={}">{}</a>'.format(
        message.from_user.id, message.from_user.first_name))
    if reply:
        send_async(bot, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_to_message_id=message.message_id)
    else:
        send_async(bot, chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


def send_sticker(bot, update, sticker, reply=False):
    message = update.message
    chat_id = message.chat.id
    #sset = bot.get_sticker_set("Druckfamilyquotes")
    if reply:
        bot.send_sticker(chat_id, sticker, reply_to_message_id=message.message_id)
    else:
        bot.send_sticker(chat_id, sticker)


def error(bot, update, error, **kwargs):
    """ Error handling """

    try:
        if isinstance(error, TelegramError)\
                and error.message == "Unauthorized"\
                or "PEER_ID_INVALID" in error.message\
                and isinstance(update, Update):

            chats = db.get('chats')
            chats.remove(update.message.chat_id)
            db.set('chats', chats)
            logger.info('Removed chat_id %s from chat list'
                        % update.message.chat_id)
        else:
            logger.error("An error (%s) occurred: %s"
                         % (type(error), error.message))
    except:
        pass


def main():
    # Create the Updater and pass it your bot's token.
    #updater = Updater(TOKEN, workers=10, request_kwargs=REQUEST_KWARGS)
    updater = Updater(TOKEN, workers=10)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", help))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler('welcome', set_welcome, pass_args=True))
    dp.add_handler(CommandHandler('goodbye', set_goodbye, pass_args=True))
    dp.add_handler(CommandHandler('disable_goodbye', disable_goodbye))
    dp.add_handler(CommandHandler('enable_goodbye', enable_goodbye))
    dp.add_handler(CommandHandler("lock", lock))
    dp.add_handler(CommandHandler("unlock", unlock))
    dp.add_handler(CommandHandler("quiet", quiet))
    dp.add_handler(CommandHandler("unquiet", unquiet))
    dp.add_handler(CommandHandler("sendtest", send_test_chat_msg))
    dp.add_handler(CommandHandler("sendfamily", send_family_chat_msg))

    dp.add_handler(MessageHandler([Filters.status_update], empty_message))
    dp.add_handler(MessageHandler(Filters.group, bis_bald))

    #dp.add_handler(MessageHandler([Filters.text], stats))

    dp.add_error_handler(error)

    update_queue = updater.start_polling(timeout=30, clean=False)

    updater.idle()

if __name__ == '__main__':
    main()
