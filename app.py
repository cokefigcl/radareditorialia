from flask import Flask, render_template, jsonify, request
import os
import json
import re
import time
import random
import unicodedata
import sqlite3
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

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
        print("[DB] ✅ Tablas inicializadas")
    except Exception as e:
        print(f"[DB] Error: {e}")

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
    'Cultura': 'cultura OR arte OR música OR cine',
    'Ocio': 'ocio OR entretenimiento',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos'
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

STOPWORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this', 'es', 'son', 'como', 'pero', 'también', 'sin', 'sobre', 'entre'}

def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(c))

def _get_fast(url, timeout=5):
    """Solicitud HTTP rápida con timeout estricto"""
    try:
        r = cr.get(url, impersonate="chrome", timeout=timeout, headers={"User-Agent": "CoraRadar/1.0"})
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

def fetch_chilean_sources():
    """Obtiene artículos de medios chilenos (rápido)"""
    articles = []
    for name, cfg in SOURCES_CL.items():
        try:
            html = _get_fast(cfg["home"], timeout=5)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup.select("h1, h2, h3")[:20]:
                    t = " ".join(tag.get_text(" ", strip=True).split())
                    if 30 < len(t) < 150:
                        a = tag.find("a") or tag.find_parent("a")
                        articles.append({
                            'title': t,
                            'source': name,
                            'url': a.get("href", "") if a else "",
                            'first_seen': datetime.now(timezone.utc).isoformat()
                        })
                print(f"[CL] ✅ {name}: OK")
        except:
            print(f"[CL] ❌ {name}: FAIL")
    return articles

def fetch_rss_sources():
    """Obtiene artículos de RSS internacionales (rápido)"""
    articles = []
    all_sources = {**SOURCES_ES, **SOURCES_EN}
    
    for name, cfg in all_sources.items():
        try:
            xml = _get_fast(cfg["rss"], timeout=5)
            if xml:
                root = ET.fromstring(xml)
                count = 0
                for item in root.iter("item"):
                    title = item.findtext("title", "").strip()
                    if title and len(title) > 20:
                        articles.append({
                            'title': title,
                            'source': name,
                            'url': item.findtext("link", ""),
                            'first_seen': datetime.now(timezone.utc).isoformat()
                        })
                        count += 1
                        if count >= 15:
                            break
                print(f"[RSS] ✅ {name}: {count}")
        except:
            print(f"[RSS] ❌ {name}: FAIL")
    return articles

def fetch_reddit_fast():
    """Reddit ultra-rápido con timeout de 3 segundos por subreddit"""
    articles = []
    subreddits = ['chile', 'worldnews']  # Solo 2 principales para velocidad
    
    def get_reddit_posts(subreddit):
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot/.rss"
            xml = _get_fast(url, timeout=3)
            if xml:
                root = ET.fromstring(xml)
                count = 0
                for item in root.iter("item"):
                    title = item.findtext("title", "").strip()
                    if title and len(title) > 30 and count < 5:
                        articles.append({
                            'title': f"[Reddit r/{subreddit}] {title}",
                            'source': f'reddit_{subreddit}',
                            'url': item.findtext("link", ""),
                            'first_seen': datetime.now(timezone.utc).isoformat(),
                            'is_trend': True
                        })
                        count += 1
                return count
        except:
            return 0
    
    # Ejecutar en paralelo con timeout total de 10 segundos
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(get_reddit_posts, sub) for sub in subreddits]
        for future in futures:
            try:
                future.result(timeout=5)
            except FuturesTimeoutError:
                print("[REDDIT] ⏱️ Timeout")
    
    print(f"[REDDIT] ✅ Total: {len(articles)}")
    return articles

def fetch_youtube_fast():
    """YouTube ultra-rápido con timeout de 5 segundos"""
    articles = []
    api_key = os.getenv('YOUTUBE_API_KEY')
    
    if not api_key:
        return []
    
    try:
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&chart=mostPopular&regionCode=CL&categoryId=25&maxResults=10&key={api_key}"
        response = cr.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            for item in data.get('items', [])[:10]:
                title = item.get('snippet', {}).get('title', '').strip()
                if title:
                    articles.append({
                        'title': f"[YouTube] {title}",
                        'source': 'youtube_trending',
                        'url': f"https://youtube.com/watch?v={item.get('id', '')}",
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True
                    })
            print(f"[YOUTUBE] ✅ {len(articles)}")
    except:
        print("[YOUTUBE] ❌ FAIL")
    
    return articles

def fetch_trends_sources():
    """Google Trends y Wikipedia (rápido)"""
    articles = []
    
    # Google Trends
    try:
        xml = _get_fast("https://trends.google.com/trending/rss?geo=CL", timeout=5)
        if xml:
            root = ET.fromstring(xml)
            for item in root.iter("item")[:10]:
                title = item.findtext("title", "").strip()
                if title:
                    articles.append({
                        'title': f"[Google Trends] {title}",
                        'source': 'google_trends',
                        'url': item.findtext("link", ""),
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True
                    })
            print(f"[TRENDS] ✅ {len([a for a in articles if a['source']=='google_trends'])}")
    except:
        print("[TRENDS]  FAIL")
    
    return articles

