import telebot
import requests
import time
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Բարև! Ես աշխատում եմ Railway-ում 🚀")

while True:
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print("Bot error:", e)
        time.sleep(5)
