import os
import re
import requests
import anthropic
from datetime import datetime

NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_KEY"]

QUERIES = [
    "WWE wrestling",
    "AEW wrestling",
    "pro wrestling",
    "indie wrestling",
    "NJPW wrestling",
    "TNA wrestling",
    "ROH wrestling",
    "professional wrestling news",
    "wrestling podcast",
    "wrestling video",
]

def fetch_articles():
    articles = []
    seen_titles = set()
    for query in QUERIES:
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "apiKey": NEWSAPI_KEY,
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            for a in data.get("articles", []):
                title = a.get("title", "")
                description = a.get("description", "") or ""
                if not title or "[Removed]" in title:
                    continue
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                articles.append({
                    "title": title,
                    "description": description,
                    "url": a.get("url", "#"),
                    "source": a.get("source", {}).get("name", ""),
                    "publishedAt": a.get("publishedAt", ""),
                })
        except Exception as e:
            print(f"Error fetching {query}: {e}")
    return articles[:30]

def clean_text(text):
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+', '', text)
    text = re.sub(r'`+', '', text)
    text = text.strip()
    return text

def detect_promotion(title, description):
    text = (title + " " + description).lower()
    if "wwe" in text or "raw" in text or "smackdown" in text or "wrestlemania" in text or "nxt" in text:
        return "WWE"
    if "aew" in text or "dynamite" in text or "collision" in text or "all in" in text or "all elite" in text:
        return "AEW"
    if "njpw" in text or "new japan" in text or "dominion" in text:
        return "NJPW"
    if "tna" in text or "impact" in text:
        return "TNA"
    if "roh" in text or "ring of honor" in text:
        return "ROH"
    if "nwa" in text:
        return "NWA"
    if "gcw" in text or "game changer" in text:
        return "GCW"
    if "stardom" in text:
        return "Stardom"
    if "cmll" in text or "lucha" in text or "aaa" in text:
        return "Lucha"
    return "Indies"

