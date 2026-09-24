from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
import re
from datetime import datetime, timedelta
from pytrends.request import TrendReq

load_dotenv()

app = Flask(__name__)

# Fallback temporal si Railway no carga NEWSAPI_KEY
if not os.getenv('NEWSAPI_KEY'):
    os.environ['NEWSAPI_KEY'] = "89f88b93d0634e1ab94c3a5fd018bc1a"
    print("️ Usando NEWSAPI_KEY hardcodeada")

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

# ==================== CATEGORÍAS EXPANDIDAS ====================
CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '⚡', 'type': 'tema'},
    {'name': 'Automotriz', 'icon': '🚗', 'type': 'tema'},
    {'name': 'Belleza', 'icon': '💄', 'type': 'tema'},
    {'name': 'Minería', 'icon': '⛏️', 'type': 'tema'},
    {'name': 'IA', 'icon': '🤖', 'type': 'tema'},
    {'name': 'Tendencias', 'icon': '📈', 'type': 'tema'},
    {'name': 'Tecnología', 'icon': '💻', 'type': 'tema'},
    {'name': 'Economía', 'icon': '💰', 'type': 'tema'},
    {'name': 'Nacional', 'icon': '🇨🇱', 'type': 'region'},
    {'name': 'Internacional', 'icon': '🌍', 'type': 'region'},
    {'name': 'Valparaíso', 'icon': '🏖️', 'type': 'region'},
    {'name': 'Metropolitana', 'icon': '🏙️', 'type': 'region'},
    {'name': 'Biobío', 'icon': '🌲', 'type': 'region'},
    {'name': 'Araucanía', 'icon': '🌳', 'type': 'region'},
    {'name': 'Los Ríos', 'icon': '🌊', 'type': 'region'},
    {'name': 'Los Lagos', 'icon': '🏔️', 'type': 'region'},
    {'name': 'Deportes', 'icon': '⚽', 'type': 'seccion'},
    {'name': 'Ciencia y Tecnología', 'icon': '🔬', 'type': 'seccion'},
    {'name': 'Cultura', 'icon': '🎭', 'type': 'seccion'},
    {'name': 'Dopamina', 'icon': '🧠', 'type': 'seccion'},
    {'name': 'Salud', 'icon': '🏥', 'type': 'seccion'},
    {'name': 'Sociedad', 'icon': '', 'type': 'seccion'},
    {'name': 'TV y Espectáculos', 'icon': '📺', 'type': 'seccion'}
]

REGIONS = ['Chile']

# Palabras clave para búsqueda en NewsAPI por categoría
SEARCH_KEYWORDS = {
    'Eléctrico': 'electromovilidad OR energía solar OR vehículos eléctricos',
    'Automotriz': 'autos OR vehículos OR automotriz',
    'Belleza': 'belleza OR cosmética OR skincare',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias',
    'Tecnología': 'tecnología OR 5G OR startups',
    'Economía': 'economía OR dólar OR inflación',
    'Nacional': 'Chile',
    'Internacional': 'internacional',
    'Valparaíso': 'Valparaíso',
    'Metropolitana': 'Santiago',
    'Biobío': 'Biobío OR Concepción',
    'Araucanía': 'Araucanía OR Temuco',
    'Los Ríos': 'Valdivia OR Los Ríos',
    'Los Lagos': 'Puerto Montt OR Los Lagos',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Dopamina': 'redes sociales OR viral',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos OR farándula'
}

# ==================== GOOGLE TRENDS ====================

def get_google_trends_data():
    """Obtiene tendencias ascendentes de Google Trends en Chile"""
    try:
        pytrends = TrendReq(hl='es-CL', tz=-240)
        
        # Obtener tendencias diarias en Chile
        trending_searches = pytrends.trending_searches(pn='chile')
        
        if trending_searches.empty:
            return []
        
        # Tomar los top 10
        topics = trending_searches[0].head(10).tolist()
        
        print(f"[TRENDS] Google Trends encontró {len(topics)} temas")
        
        return topics
    except Exception as e:
        print(f"[TRENDS] Error Google Trends: {str(e)}")
        return []

def calculate_prediction_score(topic, news_count):
    """Calcula score de predicción basado en volumen y noticias"""
    # Score base por noticias encontradas
    news_score = min(news_count * 20, 60)  # Máximo 60 puntos
    
    # Score por volumen de búsqueda (simulado con noticias)
    volume_score = min(news_count * 10, 30)  # Máximo 30 puntos
    
    # Score base mínimo
    base_score = 10
    
    total = base_score + news_score + volume_score
    return min(total, 100)

