from flask import Flask, render_template, jsonify, request
import os
import json
import re
import time
import random
import math
import unicodedata
import sqlite3
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import traceback

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from curl_cffi import requests as cr

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'news_cache.json')

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                topic2 TEXT,
                category TEXT,
                region TEXT,
                mode TEXT,
                analysis TEXT,
                score INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                error_msg TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("[DB] ✅ Tablas inicializadas (trends + api_usage)")
    except Exception as e:
        print(f"[DB] Error inicializando: {e}")

init_db()

CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '⚡', 'type': 'tema'},
    {'name': 'Automotriz', 'icon': '🚗', 'type': 'tema'},
    {'name': 'Belleza', 'icon': '💄', 'type': 'tema'},
    {'name': 'Minería', 'icon': '⛏️', 'type': 'tema'},
    {'name': 'IA', 'icon': '🤖', 'type': 'tema'},
    {'name': 'Tendencias', 'icon': '📈', 'type': 'tema'},
    {'name': 'Tecnología', 'icon': '💻', 'type': 'tema'},
    {'name': 'Economía', 'icon': '💰', 'type': 'tema'},
    {'name': 'Chile', 'icon': '🇨🇱', 'type': 'region'},
    {'name': 'Internacional', 'icon': '🌍', 'type': 'region'},
    {'name': 'Deportes', 'icon': '⚽', 'type': 'otros'},
    {'name': 'Ciencia y Tecnología', 'icon': '🔬', 'type': 'otros'},
    {'name': 'Cultura', 'icon': '🎭', 'type': 'otros'},
    {'name': 'Ocio', 'icon': '🎮', 'type': 'otros'},
    {'name': 'Salud', 'icon': '🏥', 'type': 'otros'},
    {'name': 'Sociedad', 'icon': '👥', 'type': 'otros'},
    {'name': 'TV y Espectáculos', 'icon': '📺', 'type': 'otros'}
]

SEARCH_KEYWORDS = {
    'Eléctrico': 'eléctricas OR transmisión OR distribución',
    'Automotriz': 'autos OR vehículos OR electromovilidad',
    'Belleza': 'belleza OR cosmética OR skincare',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA OR artificial intelligence',
    'Tendencias': 'tendencias OR trends',
    'Tecnología': 'tecnología OR 5G OR tech OR technology',
    'Economía': 'economía OR dólar OR inflación OR economy OR financial',
    'Chile': 'chile',
    'Internacional': 'internacional OR international OR world OR global',
    'Deportes': 'deportes OR fútbol OR sports',
    'Ciencia y Tecnología': 'ciencia OR tecnología OR science OR technology',
    'Cultura': 'cultura OR arte OR música OR cine OR teatro OR culture',
    'Ocio': 'ocio OR entretenimiento OR entertainment',
    'Salud': 'salud OR medicina OR health',
    'Sociedad': 'sociedad OR society',
    'TV y Espectáculos': 'televisión OR espectáculos OR farándula OR entertainment'
}

SOURCES_CL = {
    "biobio": {"home": "https://www.biobiochile.cl/", "domain": "biobiochile.cl"},
    "latercera": {"home": "https://www.latercera.com/", "domain": "latercera.com"},
    "cooperativa": {"home": "https://www.cooperativa.cl/", "domain": "cooperativa.cl"},
    "df": {"home": "https://www.df.cl/", "domain": "df.cl"},
    "emol": {"home": "https://www.emol.com/", "domain": "emol.com"},
    "ciper": {"home": "https://www.ciperchile.cl/", "domain": "ciperchile.cl"},
    "24horas": {"home": "https://www.24horas.cl/", "domain": "24horas.cl"},
}

