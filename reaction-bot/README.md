# Adi Reaction Bot — continuous worker

Branch: `adi-reaction-bot-24x7` · Folder: `reaction-bot`

Bot running ho to configured channel ki har nayi post automatically detect hoti hai: text, photo, video, document, sticker aur doosre channel posts. Har post par manually Run dabana zaroori nahi. Edited posts aur Telegram ke available pending updates bhi detect hote hain.

## Start on Render

1. Render par **New → Blueprint** se `adityayadav595-ship-it/Andy` select karo.
2. Branch **adi-reaction-bot-24x7** aur Blueprint Path **render-reactions.yaml** select karo. Repo ka existing `render.yaml` doosre app ka hai.
3. Prompt par ye environment secrets fill karo:

| Name | Value |
| --- | --- |
| `BOT_TOKENS` | NEW bot tokens; one token per line, quotes/brackets ke bina. |
| `TARGET_CHANNEL_IDS` | Apne NEW channel ka `@username` ya negative numeric ID. Multiple targets alag lines par. |

4. **Paid worker ka current price review** karke deploy karo. GitHub connection se hosting purchase nahi hoti. GitHub Secrets automatically Render mein transfer nahi hote.
5. Bots ko target channel mein add karo; reactions enable rakho. Logs mein `READY` ke baad naya post publish karo.

Runtime command `python -u bot.py` hai. Worker mein 60-minute cutoff nahi hai. Host ko active rehna hoga. Har nayi post par pehla reaction **10 seconds** baad attempt hota hai; phir usi post par har agle bot ka reaction **10 seconds** ke gap par, chahe ek post active ho ya multiple. Telegram rate-limit cooldown aaye to uska wait alag se follow hota hai.

## Start on your Docker server

Repo ki isi branch ko clone/download karke `reaction-bot` folder open karo. `.env.example` ko `.env` ke naam se copy karo aur new values bharo. Compose ke liye multiple tokens ek line par commas se separate karo. Completed `.env` file commit mat karo.

```bash
cd reaction-bot
docker compose build
docker compose run --rm bot python bot.py --check-config
docker compose up -d
docker compose logs -f --tail=50 bot
```

`restart: unless-stopped` unexpected process exit aur Docker restart ke baad restart policy deta hai, successful initial startup ke baad. Server aur Docker online rehne chahiye; Docker ko reboot par start hone do. Manual stop ke liye `docker compose stop`.

Tokens badalne ke baad `.env` save karke `docker compose up -d --force-recreate` run karo. Code update ke baad `docker compose up -d --build`.

## Working behavior

- Pehla valid bot channel-post listener banta hai; us bot ko har target channel mein hona chahiye.
- Positive reaction pool: ❤ 🔥 👍 🥰 👏 😁 🎉 🤩 🙏 👌 🕊 😍 ❤‍🔥 💯 ⚡ 🏆 🍾 💋 😇 🤝 🤗 🫡 🆒 💘 😘 😎. Sirf channel mein enabled positive emojis use hote hain.
- Emoji rotation har enabled positive emoji ko use karne ke baad naya cycle shuru karti hai. Ek se zyada emoji enabled ho to consecutive picks same nahi hote. Heart ke Unicode presentation formats normalize hote hain.
- Agar sirf 💯 aa raha ho to Telegram mein Channel → Edit → Reactions par aur positive emojis enable karo, phir bot restart karo. Startup logs enabled emojis dikhate hain. Bot code channel ki reaction settings change nahi karta.
- Ek running instance rakho. Same listener token doosre polling bot ya manual test mein simultaneously mat chalao.
- Existing webhook automatically remove nahi hota. Dedicated listener token use karo.
- Telegram rate limits respect hote hain; bounded retries aur network reconnect included hain.
- In-memory duplicate/album filtering included hai: same post ki edit ya album ke doosre item par duplicate sequence nahi banta. 100 active posts par polling capacity ka wait karti hai; next post silently discard nahi hota.
- Restart par Telegram mein bache unconfirmed updates automatically process hote hain; Telegram unhe maximum 24 hours rakhta hai. Yeh poori channel history fetch nahi karta. Pehle acknowledge ho chuki posts ki unfinished reactions restart par resume nahi hoti, aur duplicate memory process ke andar hi rehti hai. Host uptime aur delivery guarantee nahi hai.
- Automated reactions actual members ka feedback ya independent endorsement nahi hain.

## Updates

Render auto-deploy initially off hai. Long-polling bots ke old/new instances rolling deployments mein overlap kar sakte hain; update ke waqt old worker stop/suspend karke new version start karo. Docker Compose use karte waqt ek hi service instance rakho.

## GitHub checks

`.github/workflows/adi-reactions-check.yml` offline tests aur container build run karta hai. Isme Telegram tokens nahi jaate. GitHub Actions continuous hosting nahi hai; GitHub-hosted job maximum 6 hours ka hota hai.

Manual test: repository Actions → **Run Adi bot - 60 minute test** → **Run workflow**, branch **main**. Latest code lene ke liye naya Run workflow use karo. Koi purana listener run active ho to pehle Cancel workflow karke uske stop hone ka wait karo. Test running ho tab posts automatically detect hongi; test 60 minutes baad band hota hai.

Old uploaded tokens source mein include nahi kiye gaye. BotFather mein exposed tokens revoke/regenerate karke NEW values sirf host secrets mein daalo. Code upload se bot live nahi hota: channel, tokens aur hosting activate karna zaroori hai.

## Official references

- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [Render background workers](https://render.com/docs/background-workers)
- [Render Blueprint configuration](https://render.com/docs/blueprint-spec)
- [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/)
- [Telegram updates and retention](https://core.telegram.org/bots/api#getting-updates)
- [Telegram reaction emojis](https://core.telegram.org/bots/api#reactiontypeemoji)