def get_predictions():
    """Genera predicciones cruzando Google Trends + NewsAPI"""
    print("[PREDICT] Generando predicciones...")
    
    # 1. Obtener temas de Google Trends
    gt_topics = get_google_trends_data()
    
    if not gt_topics:
        print("[PREDICT] No hay datos de Google Trends")
        return []
    
    predictions = []
    
    # 2. Para cada tema, buscar noticias y calcular score
    for topic in gt_topics[:10]:
        print(f"[PREDICT] Analizando: {topic}")
        
        # Buscar noticias
        news = search_news(topic, max_results=3)
        news_count = len(news)
        
        # Calcular score
        score = calculate_prediction_score(topic, news_count)
        
        # Solo incluir si tiene score > 30
        if score >= 30:
            # Determinar categoría más probable
            category = guess_category(topic)
            
            # Generar alerta si score > 70
            alert_level = None
            if score >= 85:
                alert_level = 'critical'
            elif score >= 70:
                alert_level = 'high'
            
            predictions.append({
                'topic': topic,
                'score': score,
                'category': category,
                'news_count': news_count,
                'news': news,
                'alert_level': alert_level,
                'timestamp': datetime.now().isoformat()
            })
    
    # Ordenar por score descendente
    predictions.sort(key=lambda x: x['score'], reverse=True)
    
    print(f"[PREDICT] Generadas {len(predictions)} predicciones")
    
    return predictions[:10]

def guess_category(topic):
    """Intenta adivinar la categoría de un tema"""
    topic_lower = topic.lower()
    
    category_keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato', 'juego'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'banco central'],
        'Nacional': ['gobierno', 'presidente', 'kongreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial'],
        'Tecnología': ['tecnología', 'app', 'digital', 'startup', 'ia'],
        'Salud': ['salud', 'virus', 'vacuna', 'hospital', 'médico'],
        'Sociedad': ['sociedad', 'protesta', 'derechos', 'educación'],
        'TV y Espectáculos': ['actor', 'actriz', 'show', 'tv', 'famoso'],
        'Ciencia y Tecnología': ['ciencia', 'investigación', 'descubrimiento'],
    }
    
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in topic_lower:
                return category
    
    return 'Tendencias'

def get_trends_for_category(category):
    """Obtiene tendencias REALES desde NewsAPI o GDELT"""
    if not category or category == 'all':
        category = 'Chile'
    
    keywords = SEARCH_KEYWORDS.get(category, category)
    newsapi_key = os.getenv('NEWSAPI_KEY')
    
    print(f"[TRENDS] Buscando tendencias para: {category}")
    
    if newsapi_key and len(newsapi_key) > 10:
        try:
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': keywords,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d'),
                'sortBy': 'publishedAt',
                'language': 'es',
                'pageSize': 10,
                'apiKey': newsapi_key
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                trends = []
                seen = set()
                for article in articles:
                    title = article.get('title', '').strip()
                    if title and title not in seen and len(title) > 15:
                        seen.add(title)
                        trends.append({
                            'topic': title,
                            'source': article.get('source', {}).get('name', 'Medio'),
                            'region': 'Chile'
                        })
                    if len(trends) >= 5:
                        break
                
                if trends:
                    return trends
        except Exception as e:
            print(f"[TRENDS] NewsAPI error: {str(e)}")
    
    # Fallback GDELT
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': keywords + ' Chile',
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=7)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': 20,
            'sourcelang': 'spa',
            'sort': 'DateDesc'
        }
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            
            trends = []
            seen = set()
            for article in articles:
                title = article.get('title', '').strip()
                if title and title not in seen and len(title) > 15:
                    seen.add(title)
                    trends.append({
                        'topic': title,
                        'source': article.get('domain', 'Medio'),
                        'region': 'Chile'
                    })
                if len(trends) >= 5:
                    break
            
            return trends
    except Exception as e:
        print(f"[TRENDS] GDELT error: {str(e)}")
    
    return []

# ==================== BÚSQUEDA DE NOTICIAS ====================

def search_news(topic, max_results=5):
    print(f"[DEBUG] Buscando noticias para: {topic}")
    newsapi_key = os.getenv('NEWSAPI_KEY')
    
    if newsapi_key and len(newsapi_key) > 10:
        try:
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': topic,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d'),
                'sortBy': 'publishedAt',
                'language': 'es',
                'pageSize': max_results * 3,
                'apiKey': newsapi_key
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                news_items = []
                seen = set()
                for article in data.get('articles', []):
                    title = article.get('title', '').strip()
                    if title and title not in seen and len(title) > 10:
                        seen.add(title)
                        news_items.append({
                            'titulo': title,
                            'fuente': article.get('source', {}).get('name', ''),
                            'url': article.get('url', ''),
                            'fecha': article.get('publishedAt', '')[:10]
                        })
                    if len(news_items) >= max_results:
                        break
                if news_items:
                    return news_items
        except Exception as e:
            print(f"[DEBUG] NewsAPI error: {str(e)}")
    
    # Fallback GDELT
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': topic,
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=14)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': max_results * 5,
            'sourcelang': 'spa'
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
                    news_items.append({
                        'titulo': title,
                        'fuente': article.get('domain', ''),
                        'url': article.get('url', ''),
                        'fecha': article.get('seendate', '')[:10]
                    })
                if len(news_items) >= max_results:
                    break
            return news_items
    except Exception as e:
        print(f"[DEBUG] GDELT error: {str(e)}")
    
    return []