def get_cached_data(max_age_minutes=120):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                if datetime.now(timezone.utc) - timestamp.replace(tzinfo=timezone.utc) < timedelta(minutes=max_age_minutes):
                    return cache['articles'], cache.get('status', {})
        except:
            pass
    return None, None

def save_to_cache(articles, status):
    if not articles:
        return
    try:
        temp_path = CACHE_FILE + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump({'articles': articles, 'status': status, 'timestamp': datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False)
        os.replace(temp_path, CACHE_FILE)
    except:
        pass

def fetch_raw_articles(force_refresh=False):
    """Recolección ultra-rápida con timeouts estrictos"""
    if not force_refresh:
        articles, status = get_cached_data(max_age_minutes=120)
        if articles:
            return articles, status

    print("[FETCH] Iniciando recolección rápida...")
    start_time = time.time()
    articles = []
    status = {}
    
    # Ejecutar todo en paralelo con ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as executor:
        # Submit todas las tareas
        future_cl = executor.submit(fetch_chilean_sources)
        future_rss = executor.submit(fetch_rss_sources)
        future_reddit = executor.submit(fetch_reddit_fast)
        future_youtube = executor.submit(fetch_youtube_fast)
        future_trends = executor.submit(fetch_trends_sources)
        
        # Esperar con timeout total de 60 segundos
        try:
            articles.extend(future_cl.result(timeout=15))
            status['chilean'] = 'ok'
        except:
            status['chilean'] = 'error'
        
        try:
            articles.extend(future_rss.result(timeout=15))
            status['rss'] = 'ok'
        except:
            status['rss'] = 'error'
        
        try:
            articles.extend(future_reddit.result(timeout=10))
            status['reddit'] = 'ok'
        except:
            status['reddit'] = 'error'
        
        try:
            articles.extend(future_youtube.result(timeout=8))
            status['youtube'] = 'ok'
        except:
            status['youtube'] = 'error'
        
        try:
            articles.extend(future_trends.result(timeout=10))
            status['trends'] = 'ok'
        except:
            status['trends'] = 'error'
    
    # Eliminar duplicados
    seen = set()
    unique = []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            unique.append(a)
    
    elapsed = time.time() - start_time
    print(f"[FETCH] ✅ {len(unique)} artículos únicos en {elapsed:.1f}s")
    save_to_cache(unique, status)
    return unique, status

def group_related_articles(articles, top=8):
    if not articles:
        return []
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
        if len(items) < 2 and len(sources) < 2:
            continue
        
        score = len(sources) * 20 + min(30, len(items) * 5)
        representative = max(items, key=lambda x: len(x['title']))
        
        scored.append({
            'topic': representative['title'],
            'score': min(95, score),
            'sources': sorted(sources),
            'count': len(items),
            'articles': items[:3]
        })
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    
    result = []
    seen = set()
    for s in scored[:top]:
        norm = _norm(s['topic'])
        if norm not in seen:
            seen.add(norm)
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
    
    recent = articles[:15]
    headlines = "\n".join([f"- [{a['source']}] {a['title']}" for a in recent])
    
    prompt = f"""Analiza estos titulares y detecta tendencias emergentes:
{headlines}

Responde SOLO JSON con {top} tendencias:
[{{"topic": "Tema", "score": 72, "reasoning": "Por qué", "signals": ["Señal 1"], "impact": "alto", "timeframe": "próximas horas", "category": "Categoría"}}]"""

    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return []
    
    try:
        response = cr.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.4, 'max_tokens': 1500}},
            timeout=30,
            impersonate="chrome"
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('output', {}).get('choices', [{}])[0].get('message', {}).get('content') or str(result)
            
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                predictions = json.loads(match.group(0))
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
                    'news': [{'titulo': p.get('reasoning', ''), 'fuente': 'IA', 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                    'alert_level': 'critical' if p.get('score', 50) >= 80 else None,
                    'source': 'IA',
                    'is_realtime': True,
                    'timestamp': now.isoformat()
                } for p in predictions[:top]]
    except Exception as e:
        print(f"[IA] Error: {e}")
    return []

def guess_category(topic):
    topic_lower = str(topic).lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso'],
        'Chile': ['gobierno', 'presidente', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia'],
        'Salud': ['salud', 'hospital', 'médico'],
        'Sociedad': ['sociedad', 'educación'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso'],
        'Eléctrico': ['eléctric', 'transmisión'],
        'Automotriz': ['auto', 'vehículo'],
        'Minería': ['minería', 'cobre', 'litio'],
        'Cultura': ['cultura', 'arte', 'música', 'cine']
    }
    for cat, words in keywords.items():
        if any(word in topic_lower for word in words):
            return cat
    return 'Tendencias'

def track_api_usage(endpoint, tokens_input=0, tokens_output=0, success=True):
    try:
        cost = (tokens_input / 1_000_000 * 0.40) + (tokens_output / 1_000_000 * 1.20)
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute(
            'INSERT INTO api_usage (endpoint, tokens_input, tokens_output, cost_usd, success) VALUES (?, ?, ?, ?, ?)',
            (endpoint, tokens_input, tokens_output, cost, 1 if success else 0)
        )
        conn.commit()
        conn.close()
    except:
        pass

# ... (Mantén las rutas Flask existentes sin cambios) ...
# (index, dashboard, categories, trending, predictions, status, statistics, usage, analyze, history, delete_history)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
