#!/bin/bash

# 🧠 Ajoute le dossier bin/ (où se trouve ffmpeg) dans le PATH
export PATH=$PATH:/opt/render/project/src/bin

# 🟢 Lancer le bot Discord
python bot.py
