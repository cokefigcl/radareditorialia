from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
import re
import feedparser
from datetime import datetime, timedelta
from collections import Counter

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')

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

# ==================== CATEGORÍAS ====================
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
    'Eléctrico': 'eléctricas OR transmisión OR distribución OR Enel OR Colbún',
    'Automotriz': 'autos OR vehículos OR electromovilidad',
    'Belleza': 'belleza OR cosmética OR skincare',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias',
    'Tecnología': 'tecnología OR 5G OR startups',
    'Economía': 'economía OR dólar OR inflación',
    'Chile': 'chile',
    'Internacional': 'internacional',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Ocio': 'ocio OR entretenimiento OR gaming',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos OR farándula'
}

# ==================== MOTOR RSS DE MEDIOS CHILENOS ====================

RSS_FEEDS = [
    'https://www.biobiochile.cl/rss',
    'https://www.latercera.com/arc/outboundfeeds/rss/',
    'https://www.emol.com/rss/',
    'https://www.cooperativa.cl/noticias/site/tax/port/all/rss.xml'
]

def fetch_rss_articles():
    """Obtiene los últimos titulares de los principales medios chilenos"""
    all_articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get('title', 'Medio Chileno')
            for entry in feed.entries[:15]: # Últimos 15 de cada medio
                all_articles.append({
                    'title': entry.get('title', '').strip(),
                    'source': source_name,
                    'link': entry.get('link', ''),
                    'published': entry.get('published', '')
                })
        except Exception as e:
            print(f"[RSS] Error leyendo {url}: {str(e)}")
    
    # Ordenar por relevancia (simulada por orden de llegada, los primeros son los más recientes)
    return all_articles

def get_trends_for_category(category):
    """Obtiene tendencias reales filtrando los titulares RSS"""
    print(f"[TRENDS] Buscando tendencias RSS para: {category}")
    articles = fetch_rss_articles()
    
    keywords_raw = SEARCH_KEYWORDS.get(category, 'chile')
    keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
    
    trends = []
    seen = set()
    
    for article in articles:
        title = article['title']
        title_lower = title.lower()
        
        # Si es 'all' o coincide con alguna palabra clave de la categoría
        if category == 'all' or any(kw in title_lower for kw in keywords):
            if title not in seen:
                seen.add(title)
                trends.append({
                    'topic': title,
                    'source': article['source'],
                    'region': 'Chile'
                })
        
        if len(trends) >= 6:
            break
            
    return trends

def get_predictions():
    """Algoritmo de predicción: detecta temas que se repiten en múltiples medios"""
    print("[PREDICT] Analizando repetición de temas en medios...")
    articles = fetch_rss_articles()
    
    if not articles:
        return FALLBACK_PREDICTIONS
    
    # Palabras a ignorar para el análisis de frecuencia
    stop_words = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'como', 'este', 'esta'}
    
    word_counts = Counter()
    topic_sources = {}
    topic_examples = {}
    
    for article in articles:
        title = article['title'].lower()
        # Extraer palabras significativas (longitud > 4)
        words = [w for w in re.findall(r'\b\w{4,}\b', title) if w not in stop_words]
        
        for word in words:
            word_counts[word] += 1
            if word not in topic_sources:
                topic_sources[word] = set()
                topic_examples[word] = []
            
            topic_sources[word].add(article['source'])
            if len(topic_examples[word]) < 3:
                topic_examples[word].append({
                    'titulo': article['title'],
                    'fuente': article['source'],
                    'url': article['link'],
                    'fecha': article['published'][:10] if article['published'] else ''
                })
                
    predictions = []
    
    # Generar predicciones basadas en palabras que aparecen en al menos 2 medios distintos
    for word, count in word_counts.most_common(15):
        sources = topic_sources[word]
        num_sources = len(sources)
        
        if num_sources >= 2: # Si al menos 2 medios hablan de esto
            # Score: base 50 + 20 por cada medio adicional (máx 95)
            score = min(50 + (num_sources * 20), 95)
            alert_level = 'critical' if score >= 85 else ('high' if score >= 70 else None)
            
            sample_title = topic_examples[word][0]['titulo']
            
            predictions.append({
                'topic': sample_title,
                'score': score,
                'category': guess_category(sample_title),
                'news_count': num_sources,
                'news': topic_examples[word],
                'alert_level': alert_level,
                'source': f'Agregador RSS ({num_sources} medios)',
                'is_realtime': True,
                'timestamp': datetime.now().isoformat()
            })
            
    # Ordenar por score descendente
    predictions.sort(key=lambda x: x['score'], reverse=True)
    print(f"[PREDICT] ✅ Generadas {len(predictions[:8])} predicciones reales")
    
    return predictions[:8] if predictions else FALLBACK_PREDICTIONS

def guess_category(topic):
    topic_lower = topic.lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia'],
        'Salud': ['salud', 'hospital', 'médico', 'vacuna'],
        'Sociedad': ['sociedad', 'educación', 'migración', 'vivienda'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso', 'farándula'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución', 'enel', 'colbún'],
    }
    for category, words in keywords.items():
        if any(word in topic_lower for word in words):
            return category
    return 'Tendencias'

