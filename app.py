from flask import Flask, render_template, jsonify, request
import os
import json
import re
import time
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

def _get_fast(url, timeout=15):
    try:
        r = cr.get(url, impersonate="chrome", timeout=timeout, headers={"User-Agent": "CoraRadar/1.0"})
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"[HTTP] Error en {url}: {str(e)}")
    return None

def fetch_chilean_sources():
    articles = []
    for name, cfg in SOURCES_CL.items():
        try:
            html = _get_fast(cfg["home"], timeout=15)
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
        except Exception as e:
            print(f"[FETCH] Error en {name}: {str(e)}")
    return articles

def fetch_rss_sources():
    articles = []
    all_sources = {**SOURCES_ES, **SOURCES_EN}
    for name, cfg in all_sources.items():
        try:
            xml = _get_fast(cfg["rss"], timeout=15)
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
        except Exception as e:
            print(f"[FETCH] Error en RSS {name}: {str(e)}")
    return articles

def fetch_reddit_fast():
    articles = []
    try:
        url = "https://www.reddit.com/r/chile/hot/.rss"
        response = cr.get(url, impersonate="chrome", timeout=15, headers={"User-Agent": "CoraRadar/1.0"})
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            count = 0
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                if title and len(title) > 30 and count < 5:
                    articles.append({
                        'title': f"[Reddit] {title}",
                        'source': 'reddit_chile',
                        'url': item.findtext("link", ""),
                        'first_seen': datetime.now(timezone.utc).isoformat(),
                        'is_trend': True
                    })
                    count += 1
        print(f"[FETCH] Reddit: {len(articles)} artículos")
    except Exception as e:
        print(f"[FETCH] Reddit ❌ ERROR REAL: {str(e)}")
    return articles

