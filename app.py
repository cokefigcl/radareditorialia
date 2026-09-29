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
from concurrent.futures import ThreadPoolExecutor
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
        conn.commit()
        conn.close()
        print("[DB] ✅ Tabla trends inicializada")
    except Exception as e:
        print(f"[DB] Error inicializando: {e}")

init_db()

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
    'Belleza': 'belleza OR cosmética OR skincare',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias',
    'Tecnología': 'tecnología OR 5G',
    'Economía': 'economía OR dólar OR inflación',
    'Chile': 'chile',
    'Internacional': 'internacional',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte OR música OR cine OR teatro',
    'Ocio': 'ocio OR entretenimiento',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos OR farándula'
}

SOURCES = {
    "biobio": {"home": "https://www.biobiochile.cl/", "domain": "biobiochile.cl"},
    "latercera": {"home": "https://www.latercera.com/", "domain": "latercera.com"},
    "cooperativa": {"home": "https://www.cooperativa.cl/", "domain": "cooperativa.cl"},
    "df": {"home": "https://www.df.cl/", "domain": "df.cl"},
}

STOPWORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this', 'es', 'son', 'como', 'pero', 'también', 'sin', 'sobre', 'entre'}

def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(c))

def _get(url, retries=3, timeout=10):
    for i in range(retries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=timeout, headers={"Accept-Language": "es-CL,es;q=0.9"})
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

def get_cached_data(max_age_minutes=60):
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

def fetch_raw_articles(force_refresh=False):
    if not force_refresh:
        articles, status = get_cached_data(max_age_minutes=60)
        if articles:
            return articles, status

    print("[FETCH] Iniciando recolección...")
    def work(item):
        name, cfg = item
        arts = _from_homepage(name, cfg)
        if arts: return name, arts, "ok"
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
            unique_articles.append(a)

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
    except Exception:
        pass
    return []

def guess_category(topic):
    topic_lower = str(topic).lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia'],
        'Salud': ['salud', 'hospital', 'médico'],
        'Sociedad': ['sociedad', 'educación', 'migración'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso', 'farándula'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución'],
        'Automotriz': ['auto', 'vehículo', 'volvo', 'automotriz'],
        'Minería': ['minería', 'cobre', 'litio', 'mina'],
        'Cultura': ['cultura', 'arte', 'música', 'cine', 'teatro']
    }
    for cat, words in keywords.items():
        if any(word in topic_lower for word in words):
            return cat
    return 'Tendencias'

# ==================== RUTAS ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify(CATEGORIES)

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route():
    try:
        category = request.args.get('category', 'all')
        force_refresh = request.args.get('refresh') == 'true'
        print(f"[PREDICT] Iniciando para categoría: {category}")
        
        articles, status = fetch_raw_articles(force_refresh=force_refresh)
        if not articles:
            return jsonify({'predictions': [], 'source_status': status, 'category': category})
        
        # 1. Siempre generamos predicciones algorítmicas como red de seguridad
        algo_predictions = group_related_articles(articles, top=8)
        print(f"[PREDICT] Algorítmicas: {len(algo_predictions)}")
        
        cross_predictions = []
        try:
            # 2. Intentamos filtrar, pero si hay pocos, usamos todos para que la IA no falle
            if category != 'all':
                keywords_raw = SEARCH_KEYWORDS.get(category, category.lower())
                keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
                filtered = [a for a in articles if any(kw in a['title'].lower() for kw in keywords)]
                print(f"[PREDICT] Filtrados: {len(filtered)}")
                
                if len(filtered) >= 3:
                    cross_predictions = cross_predictions_func(filtered, category=category, top=6)
                else:
                    cross_predictions = cross_predictions_func(articles, category=category, top=6)
            else:
                cross_predictions = cross_predictions_func(articles, category='all', top=6)
            print(f"[PREDICT] Cruzadas: {len(cross_predictions)}")
        except Exception as e:
            print(f"[PREDICT] IA falló, usando algorítmicas: {str(e)}")
        
        # 3. Combinar (priorizando IA si existe)
        all_predictions = cross_predictions if cross_predictions else algo_predictions
        
        # 4. Deduplicar
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
        # DEVOLVEMOS 200 OK CON ARRAY VACÍO PARA QUE EL FRONTEND NO SE ROMPA
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

@app.route('/api/analyze', methods=['POST'])
def analyze():
    # ... (Mantén tu lógica de analyze actual, funciona bien según los logs)
    return jsonify({'status': 'ok'}) # Placeholder para brevedad, usa tu versión anterior de analyze

@app.route('/api/history', methods=['GET'])
def get_history():
    # ... (Mantén tu lógica de history actual)
    return jsonify([]) # Placeholder para brevedad

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