def curate_with_claude(articles):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    articles_text = "\n\n".join([
        f"Title: {a['title']}\nSource: {a['source']}\nDescription: {a['description']}\nURL: {a['url']}"
        for a in articles
    ])
    prompt = f"""You are the editor of KayfabeHeat.com, a pro wrestling news site with three content pillars:
- Work: in-ring product, match results, card previews, workrate, match quality
- Shoot: backstage news, contracts, creative decisions, business, ratings, money
- Heat: fan reaction, crowd response, social media buzz, viral moments, controversy

Here are today's wrestling news articles:

{articles_text}

Select the 12 best and most interesting articles covering a variety of promotions and topics. For each write:
- A punchy bold headline in dirt sheet style (max 12 words, NO asterisks, NO markdown formatting)
- A 1-sentence excerpt (max 25 words, no fluff, NO asterisks, NO markdown)
- Pillar: Work, Shoot, or Heat
- Heat score 1-99 (how hot or significant this story is)
- The original URL
- The source name

IMPORTANT: Do not use any markdown formatting like ** or * or # in headlines or excerpts. Plain text only.

Respond ONLY as a valid JSON array:
[
  {{
    "headline": "...",
    "excerpt": "...",
    "pillar": "Work",
    "heat": 84,
    "url": "...",
    "source": "..."
  }}
]

No preamble, no markdown, just the JSON array."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    import json
    curated = json.loads(raw)
    for a in curated:
        a["headline"] = clean_text(a.get("headline", ""))
        a["excerpt"] = clean_text(a.get("excerpt", ""))
    return curated

def build_cards(curated):
    cards_html = ""
    for a in curated:
        pillar = a.get("pillar", "Work")
        heat = a.get("heat", 60)
        headline = a.get("headline", "")
        excerpt = a.get("excerpt", "")
        url = a.get("url", "#")
        source = a.get("source", "")
        now = datetime.utcnow().strftime("%b %d, %Y")
        promo = detect_promotion(headline, excerpt)

        cards_html += f"""
      <div class="kf-card" data-pillar="{pillar}" data-promo="{promo}">
        <div class="kf-card-top">
          <div class="kf-card-tags">
            <span class="kf-tag">{pillar}</span>
            <span class="kf-tag kf-tag-promo">{promo}</span>
            <span class="kf-tag kf-tag-heat">🔥 {heat}°</span>
          </div>
          <div class="kf-card-hed">{headline}</div>
          <div class="kf-card-excerpt">{excerpt}</div>
        </div>
        <div class="kf-card-bottom">
          <div class="kf-card-meta">{source} · {now}</div>
          <a href="{url}" target="_blank" rel="noopener" class="kf-card-read">Read →</a>
        </div>
      </div>"""
    return cards_html

def build_hero(curated):
    if not curated:
        return {
            "kicker": "Top Story · Pro Wrestling",
            "hed": "Loading today's top story...",
            "deck": "Check back soon for the latest wrestling news.",
            "url": "#",
            "heat": "50",
            "heatsub": "Warming Up"
        }
    top = curated[0]
    heat = top.get("heat", 70)
    if heat >= 90:
        heatsub = "Scorching"
    elif heat >= 75:
        heatsub = "Blazing"
    elif heat >= 60:
        heatsub = "Hot"
    else:
        heatsub = "Warming Up"
    return {
        "kicker": f"Top Story · {top.get('pillar', 'Work')}",
        "hed": clean_text(top.get("headline", "")),
        "deck": clean_text(top.get("excerpt", "")),
        "url": top.get("url", "#"),
        "heat": str(heat),
        "heatsub": heatsub
    }

def build_ticker(curated):
    items = ""
    for a in curated[:6]:
        pillar = a.get("pillar", "Work")
        hed = clean_text(a.get("headline", ""))[:60]
        items += f'<span class="kf-ticker-item"><strong>{pillar}</strong> — {hed} &nbsp;·&nbsp; </span>\n      '
    return items * 2

def update_html(cards_html, hero, ticker_html, now_str):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Update article feed
    html = re.sub(
        r'(<div class="kf-center" id="article-feed">)(.*?)(</div>)(\s*\n\s*\n\s*  </div>)',
        lambda m: m.group(1) + "\n" + cards_html + "\n    " + m.group(3) + m.group(4),
        html, flags=re.DOTALL, count=1
    )

    # Update hero kicker
    html = re.sub(
        r'(<div class="kf-hero-kicker">)(.*?)(</div>)',
        lambda m: m.group(1) + hero["kicker"] + m.group(3),
        html, flags=re.DOTALL, count=1
    )

    # Update hero headline
    html = re.sub(
        r'(<div class="kf-hero-hed"[^>]*>)(.*?)(</div>)',
        lambda m: m.group(1) + hero["hed"] + m.group(3),
        html, flags=re.DOTALL, count=1
    )

    # Update hero deck
    html = re.sub(
        r'(<div class="kf-hero-deck"[^>]*>)(.*?)(</div>)',
        lambda m: m.group(1) + hero["deck"] + m.group(3),
        html, flags=re.DOTALL, count=1
    )

    # Update heat badge number
    html = re.sub(
        r'(<span class="kf-heat-badge-num"[^>]*>)(.*?)(</span>)',
        lambda m: m.group(1) + hero["heat"] + "°" + m.group(3),
        html, flags=re.DOTALL, count=1
    )

    # Update heat badge sub
    html = re.sub(
        r'(<span class="kf-heat-badge-sub"[^>]*>)(.*?)(</span>)',
        lambda m: m.group(1) + hero["heatsub"] + m.group(3),
        html, flags=re.DOTALL, count=1
    )

    # Update ticker
    html = re.sub(
        r'(<div class="kf-ticker-scroll"[^>]*>)(.*?)(</div>)',
        lambda m: m.group(1) + "\n      " + ticker_html + "\n    " + m.group(3),
        html, flags=re.DOTALL, count=1
    )

    # Update last updated — replace the entire meta line content
    html = re.sub(
        r'kayfabeheat\.com · Last updated:[^<"\']*',
        f"kayfabeheat.com · Last updated: {now_str}",
        html
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html updated successfully.")

def main():
    print("Fetching articles...")
    articles = fetch_articles()
    print(f"Fetched {len(articles)} articles.")

    if not articles:
        print("No articles fetched. Exiting.")
        return

    print("Curating with Claude...")
    curated = curate_with_claude(articles)
    print(f"Curated {len(curated)} articles.")

    cards_html = build_cards(curated)
    hero = build_hero(curated)
    now_str = datetime.utcnow().strftime("%A, %B %d, %Y at %H:%M UTC")
    ticker_html = build_ticker(curated)

    update_html(cards_html, hero, ticker_html, now_str)

if __name__ == "__main__":
    main()