SOURCES_ES = {
    "bbc_mundo": {"rss": "https://feeds.bbci.co.uk/mundo/rss.xml", "name": "BBC Mundo"},
    "elpais": {"rss": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/america/portada", "name": "El País América"},
    "cnn_es": {"rss": "https://cnnespanol.cnn.com/feed/", "name": "CNN en Español"},
    "dw_es": {"rss": "https://rss.dw.com/rdf/rss-sp-top", "name": "DW Español"},
    "france24": {"rss": "https://www.france24.com/es/rss", "name": "France 24"},
}

SOURCES_EN = {
    "reuters": {"rss": "https://feeds.reuters.com/reuters/worldNews", "name": "Reuters"},
    "guardian": {"rss": "https://www.theguardian.com/world/rss", "name": "The Guardian"},
    "aljazeera": {"rss": "https://www.aljazeera.com/xml/rss/all.xml", "name": "Al Jazeera"},
    "techcrunch": {"rss": "https://techcrunch.com/feed/", "name": "TechCrunch"},
    "ap_news": {"rss": "https://rsshub.app/apnews/topics/apf-topnews", "name": "AP News"},
}

STOPWORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this', 'es', 'son', 'como', 'pero', 'también', 'sin', 'sobre', 'entre', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'on', 'at', 'by', 'with', 'about', 'against', 'between', 'through', 'during', 'before', 'after', 'above', 'below', 'from', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'because', 'until', 'while', 'although', 'though', 'if', 'unless', 'since', 'as', 'what', 'which', 'who', 'whom', 'whose'}

def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(c))

def _get(url, retries=3, timeout=15):
    user_agent = os.getenv('USER_AGENT', 'CoraRadar/1.0 (by /u/coraradar_bot)')
    for i in range(retries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=timeout, headers={"Accept-Language": "es-CL,es;q=0.9,en;q=0.8", "User-Agent": user_agent})
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 503):
                time.sleep((2 ** i) + random.random())
                continue
            return None
        except Exception:
            time.sleep(1 + i)
    return None

def _from_homepage(name, cfg):
    html = _get(cfg["home"])
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for tag in soup.select("h1, h2, h3, h4"):
        t = " ".join(tag.get_text(" ", strip=True).split())
        if len(t) < 30 or len(t) > 150 or t in seen:
            continue
        seen.add(t)
        a = tag.find("a") or tag.find_parent("a") or tag
        out.append({'title': t, 'source': name, 'url': a.get("href", "") if a else "", 'first_seen': datetime.now(timezone.utc).isoformat()})
    return out

def _from_gnews(name, cfg):
    url = f"https://news.google.com/rss/search?q=site:{cfg['domain']}+when:1d&hl=es-419&gl=CL&ceid=CL:es-419"
    xml = _get(url)
    if not xml:
        return []
    out = []
    try:
        root = ET.fromstring(xml)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").rsplit(" - ", 1)[0].strip()
            try:
                ts = parsedate_to_datetime(it.findtext("pubDate"))
            except Exception:
                ts = datetime.now(timezone.utc)
            if title and len(title) > 30:
                out.append({'title': title, 'source': name, 'url': it.findtext("link") or "", 'first_seen': ts.isoformat()})
    except Exception:
        pass
    return out

def _from_rss(name, cfg):
    articles = []
    try:
        xml = _get(cfg["rss"])
        if not xml:
            return []
        root = ET.fromstring(xml)
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            if title and len(title) > 20:
                try:
                    ts = parsedate_to_datetime(pub_date) if pub_date else datetime.now(timezone.utc)
                except:
                    ts = datetime.now(timezone.utc)
                articles.append({
                    'title': title,
                    'source': name,
                    'url': link,
                    'first_seen': ts.isoformat()
                })
        print(f"[RSS] ✅ {cfg.get('name', name)}: {len(articles)} artículos")
    except Exception as e:
        print(f"[RSS] ❌ {cfg.get('name', name)}: {str(e)}")
    return articles[:20]

def fetch_reddit_trending():
    """Obtiene posts trending de Reddit usando RSS públicos (robusto y con pausas)"""
    articles = []
    subreddits = ['chile', 'worldnews', 'technology', 'politics', 'economy']
    user_agent = os.getenv('USER_AGENT', 'CoraRadar/1.0 (by /u/coraradar_bot)')
    
    for subreddit in subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot/.rss"
            headers = {"User-Agent": user_agent}
            
            response = cr.get(url, impersonate="chrome", timeout=15, headers=headers)
            
            if response.status_code != 200:
                print(f"[REDDIT RSS] ⚠️ r/{subreddit}: HTTP {response.status_code}")
                time.sleep(1)
                continue
            
            root = ET.fromstring(response.text)
            count = 0
            
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "")
                
                if title and len(title) > 30 and not title.startswith('[D]') and not title.startswith('[M]') and 'mod' not in title.lower():
                    articles.append({
                        'title': f"[Reddit r/{subreddit}] {title}",
                        'source': f'reddit_{subreddit}',
                        'url': link,
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True
                    })
                    count += 1
                    if count >= 8:
                        break
            
            print(f"[REDDIT RSS] ✅ r/{subreddit}: {count} posts")
            time.sleep(1.5)  # Pausa para ser amable con los servidores de Reddit
            
        except ET.ParseError as e:
            print(f"[REDDIT RSS] ⚠️ Error XML en r/{subreddit}")
            time.sleep(1)
        except Exception as e:
            print(f"[REDDIT RSS] ❌ Error en r/{subreddit}: {str(e)[:100]}")
            time.sleep(2)
    
    print(f"[REDDIT RSS] ✅ Total: {len(articles)} posts trending")
    return articles

