# Adi Reaction Bot — continuous worker

Branch: `adi-reaction-bot-24x7` · Folder: `reaction-bot`

Deploy hone ke baad bot continuously online rehta hai aur har NEW channel post automatically detect karta hai. Har message par manually Run dabana zaroori nahi.

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

Runtime command `python -u bot.py` hai. Worker mein 60-minute cutoff nahi hai. Host ko active rehna hoga. Pehla reaction original script ke hisaab se **60 seconds** baad attempt hota hai; phir **120 seconds** gap, multiple active posts par **30 seconds**.

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
- Channel access wale bots weighted random emoji react karte hain: ❤️ 🔥 👍 🏆 💯. Sirf allowed emojis select hote hain.
- Ek running instance rakho. Same listener token doosre polling bot ya manual test mein simultaneously mat chalao.
- Existing webhook automatically remove nahi hota. Dedicated listener token use karo.
- Telegram rate limits respect hote hain; bounded retries aur network reconnect included hain.
- In-memory duplicate/album filtering included hai. 100 simultaneous posts tak schedule hote hain.
- Restart/downtime mein missed posts ya pending reactions automatically resume nahi hote. Host uptime aur delivery guarantee nahi hai.
- Automated reactions actual members ka feedback ya independent endorsement nahi hain.

## Updates

Render auto-deploy initially off hai. Long-polling bots ke old/new instances rolling deployments mein overlap kar sakte hain; update ke waqt old worker stop/suspend karke new version start karo. Docker Compose use karte waqt ek hi service instance rakho.

## GitHub checks

`.github/workflows/adi-reactions-check.yml` offline tests aur container build run karta hai. Isme Telegram tokens nahi jaate. GitHub Actions continuous hosting nahi hai; GitHub-hosted job maximum 6 hours ka hota hai.

Old uploaded tokens source mein include nahi kiye gaye. BotFather mein exposed tokens revoke/regenerate karke NEW values sirf host secrets mein daalo. Code upload se bot live nahi hota: channel, tokens aur hosting activate karna zaroori hai.

## Official references

- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [Render background workers](https://render.com/docs/background-workers)
- [Render Blueprint configuration](https://render.com/docs/blueprint-spec)
- [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/)