# ==================== ANÁLISIS CON IA ====================

def analyze_with_qwen(prompt, mode='standard'):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return None, "QWEN_API_KEY no configurada"
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.1 if mode == 'briefing' else 0.7, 'max_tokens': 2000}
    }
    
    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=60
        )
        
        print(f"[DEBUG] Qwen status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            analysis_text = None
            try:
                analysis_text = result['output']['choices'][0]['message']['content']
            except:
                try:
                    analysis_text = result['output']['text']
                except:
                    try:
                        analysis_text = result['output']['result']
                    except:
                        pass
            
            if not analysis_text or not isinstance(analysis_text, str):
                return None, f"Respuesta vacía o inválida de Qwen"
            
            print(f"[DEBUG] Texto recibido ({len(analysis_text)} chars)")
            
            match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                json_str = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(json_str)
                print(f"[DEBUG] JSON parseado exitosamente!")
                return analysis, None
            except json.JSONDecodeError as e:
                print(f"[DEBUG] Error parseando JSON: {e}")
                return None, f"Error parseando JSON: {str(e)}"
        else:
            return None, f"Error HTTP {response.status_code}: {response.text[:300]}"
            
    except requests.exceptions.Timeout:
        return None, "Timeout de Qwen API"
    except Exception as e:
        return None, f"Error de conexión: {str(e)}"

def generate_analysis(topic, topic2, category, region, mode, lens, news):
    news_text = "\n\nNoticias encontradas:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    
    if mode == 'briefing':
        prompt = f"""Eres un editor periodístico experto. Genera un BRIEFING PERIODÍSTICO ejecutivo sobre:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "resumen_ejecutivo": "Un párrafo claro y directo sobre qué está pasando (3-4 oraciones)",
  "preguntas_fuente": ["Pregunta 1 exacta para hacerle a tu fuente/experto", "Pregunta 2", "Pregunta 3"],
  "datos_duros": ["Dato 1 que debes verificar antes de publicar", "Dato 2"],
  "timeline_sugerido": "Cuándo publicar (ej: 'Esta semana', 'Urgente', 'Esperar 2 días')",
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    elif mode == 'devil':
        prompt = f"""Eres un editor crítico y provocador. Analiza este tema como ABOGADO DEL DIABLO:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "cobertura_mainstream": "Lo que todos los medios están diciendo (2-3 oraciones)",
  "angulo_ciego": "Lo que NADIE está preguntando y podría ser la verdadera historia",
  "riesgos_sesgos": ["Riesgo 1 o sesgo a evitar", "Riesgo 2"],
  "pregunta_incomoda": "La pregunta incómoda que deberías hacer",
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    elif mode == 'compare' and topic2:
        prompt = f"""Eres un editor estratégico. COMPARA estos dos temas periodísticos:

TEMA A: {topic}
TEMA B: {topic2}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "tema_a": "{topic}",
  "tema_b": "{topic2}",
  "mas_recorrido": "Cuál tema tiene más recorrido periodístico ahora y por qué",
  "fuentes_comunes": ["Fuente 1 que sirve para ambos", "Fuente 2"],
  "angulo_conector": "Un ángulo que conecte ambos temas",
  "recomendacion": "Cuál cubrir primero y por qué",
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    else:
        lens_instruction = ""
        if lens == 'data':
            lens_instruction = "\nENFOQUE: Prioriza estadísticas, cifras, datos duros y fuentes oficiales."
        elif lens == 'controversy':
            lens_instruction = "\nENFOQUE: Busca conflictos, controversias, debates y posturas enfrentadas."
        elif lens == 'human':
            lens_instruction = "\nENFOQUE: Enfócate en cómo afecta a las personas, historias de vida, impacto humano."
        elif lens == 'economic':
            lens_instruction = "\nENFOQUE: Analiza impacto financiero, costos, oportunidades de negocio, mercado."
        
        prompt = f"""Analiza esta tendencia periodística:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}{lens_instruction}