def fetch_youtube_trending():
    """Obtiene videos trending de YouTube en Chile (categoría noticias)"""
    articles = []
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    
    if not youtube_api_key:
        print("[YOUTUBE] ⚠️ API Key no configurada")
        return []
    
    try:
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&chart=mostPopular&regionCode=CL&categoryId=25&maxResults=15&key={youtube_api_key}"
        response = cr.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get('items', [])
            
            for item in items:
                snippet = item.get('snippet', {})
                statistics = item.get('statistics', {})
                
                title = snippet.get('title', '').strip()
                channel = snippet.get('channelTitle', '')
                video_id = item.get('id', '')
                views = int(statistics.get('viewCount', 0))
                
                if title and views > 10000:
                    articles.append({
                        'title': f"[YouTube Trending 👁️{views:,}] {title}",
                        'source': 'youtube_trending',
                        'url': f"https://youtube.com/watch?v={video_id}",
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True,
                        'youtube_views': views,
                        'channel': channel
                    })
            
            print(f"[YOUTUBE] ✅ {len(articles)} videos trending en Chile")
        else:
            print(f"[YOUTUBE] ❌ Error HTTP: {response.status_code} - {response.text[:100]}")
            
    except Exception as e:
        print(f"[YOUTUBE] ❌ Error: {str(e)}")
    
    return articles

def fetch_google_trends():
    articles = []
    try:
        url = "https://trends.google.com/trending/rss?geo=CL"
        response = cr.get(url, impersonate="chrome", timeout=15, headers={"Accept-Language": "es-CL,es;q=0.9"})
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                if title and len(title) > 10:
                    articles.append({
                        'title': f"[Google Trends] {title}",
                        'source': 'google_trends',
                        'url': item.findtext("link", ""),
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True
                    })
            print(f"[TRENDS] ✅ Google Trends: {len(articles)} tendencias")
    except Exception as e:
        print(f"[TRENDS] ❌ Google Trends: {str(e)}")
    return articles

def fetch_wikipedia_trending():
    articles = []
    try:
        today = datetime.now(timezone.utc)
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/es.wikipedia/all-access/{today.year}/{today.month:02d}/{today.day:02d}"
        response = cr.get(url, impersonate="chrome", timeout=15)
        if response.status_code == 200:
            data = response.json()
            items = data.get('items', [{}])[0].get('articles', [])
            for item in items[:15]:
                title = item.get('article', '').replace('_', ' ')
                views = item.get('views', 0)
                if title and views > 1000:
                    articles.append({
                        'title': f"[Wiki Trending] {title} ({views:,} vistas)",
                        'source': 'wikipedia',
                        'url': f"https://es.wikipedia.org/wiki/{item.get('article', '')}",
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True,
                        'views': views
                    })
            print(f"[WIKI] ✅ Wikipedia: {len(articles)} artículos trending")
    except Exception as e:
        print(f"[WIKI] ❌ Wikipedia: {str(e)}")
    return articles

def get_cached_data(max_age_minutes=120):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                if datetime.now(timezone.utc) - timestamp.replace(tzinfo=timezone.utc) < timedelta(minutes=max_age_minutes):
                    return cache['articles'], cache.get('status', {})
        except Exception:
            pass
    return None, None