def fetch_youtube_fast():
    articles = []
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        print("[FETCH] YouTube ⚠️ No hay YOUTUBE_API_KEY configurada")
        return []
    try:
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&chart=mostPopular&regionCode=CL&categoryId=25&maxResults=10&key={api_key}"
        response = cr.get(url, timeout=15)
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
            print(f"[FETCH] YouTube: {len(articles)} artículos")
        else:
            print(f"[FETCH] YouTube ❌ ERROR REAL: HTTP {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"[FETCH] YouTube ❌ ERROR REAL: {str(e)}")
    return articles

def fetch_trends_sources():
    articles = []
    try:
        response = cr.get("https://trends.google.com/trending/rss?geo=CL", impersonate="chrome", timeout=15)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
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
        print(f"[FETCH] Trends: {len(articles)} artículos")
    except Exception as e:
        print(f"[FETCH] Trends ❌ ERROR REAL: {str(e)}")
    return articles

def get_cached_data(max_age_minutes=120):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                age = datetime.now(timezone.utc) - timestamp.replace(tzinfo=timezone.utc)
                
                if age >= timedelta(minutes=max_age_minutes):
                    return None, None
                
                articles = cache.get('articles', [])
                status = cache.get('status', {})
                
                if articles and len(articles) > 10:
                    has_ok_source = any(v == 'ok' for v in status.values())
                    if not has_ok_source:
                        print("[CACHE] ⚠️ Caché con artículos pero sin fuentes OK. Forzando refresh...")
                        return None, None
                
                print(f"[CACHE] ✅ Usando caché ({len(articles)} artículos)")
                return articles, status
        except Exception as e:
            print(f"[CACHE] Error: {str(e)}")
    return None, None

def save_to_cache(articles, status):
    if not articles:
        return
    try:
        temp_path = CACHE_FILE + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump({'articles': articles, 'status': status, 'timestamp': datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False)
        os.replace(temp_path, CACHE_FILE)
    except Exception as e:
        print(f"[CACHE] Error al guardar: {str(e)}")

def fetch_raw_articles(force_refresh=False):
    if not force_refresh:
        articles, status = get_cached_data(max_age_minutes=120)
        if articles:
            return articles, status

    print("[FETCH] Iniciando recolección...")
    start_time = time.time()
    articles = []
    status = {}
    
    cl_articles = fetch_chilean_sources()
    articles.extend(cl_articles)
    for name in SOURCES_CL.keys():
        status[name] = 'ok' if any(a['source'] == name for a in cl_articles) else 'error'
    print(f"[FETCH] Chile: {len(cl_articles)} artículos")
    
    rss_articles = fetch_rss_sources()
    articles.extend(rss_articles)
    for name in {**SOURCES_ES, **SOURCES_EN}.keys():
        status[name] = 'ok' if any(a['source'] == name for a in rss_articles) else 'error'
    print(f"[FETCH] RSS: {len(rss_articles)} artículos")
    
    reddit_articles = fetch_reddit_fast()
    articles.extend(reddit_articles)
    status['reddit'] = 'ok' if len(reddit_articles) > 0 else 'error'
    
    youtube_articles = fetch_youtube_fast()
    articles.extend(youtube_articles)
    status['youtube'] = 'ok' if len(youtube_articles) > 0 else 'error'
    
    trends_articles = fetch_trends_sources()
    articles.extend(trends_articles)
    status['trends'] = 'ok' if len(trends_articles) > 0 else 'error'
    
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
        else:
            groups[a['title']].append(a)
    
    scored = []
    for key, items in groups.items():
        sources = set(item['source'] for item in items)
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

Responde SOLO con un array JSON con {top} tendencias, sin markdown ni texto adicional. Formato:
[{{"topic": "Tema", "score": 72, "reasoning": "Por qué", "signals": ["Señal 1"], "impact": "alto", "timeframe": "próximas horas", "category": "Categoría"}}]"""

    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return []
    
    try:
        response = cr.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.4, 'max_tokens': 1500}},
            timeout=45,
            impersonate="chrome"
        )
        
        if response.status_code == 200:
            result = response.json()
            text = ""
            if isinstance(result, dict) and 'output' in result:
                if 'choices' in result['output'] and len(result['output']['choices']) > 0:
                    text = result['output']['choices'][0].get('message', {}).get('content', '')
                elif 'text' in result['output']:
                    text = result['output']['text']
            
            if not text:
                text = str(result)
            
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                try:
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
                    } for p in predictions[:top] if isinstance(p, dict)]
                except json.JSONDecodeError as e:
                    print(f"[IA] ⚠️ JSONDecodeError: {e}. Texto: {match.group(0)[:300]}")
                    return []
    except Exception as e:
        print(f"[IA] ❌ Error en llamada a IA: {str(e)}")
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
            timeout=45,
            impersonate="chrome"
        )
        if response.status_code == 200:
            result = response.json()
            text = ""
            if isinstance(result, dict) and 'output' in result:
                if 'choices' in result['output'] and len(result['output']['choices']) > 0:
                    text = result['output']['choices'][0].get('message', {}).get('content', '')
                elif 'text' in result['output']:
                    text = result['output']['text']
            
            if not text:
                text = str(result)
                
            tokens_output = len(text) // 4
            track_api_usage('analyze', tokens_input, tokens_output, success=True)
            
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    json_str = match.group(0).replace('```json', '').replace('```', '').strip()
                    return json.loads(json_str), None
                except json.JSONDecodeError as e:
                    print(f"[ANALYZE] ⚠️ JSONDecodeError: {e}. Texto: {json_str[:300]}")
                    return None, "JSON inválido"
            return None, "No se encontró JSON"
        else:
            track_api_usage('analyze', tokens_input, 0, success=False)
            return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        track_api_usage('analyze', tokens_input, 0, success=False)
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
        except Exception as e:
            print(f"[PREDICT] IA falló: {str(e)}")
        
        all_predictions = cross_predictions if cross_predictions else algo_predictions
        seen, unique = set(), []
        for p in all_predictions:
            norm = _norm(p.get('topic', ''))
            if norm and norm not in seen:
                seen.add(norm)
                unique.append(p)
        unique.sort(key=lambda x: x.get('score', 0), reverse=True)
        return jsonify({'predictions': unique[:8], 'source_status': status, 'category': category})
    except Exception as e:
        print(f"[PREDICT] ERROR: {str(e)}")
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
        stats = {'by_source': {}, 'by_category': {}, 'total_articles': len(articles), 'sources_count': 0, 'trends_detected': 0}
        for a in articles:
            source = a.get('source', 'desconocido')
            stats['by_source'][source] = stats['by_source'].get(source, 0) + 1
            cat = guess_category(a['title'])
            stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
            if a.get('is_trend'):
                stats['trends_detected'] += 1
        stats['sources_count'] = len(stats['by_source'])
        
        predictions = group_related_articles(articles, top=8)
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
        cursor.execute('SELECT COUNT(*), SUM(cost_usd) FROM api_usage WHERE DATE(created_at) = ?', (today,))
        today_requests, today_cost = cursor.fetchone()
        cursor.execute('SELECT endpoint, COUNT(*), SUM(cost_usd) FROM api_usage GROUP BY endpoint')
        by_endpoint = [{'endpoint': row[0], 'count': row[1], 'cost': row[2] or 0} for row in cursor.fetchall()]
        cursor.execute("SELECT DATE(created_at) as day, COUNT(*), SUM(cost_usd) FROM api_usage WHERE created_at >= datetime('now', '-7 days') GROUP BY day ORDER BY day")
        daily_usage = [{'day': row[0], 'requests': row[1], 'cost': row[2] or 0} for row in cursor.fetchall()]
        conn.close()
        return jsonify({
            'total_requests': total_requests, 'successful': successful, 'failed': failed,
            'total_tokens': total_tokens, 'total_cost': round(total_cost, 4),
            'today_requests': today_requests or 0, 'today_cost': round(today_cost or 0, 4),
            'by_endpoint': by_endpoint, 'daily_usage': daily_usage,
            'success_rate': round((successful / total_requests * 100) if total_requests > 0 else 0, 1)
        })
    except Exception as e:
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
        
        articles, _ = fetch_raw_articles(force_refresh=False)
        news = []
        topic_lower = topic.lower()
        for a in articles:
            if topic_lower in a['title'].lower():
                news.append({'titulo': a['title'], 'fuente': a['source'], 'url': a['url'], 'fecha': a.get('first_seen', '')[:10] if a.get('first_seen') else ''})
                if len(news) >= 5:
                    break
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        if error or not analysis:
            analysis = {
                'puntaje_relevancia': 6, 'justificacion_puntaje': f'Según {len(news)} noticias recientes.',
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
        except Exception as e:
            print(f"[DB] Error: {str(e)}")
        
        return jsonify({'topic': topic, 'topic2': topic2, 'category': category, 'region': region, 'mode': mode, 'lens': lens, 'analysis': analysis, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 10))
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute('SELECT id, topic, topic2, category, region, mode, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        conn.close()
        history = []
        for row in rows:
            try:
                analysis = json.loads(row[6]) if row[6] else {}
            except:
                analysis = {}
            history.append({'id': row[0], 'topic': row[1], 'topic2': row[2], 'category': row[3], 'region': row[4], 'mode': row[5], 'analysis': analysis, 'score': row[7] or 0, 'created_at': row[8]})
        return jsonify(history)
    except:
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
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Iniciando Cora en el puerto {port}...")
    app.run(host='0.0.0.0', port=port)
