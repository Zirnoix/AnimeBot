# 🤖 AnimeBot

AnimeBot est un bot Discord qui vous permet de :
- 📅 Voir les prochains épisodes d’anime à venir
- ⏰ Recevoir des rappels personnalisés avant la sortie
- 📬 Recevoir un résumé quotidien des épisodes en DM
- 🧭 Consulter le planning complet de la semaine
- 🌙 Tout ça basé sur votre compte [AniList](https://anilist.co)

---

## 🛠️ Commandes disponibles

```
!prochains [all/10/5/...]
!next
!planning
!aujourdhui
!reminder [on/off]
!setalert <minutes>
!journalier [on/off]
!setchannel
!help
```

---

## 🚀 Déploiement Railway

1. Publiez ce dépôt sur GitHub
2. Allez sur [https://railway.app](https://railway.app)
3. Cliquez sur `New Project > Deploy from GitHub repo`
4. Ajoutez ces variables dans l'onglet `Variables` :
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_CHANNEL_ID`
   - `ANILIST_USERNAME`
5. Le bot se lancera automatiquement !

---

Développé avec ❤️ par [Zirnoixdcoco]
