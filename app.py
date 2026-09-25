from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
import re
from datetime import datetime, timedelta

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
    {'name': 'Automotriz', 'icon': '🚗', 'type': 'tema'},
    {'name': 'Belleza', 'icon': '💄', 'type': 'tema'},
    {'name': 'Minería', 'icon': '⛏️', 'type': 'tema'},
    {'name': 'IA', 'icon': '🤖', 'type': 'tema'},
    {'name': 'Tendencias', 'icon': '📈', 'type': 'tema'},
    {'name': 'Tecnología', 'icon': '💻', 'type': 'tema'},
    {'name': 'Economía', 'icon': '💰', 'type': 'tema'},
    {'name': 'Chile', 'icon': '🇨🇱', 'type': 'region'},
    {'name': 'Regiones', 'icon': '🗺️', 'type': 'region'},
    {'name': 'Internacional', 'icon': '🌍', 'type': 'region'},
    {'name': 'Deportes', 'icon': '⚽', 'type': 'otros'},
    {'name': 'Ciencia y Tecnología', 'icon': '🔬', 'type': 'otros'},
    {'name': 'Cultura', 'icon': '🎭', 'type': 'otros'},
    {'name': 'Ocio', 'icon': '🎮', 'type': 'otros'},
    {'name': 'Salud', 'icon': '🏥', 'type': 'otros'},
    {'name': 'Sociedad', 'icon': '👥', 'type': 'otros'},
    {'name': 'TV y Espectáculos', 'icon': '📺', 'type': 'otros'}
]

REGIONS = ['Chile']

SEARCH_KEYWORDS = {
    'Eléctrico': 'empresas eléctricas OR transmisión eléctrica OR distribución eléctrica OR Enel OR Colbún OR CGE OR AES Andes',
    'Automotriz': 'autos OR vehículos OR electromovilidad OR autos eléctricos OR patentes',
    'Belleza': 'belleza OR cosmética OR skincare',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias Chile',
    'Tecnología': 'tecnología OR 5G OR startups',
    'Economía': 'economía OR dólar OR inflación',
    'Chile': 'Chile',
    'Regiones': 'regiones Chile',
    'Internacional': 'internacional',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Ocio': 'ocio OR entretenimiento OR gaming',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos OR farándula'
}

