# Briefings

Stay informed with **Briefings** — AI-generated audio and text summaries of
your news corpus. News Dashboard offers two main briefing features:

1. **Current-Day Report** — a text summary of today's news (read in-app)
2. **Scheduled delivery** — automatic delivery of the briefing at a time you
   choose (in-app notification, optional email, and podcast audio)

## The Current-Day Report

The **Current-Day Report** is a textual summary that answers: *"What
happened today in my subscribed sources?"* It appears at the top of your app
and can be played as audio.

### What it includes

The report summarizes **all articles discovered today**, regardless of your
Workflow State. It pulls from:

- Articles ingested today (midnight to midnight in your server's timezone)
- All sources you have enabled
- All article kinds (RSS, GitHub releases, trending, scraped)

For each article, the report includes:
- A one-sentence **reason** (why this article surfaced)
- The article title
- The source name
- Optional: a relevance score if personalized recommendations are active

### How it's generated

Each day, after the overnight ingestion run:
1. The app collects all articles with a `discovered_at` timestamp today
2. For each article, it runs `make_reason()` to generate a contextual blurb:
   - Release feeds → "New release vX.Y.Z from source."
   - Security content → "Security update from source — review recommended."
   - Tutorial/how-to → "How-to or deep-dive on category from source."
   - Trending (HN) → "Trending on Hacker News."
   - Trending (GitHub) → "Trending {Language} repository on GitHub today."
   - AI/agent content → "AI/agent development news from source."
   - Python content → "Python ecosystem update from source."
   - Fallback → "{Category} — {Source}."
3. These reason lines are combined into a readable paragraph, ordered by
   importance score (combination of source priority, recency, and kind)
4. The result is stored as today's briefing and served at `/api/briefings/today`

You can view the Current-Day Report:
- At the top of the app homepage
- Via the "Briefings" tab in the navigation
- By clicking the speaker icon to hear it read aloud (uses your browser's
  built-in TTS or optional external TTS if configured)

### Audio playback

Tap the **Play** button next to the Current-Day Report to hear it read
aloud. This uses:
- Your browser's built-in SpeechSynthesis API (no extra setup)
- Optional: if you've configured `OPENAI_API_KEY` for TTS, it uses
  OpenAI's audio generation for higher-quality narration
- Controls: play/pause, skip forward/back 10 seconds, speed adjustment

## Scheduled delivery

Want the briefing delivered to you automatically? Set up **scheduled
delivery** to get a notification (and optionally email) when today's briefing
is ready.

### How to enable

1. Go to Settings → Notifications
2. Toggle **"Enable daily briefing notification"**
3. Choose your preferred delivery time (in your local timezone)
4. Optionally enable:
   - **Email delivery** — receive the briefing text via email
   - **Push notifications** — get a banner/alert on your device
5. Save your preferences

### What you get

At your chosen time each day:
- An **in-app notification** appears (tap to open the briefing)
- If email is enabled — you receive an email with:
  - The full Current-Day Report text
  - Links to open the article list for today
  - A "Mark all as read" button (optional)
- If push notifications are enabled — you get a system-level alert
- The briefing is marked as "delivered" in your history

### How it works behind the scenes

The scheduler runs a lightweight job at your specified time:
1. Checks if today's briefing has been generated (triggers generation if not)
2. Sends a push notification via your device's service worker (if subscribed)
3. Sends an email via SMTP (if `SMTP_*` settings are configured)
4. Records the delivery in your briefings history

## Podcast audio (optional)

Want to listen to your briefing in a podcast app? Enable **podcast audio**
to generate an MP3 file each day that you can subscribe to in any podcast
player.

### How to enable

1. Go to Settings → Advanced
2. Toggle **"Enable briefing podcast"**
3. Save — the system will generate an MP3 after each successful briefing
   generation
4. Copy your personal podcast feed URL from Settings → Podcast
5. Add that URL to your favorite podcast app (Overcast, Pocket Casts,
   Apple Podcasts, etc.)

### What you get

Each day, after the briefing is generated:
- An MP3 file is created using your configured TTS engine:
  - Browser TTS → not applicable (podcast requires server-side)
  - OpenAI TTS → high-quality narration (requires `OPENAI_API_KEY`)
  - gTTS / eSpeak → free robotic voice (no API key needed)
- The MP3 is stored locally and served at:
  `/api/briefings/podcast.rss` (a personalized, token-secured RSS feed)
- Your feed URL includes a revocable token for security:
  `https://your.instance/api/briefings/podcast.rss?token=abc123`

### Privacy

- The podcast feed is **private and unguessable** — contains a unique token
- Only you (or anyone you share the URL with) can access it
- No audio leaves your server unless you explicitly enable the feature
- Tokens can be regenerated or revoked from Settings → Podcast

## Managing your briefing history

View past briefings in the **Briefings** tab:
- Lists all generated briefings (today, yesterday, last week, etc.)
- Shows generation time and duration
- Lets you re-read or re-listen to any past briefing
- Includes a "Regenerate audio" button if you change TTS settings
- Shows delivery status (whether notification/email/podcast was sent)

## Customizing the briefing

While the core algorithm is fixed, you can influence what appears:

### Via source management
- Disable noisy sources to reduce clutter
- Prioritize high-signal sources in Sources → Edit → Priority
- Remove sources you don't care about entirely

### Via noise filtering (built-in)
The app automatically caps noisy feeds:
- Broad feeds (HN, GitHub trending): 15–20 items per run
- Newsletter feeds (Import AI, Latent Space): 5 per run
- Curated blog feeds: 50 per run

### Via TTS engine
Choose your text-to-speech engine in Settings → Advanced:
- **Browser** — free, uses your device's voice (for in-app playback only)
- **OpenAI** — highest quality, requires API key
- **gTTS** — free, Google-backed, requires internet
- **eSpeak** — free, fully offline, robotic voice
- **None** — disables audio generation

## Troubleshooting

### No briefing showing?
- Check that ingestion has run recently (Sources → Last checked)
- Verify today's date matches the server's timezone
- Look in the Briefings tab — if today's is missing, try "Generate now"

### Audio not playing?
- For in-app: ensure browser allows audio (check site permissions)
- For podcast: verify your podcast app can fetch the URL (test in browser)
- For OpenAI TTS: confirm `OPENAI_API_KEY` is set and has credit

### Not getting notifications?
- Check Settings → Notifications
- Ensure browser notification permission is granted
- For email: verify SMTP settings and that `DAILY_BRIEFING_EMAIL=true`

## Privacy

Briefings are private to your account:
- Generated only from your source subscriptions
- Stored only in your database
- Never shared unless you explicitly export or share the audio file
- The podcast feed uses a secret token — treat it like a password
