"""Posts new videos from a YouTube channel to a Telegram group.

python bot.py test   -> DM the latest video to you (not the group), then exit
python bot.py        -> watch the channel, post NEW videos to the group
"""
import html, json, os, re, sys, time
import urllib.error, urllib.request
import xml.etree.ElementTree as ET

D = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(D, ".env")):  # local only; on GitHub these come from secrets
    for line in open(os.path.join(D, ".env")):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

TOKEN = os.environ["BOT_TOKEN"]
GROUP = os.environ.get("GROUP", "@engicommunity")
CHANNEL = os.environ["YT_CHANNEL"]  # "UC..." channel id, or "@handle"
SEEN = os.path.join(D, "seen.json")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode()


def api(method, **p):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        json.dumps(p).encode(), {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        return json.load(e)


def channel_id():
    if CHANNEL.startswith("UC"):
        return CHANNEL
    page = fetch("https://www.youtube.com/" + CHANNEL.lstrip("/"))
    return re.search(r'channel/(UC[\w-]{22})', page).group(1)


CID = channel_id()


def latest():
    ns = {"a": "http://www.w3.org/2005/Atom", "y": "http://www.youtube.com/xml/schemas/2015"}
    root = ET.fromstring(fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={CID}"))
    return [(e.find("y:videoId", ns).text, e.find("a:title", ns).text)
            for e in root.findall("a:entry", ns)]  # newest first


def post(chat, vid, title):
    url = f"https://youtu.be/{vid}"
    caption = f"🎬 <b>{html.escape(title)}</b>\n\n▶️ Watch now: {url}"
    button = {"inline_keyboard": [[{"text": "▶️ Watch on YouTube", "url": url}]]}
    for quality in ("maxresdefault", "hqdefault"):  # maxres doesn't exist for every video
        r = api("sendPhoto", chat_id=chat, photo=f"https://i.ytimg.com/vi/{vid}/{quality}.jpg",
                caption=caption, parse_mode="HTML", reply_markup=button)
        if r["ok"]:
            return
    sys.exit(f"Telegram error: {r}")


def my_chat():
    if os.environ.get("TEST_CHAT_ID"):
        return os.environ["TEST_CHAT_ID"]
    msgs = [u["message"] for u in api("getUpdates")["result"] if "message" in u]
    if not msgs:
        sys.exit("Open your bot in Telegram, press Start, then run this again.")
    return msgs[-1]["chat"]["id"]


def save(seen):
    json.dump(seen, open(SEEN, "w"))


if sys.argv[1:] == ["test"]:
    post(my_chat(), *latest()[0])
    print("Sent to you. Check Telegram.")
    sys.exit()

# First run: mark existing videos as seen so old ones aren't announced.
seen = json.load(open(SEEN)) if os.path.exists(SEEN) else [v for v, _ in latest()]
save(seen)


def check():
    for vid, title in reversed(latest()):
        if vid not in seen:
            post(GROUP, vid, title)
            seen.append(vid)
            save(seen)
            print("Posted:", title)


if sys.argv[1:] == ["once"]:  # used by GitHub Actions: one check, then exit
    check()
    sys.exit()

print("Watching for new videos...")
while True:
    try:
        check()
    except Exception as e:  # network blip, YouTube hiccup: retry next round
        print("retry:", e)
    time.sleep(300)
