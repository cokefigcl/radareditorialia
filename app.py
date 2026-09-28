from flask import Flask, render_template, jsonify, request
import os
import json
import re
import time
import random
import math
import unicodedata
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from curl_cffi import requests as cr

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'news_cache.json')

CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '', 'type': 'tema'},
    {'name': 'Automotriz', 'icon': '', 'type': 'tema'},
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
    'Belleza': 'belleza OR cosmética',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias',
    'Tecnología': 'tecnología OR 5G',
    'Economía': 'economía OR dólar OR inflación',
    'Chile': 'chile',
    'Internacional': 'internacional',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Ocio': 'ocio OR entretenimiento',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos'
}

SOURCES = {
    "biobio": {"home": "https://www.biobiochile.cl/", "domain": "biobiochile.cl"},
    "latercera": {"home": "https://www.latercera.com/", "domain": "latercera.com"},
    "cooperativa": {"home": "https://www.cooperativa.cl/", "domain": "cooperativa.cl"},
    "df": {"home": "https://www.df.cl/", "domain": "df.cl"},
}

STOPWORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this', 'es', 'son', 'como', 'pero', 'también', 'sin', 'sobre', 'entre'}

TOKEN_RE = re.compile(r"[a-zñ0-9]+")
ENTITY_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})+\b")

def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))

def _get(url: str, retries: int = 3, timeout: int = 10) -> str | None:
    for i in range(retries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=timeout,
                       headers={"Accept-Language": "es-CL,es;q=0.9"})
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 503):
                time.sleep((2 ** i) + random.random())
                continue
            return None
        except Exception:
            time.sleep(1 + i)
    return None

def _from_homepage(name: str, cfg: dict):
    html = _get(cfg["home"])
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for tag in soup.select("h2, h3"):
        t = " ".join(tag.get_text(" ", strip=True).split())
        if len(t) < 25 or t in seen:
            continue
        seen.add(t)
        a = tag.find("a") or tag.find_parent("a")
        out.append({
            'title': t,
            'source': name,
            'url': a.get("href", "") if a else "",
            'first_seen': datetime.now(timezone.utc)
        })
    return out

def _from_gnews(name: str, cfg: dict):
    url = (f"https://news.google.com/rss/search?q=site:{cfg['domain']}+when:1d"
           "&hl=es-419&gl=CL&ceid=CL:es-419")
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
            if title and len(title) > 20:
                out.append({
                    'title': title,
                    'source': name,
                    'url': it.findtext("link") or "",
                    'first_seen': ts
                })
    except Exception:
        pass
    return out

def get_cached_data(max_age_minutes=60):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                if datetime.now(timezone.utc) - timestamp.replace(tzinfo=timezone.utc) < timedelta(minutes=max_age_minutes):
                    print(f"[CACHE] ✅ Usando caché ({len(cache['articles'])} artículos)")
                    return cache['articles'], cache.get('status', {})
        except Exception as e:
            print(f"[CACHE] Error: {str(e)}")
    return None, None

def save_to_cache(articles, status):
    if not articles: return
    try:
        temp_path = CACHE_FILE + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump({
                'articles': articles,
                'status': status,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }, f, ensure_ascii=False)
        os.replace(temp_path, CACHE_FILE)
        print(f"[CACHE] 💾 Guardados {len(articles)} artículos")
    except Exception as e:
        print(f"[CACHE] Error guardando: {str(e)}")

