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

def init_db():
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

def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))

def _get(url, retries=3, timeout=10):
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
        out.append({
            'title': t,
            'source': name,
            'url': a.get("href", "") if a else "",
            'first_seen': datetime.now(timezone.utc).isoformat()
        })
    return out

def _from_gnews(name, cfg):
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
            if title and len(title) > 30:
                out.append({
                    'title': title,
                    'source': name,
                    'url': it.findtext("link") or "",
                    'first_seen': ts.isoformat()
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
    if not articles:
        return
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
            print(f"[FETCH] {name}: {len(arts)} artículos - {st}")

    seen = set()
    unique_articles = []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            unique_articles.append(a)

    print(f"[FETCH] Total artículos únicos: {len(unique_articles)}")
    save_to_cache(unique_articles, status)
    return unique_articles, status

def predict_trends(articles, top=8):
    if not articles:
        return []
    
    print(f"[PREDICT] Procesando {len(articles)} artículos (algorítmico)...")
    now = datetime.now(timezone.utc)
    
    scored = []
    for a in articles:
        title = a['title']
        source = a['source']
        
        try:
            fs = a.get('first_seen')
            if isinstance(fs, str):
                fs = datetime.fromisoformat(fs.replace('Z', '+00:00'))
            age_hours = (now - fs).total_seconds() / 3600
            recency_score = max(0, 100 - (age_hours * 5))
        except Exception:
            recency_score = 50
        
        source_bonus = 0
        if source == 'biobio': source_bonus = 10
        elif source == 'latercera': source_bonus = 8
        elif source == 'cooperativa': source_bonus = 6
        elif source == 'df': source_bonus = 5
        
        length = len(title)
        length_score = 10 if 40 <= length <= 100 else 0
        
        total_score = recency_score + source_bonus + length_score
        
        scored.append({
            'topic': title,
            'source': source,
            'score': round(min(100, total_score)),
            'first_seen': a.get('first_seen')
        })
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    
    result = []
    seen_topics = set()
    
    for s in scored:
        norm = _norm(s['topic'])
        is_duplicate = False
        for seen in seen_topics:
            if norm in seen or seen in norm:
                is_duplicate = True
                break
        
        if not is_duplicate and len(result) < top:
            seen_topics.add(norm)
            result.append({
                'topic': s['topic'],
                'score': s['score'],
                'category': guess_category(s['topic']),
                'news_count': 1,
                'news': [{'titulo': s['topic'], 'fuente': s['source'], 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                'alert_level': 'critical' if s['score'] >= 90 else ('high' if s['score'] >= 75 else None),
                'source': 'Algoritmo de Tendencias',
                'is_realtime': True,
                'timestamp': now.isoformat()
            })
    
    return result

def cross_predictions_func(articles, category='all', top=6):
    if not articles:
        return []
    
    if category != 'all':
        keywords_raw = SEARCH_KEYWORDS.get(category, 'chile')
        keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
        articles = [a for a in articles if any(kw in a['title'].lower() for kw in keywords)]
    
    if len(articles) < 5:
        return []
    
    recent = articles[:20]
    headlines = "\n".join([f"- [{a['source']}] {a['title']}" for a in recent])
    
    prompt = f"""Eres un analista editorial experto. Analiza estos titulares recientes de medios chilenos y detecta qué temas tienen POTENCIAL de convertirse en tendencia en las próximas 6-24 horas.

TITULARES ACTUALES:
{headlines}

Responde SOLO con un array JSON de {top} predicciones cruzadas. Para cada una incluye:
- "topic": el tema/titular predicho (claro y periodístico, en español)
- "score": probabilidad de volverse tendencia (0-100)
- "reasoning": por qué crees que se volverá tendencia (1 oración)
- "signals": 2-3 señales actuales que lo indican
- "impact": nivel de impacto esperado (bajo, medio, alto, crítico)
- "timeframe": cuándo podría explotar (próximas horas, mañana, esta semana)
- "category": categoría del tema

Formato JSON exacto:
[
  {{
    "topic": "Tema predicho",
    "score": 85,
    "reasoning": "Razón de por qué será tendencia",
    "signals": ["Señal 1", "Señal 2"],
    "impact": "alto",
    "timeframe": "próximas horas",
    "category": "Política"
  }}
]

Sé específico, periodístico y basado en los titulares reales."""

    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return []
    
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.3, 'max_tokens': 1500}
    }
    
    try:
        print("[CROSS] Analizando predicciones cruzadas con IA...")
        response = cr.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=45,
            impersonate="chrome"
        )
        
        if response.status_code == 200:
            result = response.json()
            try:
                if 'output' in result and 'choices' in result['output']:
                    text = result['output']['choices'][0]['message']['content']
                else:
                    text = str(result)
                
                match = re.search(r'\[.*\]', text, re.DOTALL)
                json_str = match.group(0) if match else text.replace('```json', '').replace('```', '').strip()
                
                predictions = json.loads(json_str)
                print(f"[CROSS] ✅ Generadas {len(predictions)} predicciones cruzadas")
                
                now = datetime.now(timezone.utc)
                formatted = []
                for p in predictions[:top]:
                    formatted.append({
                        'topic': p.get('topic', ''),
                        'score': p.get('score', 50),
                        'reasoning': p.get('reasoning', ''),
                        'signals': p.get('signals', []),
                        'impact': p.get('impact', 'medio'),
                        'timeframe': p.get('timeframe', 'próximas horas'),
                        'category': p.get('category', guess_category(p.get('topic', ''))),
                        'news_count': len(p.get('signals', [])),
                        'news': [{'titulo': p.get('reasoning', ''), 'fuente': 'Análisis IA', 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                        'alert_level': 'critical' if p.get('score', 0) >= 85 else ('high' if p.get('score', 0) >= 70 else None),
                        'source': 'Predicción Cruzada IA',
                        'is_realtime': True,
                        'timestamp': now.isoformat()
                    })
                return formatted
            except Exception as e:
                print(f"[CROSS] Error parseando IA: {str(e)}")
                return []
        return []
    except Exception as e:
        print(f"[CROSS] Excepción IA: {str(e)}")
        return []

def guess_category(topic):
    topic_lower = topic.lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato', 'partido'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre', 'financiero'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial', 'internacional'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia'],
        'Salud': ['salud', 'hospital', 'médico', 'vacuna'],
        'Sociedad': ['sociedad', 'educación', 'migración'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso', 'farándula'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución'],
        'Automotriz': ['auto', 'vehículo', 'volvo', 'automotriz'],
        'Minería': ['minería', 'cobre', 'litio', 'mina'],
    }
    for category, words in keywords.items():
        if any(word in topic_lower for word in words):
            return category
    return 'Tendencias'

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
            if 'output' in result and 'choices' in result['output']:
                text = result['output']['choices'][0]['message']['content']
            elif 'choices' in result:
                text = result['choices'][0]['message']['content']
            else:
                text = str(result)
            
            match = re.search(r'\{.*\}', text, re.DOTALL)
            json_str = match.group(0) if match else text.replace('```json', '').replace('```', '').strip()
            return json.loads(json_str), None
        return None, f"Error HTTP {response.status_code}"
    except Exception as e:
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
        
        algo_predictions = predict_trends(articles, top=4)
        
        cross_predictions = []
        try:
            cross_predictions = cross_predictions_func(articles, category=category, top=6)
        except Exception as e:
            print(f"[PREDICT] IA falló: {str(e)}. Usando solo algorítmicas.")
        
        all_predictions = cross_predictions + algo_predictions
        
        seen = set()
        unique_predictions = []
        for p in all_predictions:
            norm = _norm(p['topic'])
            if norm not in seen:
                seen.add(norm)
                unique_predictions.append(p)
        
        unique_predictions.sort(key=lambda x: x['score'], reverse=True)
        
        return jsonify({
            'predictions': unique_predictions[:8],
            'source_status': status,
            'category': category
        })
    except Exception as e:
        print(f"[PREDICT] ERROR CRÍTICO: {str(e)}")
        return jsonify({'predictions': [], 'error': str(e)}), 500

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
                news.append({
                    'titulo': a['title'],
                    'fuente': a['source'],
                    'url': a['url'],
                    'fecha': a.get('first_seen', '')[:10] if a.get('first_seen') else ''
                })
                if len(news) >= 5:
                    break
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        if error or not analysis:
            analysis = {
                'puntaje_relevancia': 6,
                'justificacion_puntaje': f'El tema "{topic}" requiere seguimiento editorial.',
                'hipotesis': f'{topic} es un tema de interés actual.',
                'senales_clave': ['Aumento en menciones', 'Diversidad de fuentes'],
                'angulos_periodisticos': ['Impacto en la sociedad', 'Perspectivas de expertos'],
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
        
        return jsonify({
            'topic': topic, 'topic2': topic2, 'category': category, 'region': region,
            'mode': mode, 'lens': lens, 'analysis': analysis, 'score': score,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
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