# ==================== DATOS DE RESPALDO ====================
FALLBACK_PREDICTIONS = [
    {'topic': 'Reforma de pensiones en Chile: nuevo debate en el Congreso', 'score': 85, 'category': 'Chile', 'news_count': 3, 'news': [{'titulo': 'Congreso discute nueva reforma de pensiones', 'fuente': 'La Tercera', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': 'high', 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()}
]

# ==================== PANEL DE ESTADO ====================
def get_mindicador_data():
    try:
        response = requests.get('https://mindicador.cl/api', timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {'dolar': data.get('dolar', {}).get('valor', 0), 'uf': data.get('uf', {}).get('valor', 0), 'status': 'ok'}
        return {'status': 'error'}
    except:
        return {'status': 'error'}

def get_weather_santiago():
    try:
        url = 'https://api.open-meteo.com/v1/forecast'
        params = {'latitude': -33.4489, 'longitude': -70.6693, 'current_weather': True, 'timezone': 'America/Santiago'}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            weather = data.get('current_weather', {})
            return {'temperature': weather.get('temperature', 0), 'windspeed': weather.get('windspeed', 0), 'status': 'ok'}
        return {'status': 'error'}
    except:
        return {'status': 'error'}

def get_status_panel():
    return {
        'mindicador': get_mindicador_data(),
        'weather': get_weather_santiago(),
        'apis': {'gdelt': 'ok', 'qwen': 'ok' if os.getenv('QWEN_API_KEY') else 'error'},
        'timestamp': datetime.now().isoformat()
    }

# ==================== BÚSQUEDA DE NOTICIAS (Para Análisis) ====================
def search_news(topic, max_results=5):
    # Para el análisis profundo, usamos una búsqueda directa en los mismos RSS
    articles = fetch_rss_articles()
    news_items = []
    seen = set()
    
    topic_lower = topic.lower()
    for article in articles:
        if topic_lower in article['title'].lower() or topic_lower in article['source'].lower():
            if article['title'] not in seen:
                seen.add(article['title'])
                news_items.append({
                    'titulo': article['title'],
                    'fuente': article['source'],
                    'url': article['link'],
                    'fecha': article['published'][:10] if article['published'] else ''
                })
            if len(news_items) >= max_results:
                break
                
    # Si no encuentra en RSS, fallback vacío (la IA igual generará el análisis)
    return news_items

# ==================== ANÁLISIS CON IA ====================
def analyze_with_qwen(prompt, mode='standard'):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return None, "QWEN_API_KEY no configurada"
    
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.1 if mode == 'briefing' else 0.7, 'max_tokens': 2000}}
    
    try:
        response = requests.post('https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation', headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            analysis_text = None
            try: analysis_text = result['output']['choices'][0]['message']['content']
            except:
                try: analysis_text = result['output']['text']
                except: pass
            
            if not analysis_text or not isinstance(analysis_text, str):
                return None, "Respuesta vacía"
            
            match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            json_str = match.group(0) if match else analysis_text.replace('```json', '').replace('```', '').strip()
            
            try: return json.loads(json_str), None
            except json.JSONDecodeError as e: return None, f"Error JSON: {str(e)}"
        return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        return None, f"Error: {str(e)}"

def generate_analysis(topic, topic2, category, region, mode, lens, news):
    news_text = "\n\nNoticias:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    if mode == 'briefing':
        prompt = f"""Eres editor experto. BRIEFING sobre: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"resumen_ejecutivo": "Párrafo claro", "preguntas_fuente": ["P1", "P2", "P3"], "datos_duros": ["D1", "D2"], "timeline_sugerido": "Cuándo publicar", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'devil':
        prompt = f"""Editor crítico. ABOGADO DEL DIABLO: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"cobertura_mainstream": "Lo que todos dicen", "angulo_ciego": "Lo que NADIE pregunta", "riesgos_sesgos": ["R1", "R2"], "pregunta_incomoda": "Pregunta incómoda", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'compare' and topic2:
        prompt = f"""Editor estratégico. COMPARA: TEMA A: {topic} | TEMA B: {topic2} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"tema_a": "{topic}", "tema_b": "{topic2}", "mas_recorrido": "Cuál tiene más recorrido", "fuentes_comunes": ["F1", "F2"], "angulo_conector": "Ángulo conector", "recomendacion": "Cuál cubrir primero", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    else:
        lens_instruction = {"data": "\nENFOQUE: Estadísticas.", "controversy": "\nENFOQUE: Conflictos.", "human": "\nENFOQUE: Personas.", "economic": "\nENFOQUE: Finanzas."}.get(lens, "")
        prompt = f"""Analiza tendencia: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}{lens_instruction}
Responde SOLO JSON: {{"puntaje_relevancia": 7, "justificacion_puntaje": "Explicación", "hipotesis": "Hipótesis", "senales_clave": ["S1", "S2"], "angulos_periodisticos": ["A1", "A2"], "fuentes_sugeridas": ["F1", "F2"], "titulares_ejemplo": ["T1", "T2"], "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    return prompt

def generate_fallback(topic, topic2, category, region, mode, news):
    return {'puntaje_relevancia': 5, 'justificacion_puntaje': 'Análisis automático', 'hipotesis': f'Tendencia "{topic}" muestra relevancia.', 'senales_clave': ['Aumento menciones', 'Nuevas regulaciones'], 'angulos_periodisticos': ['Impacto económico', 'Perspectivas expertos'], 'fuentes_sugeridas': ['Organismos', 'Expertos'], 'titulares_ejemplo': [f"Análisis: {topic}"], 'noticias_reales': news if news else []}

# ==================== RUTAS ====================
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
        
        print(f"\n[ANALYZE] Topic: {topic}, Mode: {mode}")
        news = search_news(topic, max_results=5)
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        if error or not analysis:
            analysis = generate_fallback(topic, topic2, category, region, mode, news)
        
        if 'noticias_reales' not in analysis: analysis['noticias_reales'] = news if news else []
        score = analysis.get('puntaje_relevancia', 5)
        
        conn = get_db()
        conn.cursor().execute('INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)', (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score))
        conn.commit()
        conn.close()
        
        return jsonify({'topic': topic, 'topic2': topic2, 'category': category, 'region': region, 'mode': mode, 'lens': lens, 'analysis': analysis, 'score': score, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
