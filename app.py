from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'news_cache.json')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
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

# LISTA DEFINITIVA DE RSS (Chile + Internacional + Tech/Econ)
RSS_FEEDS = [
    # Chile
    'https://www.biobiochile.cl/feed/',
    'https://www.elmostrador.cl/feed/',
    'https://www.cooperativa.cl/noticias/site/tax/port/all/rss____1.xml',
    'https://www.latercera.com/arc/outboundfeeds/rss/',
    'https://www.df.cl/noticias/site/tax/port/all/rss____1.xml',
    'https://www.ciperchile.cl/feed/',
    'https://www.theclinic.cl/feed/',
    'https://www.lanacion.cl/feed/',
    # Internacional (Español)
    'https://feeds.bbci.co.uk/mundo/rss.xml',
    'https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/america/portada',
    'https://rss.dw.com/rdf/rss-sp-top',
    'https://cnnespanol.cnn.com/feed/',
    'https://e00-elmundo.uecdn.es/rss/portada.xml',
    # Internacional (Inglés - Tech/Econ)
    'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
    'https://www.theguardian.com/world/rss',
    'https://www.ft.com/world?format=rss', # URL más estable para FT
    'https://techcrunch.com/feed/',
    'https://www.wired.com/feed/rss'
]

def get_cached_news(max_age_minutes=120):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                if datetime.now() - timestamp < timedelta(minutes=max_age_minutes):
                    print(f"[CACHE] ✅ Usando caché ({len(cache['articles'])} artículos)")
                    return cache['articles']
        except Exception as e:
            print(f"[CACHE] Error: {str(e)}")
    return None

def save_to_cache(articles):
    if not articles: return
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'articles': articles, 'timestamp': datetime.now().isoformat()}, f, ensure_ascii=False)
        print(f"[CACHE] 💾 Guardados {len(articles)} artículos")
    except Exception as e:
        print(f"[CACHE] Error guardando: {str(e)}")