# ==================== DATOS DE RESPALDO ====================
FALLBACK_PREDICTIONS = [
    {'topic': 'Reforma de pensiones en Chile: nuevo debate en el Congreso', 'score': 85, 'category': 'Chile', 'news_count': 12, 'news': [{'titulo': 'Congreso discute nueva reforma de pensiones', 'fuente': 'La Tercera', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': 'high', 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Crisis de seguridad en Santiago: nuevas medidas gubernamentales', 'score': 80, 'category': 'Sociedad', 'news_count': 10, 'news': [{'titulo': 'Gobierno anuncia plan de seguridad para Santiago', 'fuente': 'BioBio Chile', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': 'high', 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Precio del dólar alcanza nuevo máximo histórico', 'score': 75, 'category': 'Economía', 'news_count': 8, 'news': [{'titulo': 'Dólar supera los $950 pesos chilenos', 'fuente': 'DF', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Selección chilena de fútbol: preparativos para eliminatorias', 'score': 70, 'category': 'Deportes', 'news_count': 7, 'news': [{'titulo': 'La Roja se prepara para próximo partido eliminatorio', 'fuente': 'AS Chile', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Avance de inteligencia artificial en empresas chilenas', 'score': 65, 'category': 'Tecnología', 'news_count': 6, 'news': [{'titulo': 'Startups chilenas lideran adopción de IA', 'fuente': 'Pulso', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Empresas eléctricas anuncian inversión en transmisión', 'score': 60, 'category': 'Eléctrico', 'news_count': 5, 'news': [{'titulo': 'Enel y Colbún planean nuevas líneas de transmisión', 'fuente': 'El Mercurio', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Precio del cobre: impacto en economía chilena', 'score': 55, 'category': 'Economía', 'news_count': 4, 'news': [{'titulo': 'Cobre alcanza máximos de 6 meses', 'fuente': 'DF', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Listas de espera en salud pública: nuevas soluciones', 'score': 50, 'category': 'Salud', 'news_count': 3, 'news': [{'titulo': 'MINSAL implementa sistema digital para reducir listas', 'fuente': '24 Horas', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()}
]

FALLBACK_TRENDS = [
    {'topic': 'Reforma de pensiones genera debate en el Congreso Nacional', 'source': 'La Tercera', 'region': 'Chile'},
    {'topic': 'Nuevas medidas de seguridad para Santiago Centro', 'source': 'BioBio Chile', 'region': 'Chile'},
    {'topic': 'Dólar cierra al alza y alcanza nuevo récord histórico', 'source': 'El Mercurio', 'region': 'Chile'},
    {'topic': 'Selección chilena se prepara para eliminatorias mundialistas', 'source': 'AS Chile', 'region': 'Chile'},
    {'topic': 'Inteligencia artificial transforma empresas chilenas', 'source': 'Pulso', 'region': 'Chile'}
]

# ==================== PANEL DE ESTADO ====================

def get_mindicador_data():
    try:
        print("[STATUS] Consultando mindicador.cl...")
        response = requests.get('https://mindicador.cl/api', timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'dolar': data.get('dolar', {}).get('valor', 0),
                'uf': data.get('uf', {}).get('valor', 0),
                'utm': data.get('utm', {}).get('valor', 0),
                'status': 'ok'
            }
        return {'status': 'error'}
    except Exception as e:
        print(f"[STATUS] Error mindicador: {str(e)}")
        return {'status': 'error'}

def get_weather_santiago():
    try:
        print("[STATUS] Consultando Open-Meteo...")
        url = 'https://api.open-meteo.com/v1/forecast'
        params = {
            'latitude': -33.4489,
            'longitude': -70.6693,
            'current_weather': True,
            'timezone': 'America/Santiago'
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            weather = data.get('current_weather', {})
            return {
                'temperature': weather.get('temperature', 0),
                'windspeed': weather.get('windspeed', 0),
                'weathercode': weather.get('weathercode', 0),
                'status': 'ok'
            }
        return {'status': 'error'}
    except Exception as e:
        print(f"[STATUS] Error clima: {str(e)}")
        return {'status': 'error'}

def check_api_status():
    status = {'gdelt': 'unknown', 'qwen': 'unknown'}
    
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': 'Chile',
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=1)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': 1,
            'sourcelang': 'spa'
        }
        response = requests.get(url, params=params, timeout=15)
        status['gdelt'] = 'ok' if response.status_code == 200 else 'error'
        print(f"[STATUS] GDELT status: {response.status_code}")
    except Exception as e:
        print(f"[STATUS] GDELT error: {str(e)}")
        status['gdelt'] = 'error'
    
    api_key = os.getenv('QWEN_API_KEY')
    status['qwen'] = 'ok' if api_key and len(api_key) > 10 else 'error'
    
    return status

def get_status_panel():
    print("[STATUS] Generando panel de estado...")
    mindicador = get_mindicador_data()
    weather = get_weather_santiago()
    apis = check_api_status()
    
    return {
        'mindicador': mindicador,
        'weather': weather,
        'apis': apis,
        'timestamp': datetime.now().isoformat()
    }

# ==================== PREDICCIONES ====================

def get_gdelt_predictions():
    try:
        print("[PREDICT] Consultando GDELT...")
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': 'Chile',
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=1)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': 50,
            'sourcelang': 'spa',
            'sort': 'DateDesc'
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            if not articles:
                return None
            
            topic_groups = {}
            for article in articles:
                title = article.get('title', '').strip()
                if not title or len(title) < 20:
                    continue
                
                spanish_words = ['el', 'la', 'los', 'las', 'de', 'del', 'al', 'y', 'que', 'por', 'para', 'con', 'chile', 'santiago', 'gobierno', 'presidente', 'ley', 'nuevo', 'más', 'hoy', 'ayer']
                if not any(word in title.lower() for word in spanish_words):
                    continue
                
                words = title.split()[:6]
                topic_key = ' '.join(words)
                
                if topic_key not in topic_groups:
                    topic_groups[topic_key] = {'topic': title, 'count': 0, 'news': [], 'category': guess_category(title)}
                
                topic_groups[topic_key]['count'] += 1
                if len(topic_groups[topic_key]['news']) < 3:
                    topic_groups[topic_key]['news'].append({
                        'titulo': title, 'fuente': article.get('domain', 'Medio'),
                        'url': article.get('url', ''), 'fecha': article.get('seendate', '')[:10]
                    })
            
            predictions = []
            for topic_key, group in topic_groups.items():
                count = group['count']
                score = 90 if count >= 5 else (75 if count >= 3 else (60 if count >= 2 else 40))
                alert_level = 'critical' if count >= 5 else ('high' if count >= 3 else None)
                
                predictions.append({
                    'topic': group['topic'], 'score': score, 'category': group['category'],
                    'news_count': count, 'news': group['news'], 'alert_level': alert_level,
                    'source': 'GDELT Global', 'is_realtime': True, 'timestamp': datetime.now().isoformat()
                })
            
            predictions.sort(key=lambda x: x['score'], reverse=True)
            print(f"[PREDICT] ✅ GDELT: {len(predictions[:8])} predicciones")
            return predictions[:8] if predictions else None
        return None
    except Exception as e:
        print(f"[PREDICT] Error GDELT: {str(e)}")
        return None

def get_predictions():
    print("[PREDICT] Generando predicciones...")
    predictions = get_gdelt_predictions()
    if predictions:
        return predictions
    print("[PREDICT] Usando datos de respaldo")
    return FALLBACK_PREDICTIONS

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

def is_spanish_title(title):
    spanish_words = ['el', 'la', 'los', 'las', 'de', 'del', 'al', 'y', 'que', 'por', 'para', 'con', 'chile', 'santiago', 'gobierno', 'presidente', 'ley', 'nuevo', 'más']
    return sum(1 for word in title.lower().split() if word in spanish_words) >= 2

def get_trends_for_category(category):
    if not category or category == 'all':
        category = 'Chile'
    keywords = SEARCH_KEYWORDS.get(category, category)
    print(f"[TRENDS] Buscando tendencias para: {category}")
    
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': keywords + ' Chile', 'mode': 'artlist', 'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=7)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': 20, 'sourcelang': 'spa', 'sort': 'DateDesc'
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            trends = []
            seen = set()
            for article in data.get('articles', []):
                title = article.get('title', '').strip()
                if title and title not in seen and len(title) > 15 and is_spanish_title(title):
                    seen.add(title)
                    trends.append({'topic': title, 'source': article.get('domain', 'Medio'), 'region': 'Chile'})
                if len(trends) >= 5:
                    break
            if trends:
                print(f"[TRENDS] ✅ GDELT: {len(trends)} tendencias")
                return trends
    except Exception as e:
        print(f"[TRENDS] GDELT error: {str(e)}")
    
    print(f"[TRENDS] Usando datos de respaldo para {category}")
    return FALLBACK_TRENDS[:5]

def search_news(topic, max_results=5):
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': topic, 'mode': 'artlist', 'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=14)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': max_results * 5, 'sourcelang': 'spa'
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            news_items = []
            seen = set()
            for article in data.get('articles', []):
                title = article.get('title', '').strip()
                if title and title not in seen and len(title) > 5:
                    seen.add(title)
                    news_items.append({'titulo': title, 'fuente': article.get('domain', ''), 'url': article.get('url', ''), 'fecha': article.get('seendate', '')[:10]})
                if len(news_items) >= max_results:
                    break
            return news_items
    except Exception as e:
        print(f"[DEBUG] GDELT error: {str(e)}")
    return []

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
    if mode == 'briefing': return {'resumen_ejecutivo': f'Tema "{topic}" requiere atención.', 'preguntas_fuente': ['¿Qué pasa?', '¿Afectados?', '¿Qué sigue?'], 'datos_duros': ['Verificar cifras', 'Confirmar fuentes'], 'timeline_sugerido': 'Esta semana', 'noticias_reales': news if news else []}
    if mode == 'devil': return {'cobertura_mainstream': f'Medios cubren "{topic}" convencionalmente.', 'angulo_ciego': 'Nadie pregunta consecuencias.', 'riesgos_sesgos': ['Sesgo confirmación', 'Falta fuentes'], 'pregunta_incomoda': '¿Qué interés hay?', 'noticias_reales': news if news else []}
    if mode == 'compare' and topic2: return {'tema_a': topic, 'tema_b': topic2, 'mas_recorrido': f'{topic} tiene más recorrido.', 'fuentes_comunes': ['Expertos', 'Organismos'], 'angulo_conector': 'Ambos reflejan cambios.', 'recomendacion': f'Cubrir {topic} primero.', 'noticias_reales': news if news else []}
    return {'puntaje_relevancia': 5, 'justificacion_puntaje': 'Análisis automático', 'hipotesis': f'Tendencia "{topic}" muestra relevancia.', 'senales_clave': ['Aumento menciones', 'Nuevas regulaciones'], 'angulos_periodisticos': ['Impacto económico', 'Perspectivas expertos'], 'fuentes_sugeridas': ['Organismos', 'Expertos'], 'titulares_ejemplo': [f"Análisis: {topic}"], 'noticias_reales': news if news else []}

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories(): return jsonify(CATEGORIES)

@app.route('/api/regions', methods=['GET'])
def get_regions(): return jsonify(REGIONS)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 5))
    return jsonify(get_trends_for_category(category)[:limit])

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route(): return jsonify(get_predictions())

@app.route('/api/status', methods=['GET'])
def get_status(): return jsonify(get_status_panel())

@app.route('/api/debug', methods=['GET'])
def debug():
    return jsonify({'qwen_configured': bool(os.getenv('QWEN_API_KEY')), 'qwen_key_length': len(os.getenv('QWEN_API_KEY', '')), 'timestamp': datetime.now().isoformat()})

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 20))
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
        
        print(f"\n{'='*60}\n[ANALYZE] Topic: {topic}, Mode: {mode}, Lens: {lens}")
        news = search_news(topic, max_results=5)
        print(f"[ANALYZE] Noticias: {len(news)}")
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        used_fallback = False
        if error or not analysis:
            print(f"[ANALYZE] Qwen falló: {error}. Fallback.")
            analysis = generate_fallback(topic, topic2, category, region, mode, news)
            used_fallback = True
        else:
            print("[ANALYZE] Qwen OK!")
        
        if 'noticias_reales' not in analysis: analysis['noticias_reales'] = news if news else []
        score = analysis.get('puntaje_relevancia', 5)
        
        conn = get_db()
        conn.cursor().execute('INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)', (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score))
        conn.commit()
        conn.close()
        
        print(f"[ANALYZE] Completado. Fallback: {used_fallback}\n{'='*60}\n")
        return jsonify({'topic': topic, 'topic2': topic2, 'category': category, 'region': region, 'mode': mode, 'lens': lens, 'analysis': analysis, 'score': score, 'used_fallback': used_fallback, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        topic = request.json.get('topic', 'Tema') if request.json else 'Tema'
        return jsonify({'topic': topic, 'analysis': generate_fallback(topic, None, None, None, 'standard', []), 'score': 5, 'warning': f'Error: {str(e)}'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