def fetch_raw_articles(force_refresh=False):
    if not force_refresh:
        articles, status = get_cached_data(max_age_minutes=60)
        if articles:
            return articles, status

    print("[FETCH] Iniciando recolección...")
    
    def work(item):
        name, cfg = item
        arts = _from_homepage(name, cfg)
        if arts:
            return name, arts, "ok"
        arts = _from_gnews(name, cfg)
        return name, arts, "ok_fallback" if arts else "blocked_or_empty"

    articles, status = [], {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for name, arts, st in ex.map(work, SOURCES.items()):
            articles.extend(arts)
            status[name] = st

    seen = set()
    unique_articles = []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            # CORRECCIÓN: Asegurar que first_seen sea string para JSON
            fs = a.get('first_seen')
            if isinstance(fs, datetime):
                a['first_seen'] = fs.isoformat()
            elif not fs:
                a['first_seen'] = datetime.now(timezone.utc).isoformat()
            unique_articles.append(a)

    print(f"[FETCH] Total artículos únicos: {len(unique_articles)}")
    save_to_cache(unique_articles, status)
    return unique_articles, status

def predict_trends(articles, top: int = 8):
    if not articles:
        return []
    
    now = datetime.now(timezone.utc)
    T = defaultdict(lambda: {"srcs": set(), "urls": set(), "rec": [], "label": Counter()})

    for a in articles:
        toks = TOKEN_RE.findall(_norm(a['title']))
        ok = [t for t in toks if len(t) >= 4 and t not in STOPWORDS]
        cands = set(ok)
        cands |= {f"{x} {y}" for x, y in zip(toks, toks[1:])
                  if len(x) >= 4 and len(y) >= 4 and x not in STOPWORDS and y not in STOPWORDS}
        
        for m in ENTITY_RE.findall(a['title']):
            cands.add(_norm(m))
            T[_norm(m)]["label"][m] += 1
            
        first_seen = a.get('first_seen')
        if isinstance(first_seen, str):
            try:
                first_seen = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
            except:
                first_seen = now
        if not first_seen:
            first_seen = now
            
        age_h = ((now - first_seen).total_seconds() / 3600)
        
        for c in cands:
            d = T[c]
            d["srcs"].add(a['source'])
            d["urls"].add(a['url'] or a['title'])
            d["rec"].append(0.5 ** (max(age_h, 0) / 6))

    scored = []
    for term, d in T.items():
        n_src, n_art = len(d["srcs"]), len(d["urls"])
        if n_src < 2:
            continue
            
        diversity = min(1, (n_src - 1) / 3)
        volume = min(1, math.log1p(n_art) / math.log1p(8))
        recency = sum(d["rec"]) / len(d["rec"])
        score = round(100 * (0.35 * diversity + 0.25 * volume + 0.25 * 1.0 + 0.15 * recency))
        
        scored.append({
            "term": d["label"].most_common(1)[0][0] if d["label"] else term,
            "key": term,
            "score": score,
            "sources": sorted(d["srcs"]),
            "articles": n_art,
            "level": "critica" if score > 85 else "alta" if score > 70 else "media"
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    
    result = []
    added_keys = set()
    for s in scored:
        # CORRECCIÓN: Lógica segura para evitar unigramas absorbidos por bigramas
        is_subsumed = False
        for r_key in added_keys:
            if s["key"] in r_key.split() or r_key in s["key"].split():
                is_subsumed = True
                break
        
        if not is_subsumed:
            added_keys.add(s["key"])
            result.append({
                'topic': s['term'],
                'score': s['score'],
                'category': guess_category(s['term']),
                'news_count': s['articles'],
                'news': [{'titulo': 'Agrupado por Frecuencia', 'fuente': ', '.join(s['sources']), 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                'alert_level': 'critical' if s['level'] == 'critica' else ('high' if s['level'] == 'alta' else None),
                'source': 'Algoritmo de Crecimiento',
                'is_realtime': True,
                'timestamp': now.isoformat()
            })
            if len(result) == top:
                break
                
    return result

def guess_category(topic):
    topic_lower = topic.lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia'],
        'Salud': ['salud', 'hospital', 'médico'],
        'Sociedad': ['sociedad', 'educación', 'migración'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución'],
    }
    for category, words in keywords.items():
        if any(word in topic_lower for word in words):
            return category
    return 'Tendencias'

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories(): return jsonify(CATEGORIES)

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
    force_refresh = request.args.get('refresh') == 'true'
    articles, status = fetch_raw_articles(force_refresh=force_refresh)
    predictions = predict_trends(articles)
    return jsonify({'predictions': predictions, 'source_status': status})

@app.route('/api/status', methods=['GET'])
def get_status():
    _, status = get_cached_data()
    return jsonify({
        'mindicador': {'dolar': 950, 'uf': 36000, 'status': 'ok'},
        'weather': {'temperature': 22, 'windspeed': 10, 'status': 'ok'},
        'apis': {'scraping': 'ok', 'sources': status or {}},
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
