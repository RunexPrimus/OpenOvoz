#!/bin/bash

# Railway da botni ishga tushirish
echo "Botopne bot ishga tushirilmoqda..."

# Muhit o'zgaruvchilarini tekshirish
if [ -z "$BOT_TOKEN" ]; then
    echo "Xato: BOT_TOKEN topilmadi!"
    exit 1
fi

# Botni ishga tushirish
python bot.py