def fetch_raw_articles():
    all_articles = []
    api_key = os.getenv('NEWSAPI_KEY')
    
    print(f"[FETCH] NewsAPI Key configurada: {'Sí' if api_key else 'NO'}")
    
    # 1. Intentar NewsAPI primero
    if api_key:
        try:
            url = 'https://newsapi.org/v2/top-headlines'
            params = {'country': 'cl', 'language': 'es', 'pageSize': 30, 'apiKey': api_key}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data.get('articles', []):
                    if item.get('title'):
                        all_articles.append({
                            'title': item['title'].strip(),
                            'source': item.get('source', {}).get('name', 'NewsAPI'),
                            'link': item.get('url', ''),
                            'published': item.get('publishedAt', '')
                        })
                print(f"[FETCH] ✅ NewsAPI: {len(all_articles)} artículos")
        except Exception as e:
            print(f"[FETCH] ❌ NewsAPI Excepción: {str(e)}")

    # 2. Complementar con la lista completa de RSS
    if len(all_articles) < 40: # Apuntamos a tener un buen volumen para la IA
        print(f"[FETCH] Intentando {len(RSS_FEEDS)} feeds RSS...")
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/html, */*',
            'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8'
        })
        
        for url in RSS_FEEDS:
            try:
                response = session.get(url, timeout=8, allow_redirects=True)
                if response.status_code == 200:
                    # Limpiar namespaces XML para evitar errores de parsing
                    content = re.sub(r'\sxmlns="[^"]+"', '', response.text, count=1)
                    root = ET.fromstring(content.encode('utf-8'))
                    
                    source_name = root.find('.//channel/title')
                    source_text = source_name.text.strip() if source_name is not None and source_name.text else 'Medio'
                    
                    items = root.findall('.//item') or root.findall('.//entry')
                    count = 0
                    for item in items[:10]: # Tomamos 10 de cada medio para no saturar
                        title_elem = item.find('title')
                        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                        if title and len(title) > 10:
                            if not any(a['title'] == title for a in all_articles):
                                all_articles.append({
                                    'title': title,
                                    'source': source_text,
                                    'link': item.find('link').text if item.find('link') is not None else '',
                                    'published': ''
                                })
                                count += 1
                    if count > 0:
                        print(f"[FETCH] ✅ {source_text}: {count} artículos")
            except Exception:
                pass # Falla silenciosa, pasamos al siguiente feed
                
    print(f"[FETCH] Total artículos recolectados: {len(all_articles)}")
    return all_articles

def analyze_with_ai_editor(articles):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key or len(articles) < 5:
        return None
    
    headlines = [f"- [{a['source']}] {a['title']}" for a in articles[:50]] # Damos hasta 50 titulares a la IA
    prompt = f"""Eres un Editor Jefe de un medio digital. Analiza estos titulares (mezcla de Chile e internacionales).
Tu tarea:
1. Agrupar titulares que se refieran al mismo evento o tendencia global/local.
2. Crear un 'topic' (título resumen claro, periodístico y SIEMPRE en español, traduce si es necesario).
3. Asignar un 'score' de 0 a 100 basado en relevancia, urgencia e impacto real.
4. Listar las 'sources' (medios) que lo cubren.
5. Devolver SOLO un array JSON válido con los 8 temas más importantes, ordenados por score descendente.

Formato JSON exacto:
[
  {{"topic": "Título resumen del tema en español", "score": 85, "sources": ["BioBio", "NYT"], "summary": "Breve descripción de 10 palabras"}}
]

Titulares a analizar:
{chr(10).join(headlines)}
"""
    
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.1, 'max_tokens': 1500}}
    
    try:
        response = requests.post('https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation', headers=headers, json=payload, timeout=45)
        if response.status_code == 200:
            text = response.json()['output']['choices'][0]['message']['content']
            match = re.search(r'\[.*\]', text, re.DOTALL)
            json_str = match.group(0) if match else text.replace('```json', '').replace('```', '').strip()
            return json.loads(json_str)
    except Exception as e:
        print(f"[AI] Falló: {str(e)}")
    return None

def get_predictions():
    print("[PREDICT] Iniciando...")
    cached = get_cached_news()
    if cached:
        ai_result = analyze_with_ai_editor(cached)
        if ai_result: return format_ai_predictions(ai_result)
    
    raw = fetch_raw_articles()
    if raw:
        save_to_cache(raw)
        
    ai_result = analyze_with_ai_editor(raw)
    if ai_result:
        return format_ai_predictions(ai_result)
    
    if raw:
        return get_algorithmic_fallback(raw)
    
    return []

def format_ai_predictions(ai_data):
    predictions = []
    for item in ai_data[:8]:
        predictions.append({
            'topic': item.get('topic', 'Tema'),
            'score': min(int(item.get('score', 50)), 100),
            'category': guess_category(item.get('topic', '')),
            'news_count': len(item.get('sources', [])),
            'news': [{'titulo': item.get('summary', ''), 'fuente': ', '.join(item.get('sources', [])), 'url': '', 'fecha': datetime.now().strftime('%Y-%m-%d')}],
            'alert_level': 'critical' if item.get('score', 0) >= 85 else ('high' if item.get('score', 0) >= 70 else None),
            'source': 'IA Editor Jefe',
            'is_realtime': True,
            'timestamp': datetime.now().isoformat()
        })
    return sorted(predictions, key=lambda x: x['score'], reverse=True)

def get_algorithmic_fallback(articles):
    from collections import Counter
    stop_words = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this'}
    word_counts = Counter()
    topic_sources = {}
    topic_examples = {}
    
    for article in articles:
        words = [w for w in re.findall(r'\b\w{4,}\b', article['title'].lower()) if w not in stop_words]
        for word in words:
            word_counts[word] += 1
            if word not in topic_sources:
                topic_sources[word] = set()
                topic_examples[word] = []
            topic_sources[word].add(article['source'])
            if len(topic_examples[word]) < 2:
                topic_examples[word].append({'titulo': article['title'], 'fuente': article['source']})
                
    predictions = []
    for word, count in word_counts.most_common(8):
        sources = topic_sources[word]
        if len(sources) >= 2:
            predictions.append({
                'topic': topic_examples[word][0]['titulo'],
                'score': min(50 + len(sources) * 20, 90),
                'category': guess_category(topic_examples[word][0]['titulo']),
                'news_count': len(sources),
                'news': topic_examples[word],
                'alert_level': 'high' if len(sources) >= 3 else None,
                'source': 'Análisis de Frecuencia',
                'is_realtime': True,
                'timestamp': datetime.now().isoformat()
            })
    return sorted(predictions, key=lambda x: x['score'], reverse=True)[:6]

def guess_category(topic):
    topic_lower = topic.lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre', 'financial', 'market'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial', 'world', 'global'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia', 'tech', 'startup'],
        'Salud': ['salud', 'hospital', 'médico'],
        'Sociedad': ['sociedad', 'educación', 'migración'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución'],
    }
    for category, words in keywords.items():
        if any(word in topic_lower for word in words):
            return category
    return 'Tendencias'

def get_trends_for_category(category):
    cached = get_cached_news()
    articles = cached if cached else fetch_raw_articles()
    keywords_raw = SEARCH_KEYWORDS.get(category, 'chile')
    keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
    
    trends = []
    seen = set()
    for article in articles:
        if category == 'all' or any(kw in article['title'].lower() for kw in keywords):
            if article['title'] not in seen:
                seen.add(article['title'])
                trends.append({'topic': article['title'], 'source': article['source'], 'region': 'Chile'})
        if len(trends) >= 6:
            break
    return trends

def get_status_panel():
    return {
        'mindicador': {'dolar': 950, 'uf': 36000, 'status': 'ok'},
        'weather': {'temperature': 22, 'windspeed': 10, 'status': 'ok'},
        'apis': {'rss': 'ok', 'qwen': 'ok' if os.getenv('QWEN_API_KEY') else 'error'},
        'timestamp': datetime.now().isoformat()
    }

def search_news(topic, max_results=5):
    articles = get_cached_news() or fetch_raw_articles()
    news_items = []
    seen = set()
    topic_lower = topic.lower()
    for article in articles:
        if topic_lower in article['title'].lower():
            if article['title'] not in seen:
                seen.add(article['title'])
                news_items.append({'titulo': article['title'], 'fuente': article['source'], 'url': article['link'], 'fecha': article['published'][:10] if article['published'] else ''})
            if len(news_items) >= max_results:
                break
    return news_items

def analyze_with_qwen(prompt, mode='standard'):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key: return None, "QWEN_API_KEY no configurada"
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.1 if mode == 'briefing' else 0.7, 'max_tokens': 2000}}
    try:
        response = requests.post('https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation', headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            text = response.json()['output']['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', text, re.DOTALL)
            json_str = match.group(0) if match else text.replace('```json', '').replace('```', '').strip()
            return json.loads(json_str), None
        return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        return None, f"Error: {str(e)}"

def generate_analysis(topic, topic2, category, region, mode, lens, news):
    news_text = "\n\nNoticias:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    if mode == 'briefing':
        prompt = f"""BRIEFING: TEMA: {topic} | REGIÓN: {region or 'Chile'}{news_text}
JSON: {{"resumen_ejecutivo": "Párrafo claro", "preguntas_fuente": ["P1", "P2", "P3"], "datos_duros": ["D1", "D2"], "timeline_sugerido": "Cuándo publicar", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'devil':
        prompt = f"""ABOGADO DEL DIABLO: TEMA: {topic}{news_text}
JSON: {{"cobertura_mainstream": "Lo que todos dicen", "angulo_ciego": "Lo que NADIE pregunta", "riesgos_sesgos": ["R1", "R2"], "pregunta_incomoda": "Pregunta incómoda", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'compare' and topic2:
        prompt = f"""COMPARA: TEMA A: {topic} | TEMA B: {topic2}{news_text}
JSON: {{"tema_a": "{topic}", "tema_b": "{topic2}", "mas_recorrido": "Cuál tiene más recorrido", "fuentes_comunes": ["F1", "F2"], "angulo_conector": "Ángulo conector", "recomendacion": "Cuál cubrir primero", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    else:
        lens_instruction = {"data": "\nENFOQUE: Estadísticas.", "controversy": "\nENFOQUE: Conflictos.", "human": "\nENFOQUE: Personas.", "economic": "\nENFOQUE: Finanzas."}.get(lens, "")
        prompt = f"""Analiza: TEMA: {topic}{news_text}{lens_instruction}
JSON: {{"puntaje_relevancia": 7, "justificacion_puntaje": "Explicación", "hipotesis": "Hipótesis", "senales_clave": ["S1", "S2"], "angulos_periodisticos": ["A1", "A2"], "fuentes_sugeridas": ["F1", "F2"], "titulares_ejemplo": ["T1", "T2"], "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    return prompt

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories(): return jsonify(CATEGORIES)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 6))
    return jsonify(get_trends_for_category(category)[:limit])

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route(): return jsonify(get_predictions())

@app.route('/api/status', methods=['GET'])
def get_status(): return jsonify(get_status_panel())

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 10))
    conn = get_db()
    rows = conn.cursor().execute('SELECT id, topic, topic2, category, region, mode, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    history = []
    for row in rows:
        try: analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except: analysis = {}
        history.append({'id': row['id'], 'topic': row['topic'], 'topic2': row['topic2'], 'category': row['category'], 'region': row['region'], 'mode': row['mode'], 'analysis': analysis, 'score': row['score'] or 0, 'created_at': row['created_at']})
    return jsonify(history)

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    conn = get_db()
    conn.cursor().execute('DELETE FROM trends WHERE id = ?', (analysis_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

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
        if not topic: return jsonify({'error': 'Falta el tema'}), 400
        
        news = search_news(topic, max_results=5)
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        if error or not analysis:
            analysis = {'puntaje_relevancia': 5, 'hipotesis': 'Análisis en modo fallback.', 'noticias_reales': news}
        
        score = analysis.get('puntaje_relevancia', 5)
        conn = get_db()
        conn.cursor().execute('INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)', (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score))
        conn.commit()
        conn.close()
        
        return jsonify({'topic': topic, 'category': category, 'mode': mode, 'analysis': analysis, 'score': score, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