def save_to_cache(articles, status):
    if not articles: return
    try:
        temp_path = CACHE_FILE + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump({'articles': articles, 'status': status, 'timestamp': datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False)
        os.replace(temp_path, CACHE_FILE)
    except Exception:
        pass

def track_api_usage(endpoint, tokens_input=0, tokens_output=0, success=True, error_msg=None):
    try:
        COST_PER_1M_INPUT = 0.40
        COST_PER_1M_OUTPUT = 1.20
        cost = (tokens_input / 1_000_000 * COST_PER_1M_INPUT) + (tokens_output / 1_000_000 * COST_PER_1M_OUTPUT)
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute(
            '''INSERT INTO api_usage (endpoint, tokens_input, tokens_output, cost_usd, success, error_msg)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (endpoint, tokens_input, tokens_output, cost, 1 if success else 0, error_msg)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[TRACK] Error: {str(e)}")

def fetch_raw_articles(force_refresh=False):
    """Recolección secuencial optimizada para evitar picos de memoria (SIGKILL)"""
    if not force_refresh:
        articles, status = get_cached_data(max_age_minutes=120)
        if articles:
            return articles, status

    print("[FETCH] Iniciando recolección (modo estable)...")
    articles, status = [], {}
    
    # 1. Medios chilenos (secuencial con pausas)
    for name, cfg in SOURCES_CL.items():
        html = _get(cfg["home"])
        if html:
            arts = _from_homepage(name, cfg)
            if arts:
                articles.extend(arts)
                status[name] = "ok"
                print(f"[FETCH] {name}: {len(arts)} artículos - ok")
                time.sleep(0.5)
                continue
        
        arts = _from_gnews(name, cfg)
        articles.extend(arts)
        status[name] = "ok_fallback" if arts else "blocked_or_empty"
        print(f"[FETCH] {name}: {len(arts)} artículos - {status[name]}")
        time.sleep(0.5)
    
    # 2. Fuentes RSS en español e inglés (secuencial)
    all_rss_sources = {**SOURCES_ES, **SOURCES_EN}
    for name, cfg in all_rss_sources.items():
        arts = _from_rss(name, cfg)
        articles.extend(arts)
        status[name] = "ok" if arts else "empty"
        time.sleep(0.3)
    
    # 3. Reddit
    try:
        reddit_articles = fetch_reddit_trending()
        articles.extend(reddit_articles)
        status['reddit'] = 'ok' if reddit_articles else 'empty'
    except Exception as e:
        status['reddit'] = 'error'
        print(f"[FETCH] Reddit error: {str(e)}")
    
    # 4. YouTube
    try:
        youtube_articles = fetch_youtube_trending()
        articles.extend(youtube_articles)
        status['youtube'] = 'ok' if youtube_articles else 'empty'
    except Exception as e:
        status['youtube'] = 'error'
        print(f"[FETCH] YouTube error: {str(e)}")
    
    # 5. Google Trends
    try:
        trends_articles = fetch_google_trends()
        articles.extend(trends_articles)
        status['google_trends'] = 'ok' if trends_articles else 'empty'
    except:
        status['google_trends'] = 'error'
    
    # 6. Wikipedia
    try:
        wiki_articles = fetch_wikipedia_trending()
        articles.extend(wiki_articles)
        status['wikipedia'] = 'ok' if wiki_articles else 'empty'
    except:
        status['wikipedia'] = 'error'

    # Eliminar duplicados
    seen = set()
    unique_articles = []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            unique_articles.append(a)

    print(f"[FETCH] Total artículos únicos: {len(unique_articles)}")
    save_to_cache(unique_articles, status)
    return unique_articles, status

def group_related_articles(articles, top=8):
    if not articles: return []
    now = datetime.now(timezone.utc)
    groups = defaultdict(list)
    
    for a in articles:
        norm = _norm(a['title'])
        words = re.findall(r'[a-zñ]{4,}', norm)
        significant = [w for w in words if w not in STOPWORDS]
        if len(significant) >= 3:
            key = ' '.join(sorted(significant[:5]))
            groups[key].append(a)
    
    scored = []
    for key, items in groups.items():
        sources = set(item['source'] for item in items)
        n_articles = len(items)
        if n_articles < 2 and len(sources) < 2:
            continue
        
        avg_age = 12
        try:
            ages = []
            for item in items:
                fs = item.get('first_seen')
                if isinstance(fs, str):
                    fs = datetime.fromisoformat(fs.replace('Z', '+00:00'))
                ages.append((now - fs).total_seconds() / 3600)
            avg_age = sum(ages) / len(ages)
        except:
            pass
        
        score = (max(0, 100 - (avg_age * 5)) * 0.4) + (len(sources) * 15) + min(20, n_articles * 5)
        representative = max(items, key=lambda x: len(x['title']))
        
        scored.append({
            'topic': representative['title'],
            'score': round(min(95, score)),
            'sources': sorted(sources),
            'count': n_articles,
            'articles': items[:3]
        })
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    result, seen_topics = [], set()
    
    for s in scored:
        norm = _norm(s['topic'])
        if not any(norm in seen or seen in norm for seen in seen_topics):
            if len(result) < top:
                seen_topics.add(norm)
                result.append({
                    'topic': s['topic'],
                    'score': s['score'],
                    'category': guess_category(s['topic']),
                    'news_count': s['count'],
                    'news': [{'titulo': art['title'], 'fuente': art['source'], 'url': art.get('url', ''), 'fecha': art.get('first_seen', '')[:10]} for art in s['articles']],
                    'alert_level': 'critical' if s['score'] >= 80 else ('high' if s['score'] >= 65 else None),
                    'source': ', '.join(s['sources']),
                    'is_realtime': True,
                    'timestamp': now.isoformat()
                })
    return result

def cross_predictions_func(articles, category='all', top=6):
    if not articles or len(articles) < 3:
        return []
    
    recent = articles[:20]
    headlines = "\n".join([f"- [{a['source']}] {a['title']}" for a in recent])
    category_instruction = f"Prioriza tendencias relacionadas con: {category}." if category != 'all' else "Cubre una variedad de categorías."
    
    prompt = f"""Eres un analista de tendencias editoriales experto.
{category_instruction}
Analiza estos titulares recientes y detecta PATRONES o TEMAS EMERGENTES:
TITULARES ACTUALES:
{headlines}

Identifica {top} TENDENCIAS EMERGENTES. Formato JSON:
[
  {{
    "topic": "Tema claro y específico",
    "score": 72,
    "reasoning": "Por qué es tendencia (2-3 oraciones)",
    "signals": ["Señal 1", "Señal 2"],
    "impact": "alto",
    "timeframe": "próximas horas",
    "category": "Categoría"
  }}
]
IMPORTANTE: Varía los scores (40-85). Responde SOLO con el array JSON."""

    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return []
    
    tokens_input = len(prompt) // 4
    
    try:
        response = cr.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.4, 'max_tokens': 2000}},
            timeout=60,
            impersonate="chrome"
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('output', {}).get('choices', [{}])[0].get('message', {}).get('content') or result.get('output', {}).get('text') or str(result)
            
            tokens_output = len(text) // 4
            track_api_usage('predictions', tokens_input, tokens_output, success=True)
            
            start_idx, end_idx = text.find('['), text.rfind(']')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1].replace('```json', '').replace('```', '').strip()
                predictions = json.loads(json_str)
                
                now = datetime.now(timezone.utc)
                return [{
                    'topic': p.get('topic', ''),
                    'score': max(40, min(85, int(p.get('score', 50)))),
                    'reasoning': p.get('reasoning', ''),
                    'signals': p.get('signals', []),
                    'impact': p.get('impact', 'medio'),
                    'timeframe': p.get('timeframe', 'próximas horas'),
                    'category': p.get('category', guess_category(p.get('topic', ''))),
                    'news_count': len(p.get('signals', [])),
                    'news': [{'titulo': p.get('reasoning', ''), 'fuente': 'Análisis IA', 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                    'alert_level': 'critical' if p.get('score', 50) >= 80 else ('high' if p.get('score', 50) >= 65 else None),
                    'source': 'Predicción Cruzada IA',
                    'is_realtime': True,
                    'timestamp': now.isoformat()
                } for p in predictions[:top]]
        else:
            track_api_usage('predictions', tokens_input, 0, success=False, error_msg=f"HTTP {response.status_code}")
    except Exception as e:
        track_api_usage('predictions', tokens_input, 0, success=False, error_msg=str(e))
    return []

def guess_category(topic):
    topic_lower = str(topic).lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato', 'soccer', 'football'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre', 'financial', 'economy', 'market', 'stock'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial', 'international', 'world', 'global', 'united states', 'europe'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia', 'tech', 'technology', 'ai', 'artificial intelligence', 'startup'],
        'Salud': ['salud', 'hospital', 'médico', 'vacuna', 'health', 'medical', 'pandemic'],
        'Sociedad': ['sociedad', 'educación', 'migración', 'society', 'education', 'migration'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso', 'farándula', 'entertainment', 'celebrity'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución', 'electric', 'energy'],
        'Automotriz': ['auto', 'vehículo', 'volvo', 'automotriz', 'car', 'vehicle', 'ev'],
        'Minería': ['minería', 'cobre', 'litio', 'mina', 'mining', 'copper', 'lithium'],
        'Cultura': ['cultura', 'arte', 'música', 'cine', 'teatro', 'culture', 'art', 'music', 'film'],
        'Ciencia y Tecnología': ['ciencia', 'tecnología', 'science', 'technology', 'research', 'discovery']
    }
    for cat, words in keywords.items():
        if any(word in topic_lower for word in words):
            return cat
    return 'Tendencias'

def get_statistics(articles):
    stats = {
        'by_source': {},
        'by_category': {},
        'total_articles': len(articles),
        'sources_count': 0,
        'trends_detected': 0
    }
    
    for a in articles:
        source = a.get('source', 'desconocido')
        stats['by_source'][source] = stats['by_source'].get(source, 0) + 1
        
        cat = guess_category(a['title'])
        stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
        
        if a.get('is_trend'):
            stats['trends_detected'] += 1
    
    stats['sources_count'] = len(stats['by_source'])
    return stats

def analyze_with_qwen(prompt, mode='standard'):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return None, "QWEN_API_KEY no configurada"
    
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.1 if mode == 'briefing' else 0.7, 'max_tokens': 2000}
    }
    
    tokens_input = len(prompt) // 4
    
    try:
        response = cr.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=60,
            impersonate="chrome"
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('output', {}).get('choices', [{}])[0].get('message', {}).get('content') or result.get('output', {}).get('text') or str(result)
            
            tokens_output = len(text) // 4
            track_api_usage('analyze', tokens_input, tokens_output, success=True)
            
            match = re.search(r'\{.*\}', text, re.DOTALL)
            json_str = match.group(0) if match else text.replace('```json', '').replace('```', '').strip()
            
            return json.loads(json_str), None
        else:
            track_api_usage('analyze', tokens_input, 0, success=False, error_msg=f"HTTP {response.status_code}")
            return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        track_api_usage('analyze', tokens_input, 0, success=False, error_msg=str(e))
        return None, f"Error: {str(e)}"

def generate_analysis(topic, topic2, category, region, mode, lens, news):
    news_text = "\n\nNoticias:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    
    if mode == 'briefing':
        return f"""Eres editor experto. BRIEFING sobre: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"resumen_ejecutivo": "Párrafo claro", "preguntas_fuente": ["¿Qué pasó?", "¿Quiénes afectan?", "¿Qué sigue?"], "datos_duros": ["Dato 1", "Dato 2"], "timeline_sugerido": "Esta semana", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'devil':
        return f"""Editor crítico. ABOGADO DEL DIABLO: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"cobertura_mainstream": "Lo que todos dicen", "angulo_ciego": "Lo que NADIE pregunta", "riesgos_sesgos": ["Sesgo 1", "Sesgo 2"], "pregunta_incomoda": "Pregunta incómoda", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'compare' and topic2:
        return f"""Editor estratégico. COMPARA: TEMA A: {topic} | TEMA B: {topic2} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"tema_a": "{topic}", "tema_b": "{topic2}", "mas_recorrido": "Cuál tiene más recorrido", "fuentes_comunes": ["Fuente 1", "Fuente 2"], "angulo_conector": "Ángulo conector", "recomendacion": "Cuál cubrir primero", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    else:
        lens_instruction = {"data": "\nENFOQUE: Estadísticas.", "controversy": "\nENFOQUE: Conflictos.", "human": "\nENFOQUE: Personas.", "economic": "\nENFOQUE: Finanzas."}.get(lens, "")
        return f"""Analiza tendencia: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}{lens_instruction}
Responde SOLO JSON: {{"puntaje_relevancia": 7, "justificacion_puntaje": "Explicación del puntaje", "hipotesis": "Hipótesis editorial", "senales_clave": ["Señal 1", "Señal 2"], "angulos_periodisticos": ["Ángulo 1", "Ángulo 2"], "fuentes_sugeridas": ["Fuente 1", "Fuente 2"], "titulares_ejemplo": ["Titular 1", "Titular 2"], "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify(CATEGORIES)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 6))
    force_refresh = request.args.get('refresh') == 'true'
    articles, status = fetch_raw_articles(force_refresh=force_refresh)
    
    keywords_raw = SEARCH_KEYWORDS.get(category, 'chile')
    keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
    
    trends = []
    seen = set()
    for a in articles:
        if category == 'all' or any(kw in a['title'].lower() for kw in keywords):
            if a['title'] not in seen:
                seen.add(a['title'])
                trends.append({'topic': a['title'], 'source': a['source'], 'region': 'Chile'})
        if len(trends) >= limit:
            break
    
    return jsonify({'trends': trends, 'source_status': status})

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route():
    try:
        category = request.args.get('category', 'all')
        force_refresh = request.args.get('refresh') == 'true'
        print(f"[PREDICT] Iniciando para categoría: {category}")
        
        articles, status = fetch_raw_articles(force_refresh=force_refresh)
        if not articles:
            return jsonify({'predictions': [], 'source_status': status, 'category': category})
        
        algo_predictions = group_related_articles(articles, top=8)
        print(f"[PREDICT] Algorítmicas: {len(algo_predictions)}")
        
        cross_predictions = []
        try:
            if category != 'all':
                keywords_raw = SEARCH_KEYWORDS.get(category, category.lower())
                keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
                filtered = [a for a in articles if any(kw in a['title'].lower() for kw in keywords)]
                
                if len(filtered) >= 3:
                    cross_predictions = cross_predictions_func(filtered, category=category, top=6)
                else:
                    cross_predictions = cross_predictions_func(articles, category=category, top=6)
            else:
                cross_predictions = cross_predictions_func(articles, category='all', top=6)
            print(f"[PREDICT] Cruzadas: {len(cross_predictions)}")
        except Exception as e:
            print(f"[PREDICT] IA falló, usando algorítmicas: {str(e)}")
        
        all_predictions = cross_predictions if cross_predictions else algo_predictions
        
        seen, unique = set(), []
        for p in all_predictions:
            norm = _norm(p.get('topic', ''))
            if norm and norm not in seen:
                seen.add(norm)
                unique.append(p)
        
        unique.sort(key=lambda x: x.get('score', 0), reverse=True)
        print(f"[PREDICT] ✅ Enviando {len(unique[:8])} predicciones")
        
        return jsonify({'predictions': unique[:8], 'source_status': status, 'category': category})
        
    except Exception as e:
        print(f"[PREDICT] ERROR CRÍTICO: {str(e)}")
        traceback.print_exc()
        return jsonify({'predictions': [], 'error': str(e), 'category': request.args.get('category', 'all')}), 200

@app.route('/api/status', methods=['GET'])
def get_status():
    _, status = get_cached_data()
    return jsonify({
        'mindicador': {'dolar': 950, 'uf': 36000, 'status': 'ok'},
        'weather': {'temperature': 22, 'windspeed': 10, 'status': 'ok'},
        'apis': {'scraping': 'ok', 'sources': status or {}},
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/api/statistics', methods=['GET'])
def get_statistics_route():
    try:
        articles, status = fetch_raw_articles(force_refresh=False)
        stats = get_statistics(articles)
        
        predictions = []
        try:
            predictions = group_related_articles(articles, top=8)
        except:
            pass
        
        return jsonify({
            'stats': stats,
            'source_status': status,
            'predictions_count': len(predictions),
            'predictions_by_score': {
                'high': len([p for p in predictions if p.get('score', 0) >= 70]),
                'medium': len([p for p in predictions if 40 <= p.get('score', 0) < 70]),
                'low': len([p for p in predictions if p.get('score', 0) < 40])
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        print(f"[STATS] Error: {str(e)}")
        return jsonify({'error': str(e)}), 200

@app.route('/api/usage', methods=['GET'])
def get_usage_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM api_usage')
        total_requests = cursor.fetchone()[0]
        
        cursor.execute('SELECT success, COUNT(*) FROM api_usage GROUP BY success')
        success_stats = dict(cursor.fetchall())
        successful = success_stats.get(1, 0)
        failed = success_stats.get(0, 0)
        
        cursor.execute('SELECT SUM(tokens_input), SUM(tokens_output) FROM api_usage')
        total_input, total_output = cursor.fetchone()
        total_tokens = (total_input or 0) + (total_output or 0)
        
        cursor.execute('SELECT SUM(cost_usd) FROM api_usage')
        total_cost = cursor.fetchone()[0] or 0.0
        
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT COUNT(*), SUM(cost_usd) 
            FROM api_usage 
            WHERE DATE(created_at) = ?
        ''', (today,))
        today_requests, today_cost = cursor.fetchone()
        
        cursor.execute('''
            SELECT endpoint, COUNT(*), SUM(cost_usd) 
            FROM api_usage 
            GROUP BY endpoint
        ''')
        by_endpoint = [{'endpoint': row[0], 'count': row[1], 'cost': row[2] or 0} for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT DATE(created_at) as day, COUNT(*), SUM(cost_usd)
            FROM api_usage
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY day
            ORDER BY day
        ''')
        daily_usage = [{'day': row[0], 'requests': row[1], 'cost': row[2] or 0} for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'total_requests': total_requests,
            'successful': successful,
            'failed': failed,
            'total_tokens': total_tokens,
            'total_cost': round(total_cost, 4),
            'today_requests': today_requests or 0,
            'today_cost': round(today_cost or 0, 4),
            'by_endpoint': by_endpoint,
            'daily_usage': daily_usage,
            'success_rate': round((successful / total_requests * 100) if total_requests > 0 else 0, 1)
        })
    except Exception as e:
        print(f"[USAGE] Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        topic2 = data.get('topic2', '').strip()
        category = data.get('category')
        region = data.get('region')
        mode = data.get('mode', 'standard')
        lens = data.get('lens', '')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        print(f"\n{'='*60}\n[ANALYZE] Topic: {topic}, Mode: {mode}")
        
        articles, _ = fetch_raw_articles(force_refresh=False)
        news = []
        topic_lower = topic.lower()
        for a in articles:
            if topic_lower in a['title'].lower():
                news.append({
                    'titulo': a['title'],
                    'fuente': a['source'],
                    'url': a['url'],
                    'fecha': a.get('first_seen', '')[:10] if a.get('first_seen') else ''
                })
                if len(news) >= 5:
                    break
        
        print(f"[ANALYZE] Noticias encontradas: {len(news)}")
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        if error or not analysis:
            print(f"[ANALYZE] ⚠️ Qwen falló: {error}. Usando fallback.")
            analysis = {
                'puntaje_relevancia': 6,
                'justificacion_puntaje': f'Según {len(news)} noticias recientes.',
                'hipotesis': f'El tema "{topic}" muestra actividad mediática.',
                'senales_clave': [f'{len(news)} menciones en medios'] if news else ['Tema emergente'],
                'angulos_periodisticos': [f'Impacto de {topic}', f'Perspectivas sobre {topic}'],
                'fuentes_sugeridas': ['Expertos', 'Organismos oficiales'],
                'titulares_ejemplo': [f'Análisis: {topic}'],
                'noticias_reales': news
            }
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news
        
        score = analysis.get('puntaje_relevancia', 5)
        
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.cursor().execute(
                'INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score)
            )
            conn.commit()
            conn.close()
            print("[DB] ✅ Guardado en historial")
        except Exception as e:
            print(f"[DB] Error: {str(e)}")
        
        return jsonify({
            'topic': topic, 'topic2': topic2, 'category': category, 'region': region,
            'mode': mode, 'lens': lens, 'analysis': analysis, 'score': score,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute(
            'SELECT id, topic, topic2, category, region, mode, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?',
            (limit,)
        ).fetchall()
        conn.close()
        
        history = []
        for row in rows:
            try:
                analysis = json.loads(row[6]) if row[6] else {}
            except Exception:
                analysis = {}
            history.append({
                'id': row[0], 'topic': row[1], 'topic2': row[2], 'category': row[3],
                'region': row[4], 'mode': row[5], 'analysis': analysis,
                'score': row[7] or 0, 'created_at': row[8]
            })
        return jsonify(history)
    except Exception:
        return jsonify([])

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute('DELETE FROM trends WHERE id = ?', (analysis_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