Responde SOLO con JSON válido:
{{
  "puntaje_relevancia": 7,
  "justificacion_puntaje": "Explicación breve",
  "hipotesis": "Hipótesis de 2-3 oraciones",
  "senales_clave": ["Señal 1", "Señal 2"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2"],
  "titulares_ejemplo": ["Titular 1", "Titular 2"],
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    return prompt

def generate_fallback(topic, topic2, category, region, mode, news):
    if mode == 'briefing':
        return {
            'resumen_ejecutivo': f'El tema "{topic}" en {region or "Chile"} requiere atención periodística.',
            'preguntas_fuente': ['¿Qué está pasando exactamente?', '¿Quiénes son los afectados?', '¿Qué sigue?'],
            'datos_duros': ['Verificar cifras oficiales', 'Confirmar fuentes primarias'],
            'timeline_sugerido': 'Esta semana',
            'noticias_reales': news if news else []
        }
    elif mode == 'devil':
        return {
            'cobertura_mainstream': f'Los medios están cubriendo "{topic}" de forma convencional.',
            'angulo_ciego': 'Nadie está preguntando sobre las consecuencias a largo plazo.',
            'riesgos_sesgos': ['Sesgo de confirmación', 'Falta de fuentes diversas'],
            'pregunta_incomoda': '¿Qué interés hay detrás de esta narrativa?',
            'noticias_reales': news if news else []
        }
    elif mode == 'compare' and topic2:
        return {
            'tema_a': topic,
            'tema_b': topic2,
            'mas_recorrido': f'{topic} tiene más recorrido inmediato.',
            'fuentes_comunes': ['Expertos del sector', 'Organismos oficiales'],
            'angulo_conector': 'Ambos temas reflejan cambios estructurales en la sociedad.',
            'recomendacion': f'Cubrir {topic} primero por urgencia.',
            'noticias_reales': news if news else []
        }
    else:
        return {
            'puntaje_relevancia': 5,
            'justificacion_puntaje': 'Análisis automático',
            'hipotesis': f'La tendencia "{topic}" muestra relevancia.',
            'senales_clave': ['Aumento de menciones', 'Nuevas regulaciones'],
            'angulos_periodisticos': ['Impacto económico', 'Perspectivas de expertos'],
            'fuentes_sugeridas': ['Organismos oficiales', 'Expertos'],
            'titulares_ejemplo': [f"Análisis: {topic}"],
            'noticias_reales': news if news else []
        }

# ==================== RUTAS ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify(CATEGORIES)

@app.route('/api/regions', methods=['GET'])
def get_regions():
    return jsonify(REGIONS)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 5))
    trends = get_trends_for_category(category)
    return jsonify(trends[:limit])

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route():
    """Endpoint para obtener predicciones basadas en Google Trends"""
    predictions = get_predictions()
    return jsonify(predictions)

@app.route('/api/debug', methods=['GET'])
def debug():
    return jsonify({
        'qwen_configured': bool(os.getenv('QWEN_API_KEY')),
        'qwen_key_length': len(os.getenv('QWEN_API_KEY', '')),
        'newsapi_configured': bool(os.getenv('NEWSAPI_KEY')),
        'newsapi_key_length': len(os.getenv('NEWSAPI_KEY', '')),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 20))
    conn = get_db()
    rows = conn.cursor().execute('SELECT id, topic, topic2, category, region, mode, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    history = []
    for row in rows:
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except:
            analysis = {}
        history.append({
            'id': row['id'], 'topic': row['topic'], 'topic2': row['topic2'],
            'category': row['category'], 'region': row['region'], 'mode': row['mode'],
            'analysis': analysis, 'score': row['score'] or 0, 'created_at': row['created_at']
        })
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
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        print(f"\n{'='*60}")
        print(f"[ANALYZE] Topic: {topic}, Mode: {mode}, Lens: {lens}")
        
        news = search_news(topic, max_results=5)
        print(f"[ANALYZE] Noticias: {len(news)}")
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        used_fallback = False
        if error or not analysis:
            print(f"[ANALYZE] Qwen falló: {error}")
            analysis = generate_fallback(topic, topic2, category, region, mode, news)
            used_fallback = True
        else:
            print(f"[ANALYZE] Qwen OK!")
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news if news else []
        
        score = analysis.get('puntaje_relevancia', 5)
        
        conn = get_db()
        conn.cursor().execute('INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)',
                              (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score))
        conn.commit()
        conn.close()
        
        print(f"[ANALYZE] Completado. Fallback: {used_fallback}")
        print(f"{'='*60}\n")
        
        return jsonify({
            'topic': topic, 'topic2': topic2, 'category': category, 'region': region,
            'mode': mode, 'lens': lens,
            'analysis': analysis, 'score': score, 'used_fallback': used_fallback,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        topic = request.json.get('topic', 'Tema') if request.json else 'Tema'
        return jsonify({'topic': topic, 'analysis': generate_fallback(topic, None, None, None, 'standard', []), 'score': 5, 'warning': f'Error: {str(e)}'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
