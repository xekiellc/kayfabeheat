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
                if title and title not in seen_titles and "[Removed]" not in title:
                    seen_titles.add(title)
                    articles.append({
                        "title": title,
                        "description": a.get("description", ""),
                        "url": a.get("url", "#"),
                        "source": a.get("source", {}).get("name", ""),
                        "publishedAt": a.get("publishedAt", ""),
                    })
        except Exception as e:
            print(f"Error fetching {query}: {e}")
    return articles[:20]

def classify_pillar(title, description):
    text = (title + " " + description).lower()
    shoot_words = ["contract", "backstage", "sign", "release", "creative", "ratings", "attendance", "budget", "lawsuit", "fired", "hired", "deal", "salary", "tv deal", "business"]
    heat_words = ["reaction", "crowd", "fans", "chant", "viral", "twitter", "reddit", "social media", "response", "angry", "heat", "pop", "boo"]
    for w in shoot_words:
        if w in text:
            return "Shoot"
    for w in heat_words:
        if w in text:
            return "Heat"
    return "Work"

def score_heat(title, description):
    text = (title + " " + description).lower()
    score = 50
    hot_words = ["shock", "surprise", "return", "debut", "title", "champion", "heel turn", "fired", "lawsuit", "injury", "retirement", "viral", "boo", "chant", "sellout", "record"]
    for w in hot_words:
        if w in text:
            score += 8
    return min(score, 99)

def curate_with_claude(articles):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    articles_text = "\n\n".join([
        f"Title: {a['title']}\nSource: {a['source']}\nDescription: {a['description']}\nURL: {a['url']}"
        for a in articles
    ])
    prompt = f"""You are the editor of KayfabeHeat.com, a pro wrestling news site with three content pillars: Work (in-ring product), Shoot (backstage/business), and Heat (fan reaction/culture).

Here are today's wrestling news articles:

{articles_text}

Select the 6 best articles for the site. For each selected article write:
- A punchy, bold headline in the style of a wrestling dirt sheet (max 12 words)
- A 1-sentence excerpt (max 25 words, no fluff)
- Assign a pillar: Work, Shoot, or Heat
- Assign a heat score 1-99 (how hot/controversial this story is)
- The original URL
- The source name

Respond ONLY as valid JSON array like this:
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
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    import json
    return json.loads(raw)

def build_cards(curated):
    cards_html = ""
    for i, a in enumerate(curated[:6]):
        pillar = a.get("pillar", "Work")
        heat = a.get("heat", 60)
        headline = a.get("headline", "")
        excerpt = a.get("excerpt", "")
        url = a.get("url", "#")
        source = a.get("source", "")
        now = datetime.utcnow().strftime("%b %d, %Y")

        cards_html += f"""
      <div class="kf-card">
        <div class="kf-card-top">
          <div class="kf-card-tags">
            <span class="kf-tag">{pillar}</span>
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
            "deck": "Check back soon for the latest.",
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
        "hed": top.get("headline", ""),
        "deck": top.get("excerpt", ""),
        "url": top.get("url", "#"),
        "heat": str(heat),
        "heatsub": heatsub
    }

def build_ticker(curated):
    items = ""
    for a in curated[:5]:
        pillar = a.get("pillar", "Work")
        hed = a.get("headline", "")[:60]
        items += f'<span class="kf-ticker-item"><strong>{pillar}</strong> — {hed} &nbsp;·&nbsp; </span>\n      '
    return items * 2

def update_html(cards_html, hero, ticker_html, now_str):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Update article feed
    html = re.sub(
        r'(<div class="kf-center" id="article-feed">)(.*?)(</div>\s*</div>\s*<!-- end 3col -->)',
        lambda m: m.group(1) + "\n" + cards_html + "\n    " + m.group(3),
        html, flags=re.DOTALL
    )

    # Update hero
    html = re.sub(r'(<div class="kf-hero-kicker">)[^<]*(</div>)', f'\\g<1>{hero["kicker"]}\\g<2>', html)
    html = re.sub(r'(<div class="kf-hero-hed"[^>]*>)[^<]*(</div>)', f'\\g<1>{hero["hed"]}\\g<2>', html)
    html = re.sub(r'(<div class="kf-hero-deck"[^>]*>)[^<]*(</div>)', f'\\g<1>{hero["deck"]}\\g<2>', html)
    html = re.sub(r'(<span class="kf-heat-badge-num">)[^<]*(</span>)', f'\\g<1>{hero["heat"]}°\\g<2>', html)
    html = re.sub(r'(<span class="kf-heat-badge-sub">)[^<]*(</span>)', f'\\g<1>{hero["heatsub"]}\\g<2>', html)

    # Update ticker
    html = re.sub(
        r'(<div class="kf-ticker-scroll">)(.*?)(</div>\s*</div>\s*<!-- HERO -->)',
        lambda m: m.group(1) + "\n      " + ticker_html + "\n    " + m.group(3),
        html, flags=re.DOTALL
    )

    # Update last updated
    html = re.sub(
        r"(kayfabeheat\.com · Last updated: )([^<'\"]*)",
        f"\\g<1>{now_str}",
        html
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html updated successfully.")

def main():
    print("Fetching articles...")
    articles = fetch_articles()
    print(f"Fetched {len(articles)} articles.")

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
