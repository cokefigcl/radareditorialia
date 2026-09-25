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

if not os.getenv('NEWSAPI_KEY'):
    os.environ['NEWSAPI_KEY'] = "89f88b93d0634e1ab94c3a5fd018bc1a"
    print("⚠️ Usando NEWSAPI_KEY hardcodeada")

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
    {'name': 'Sociedad', 'icon': '👥', 'type': 'seccion'},
    {'name': 'TV y Espectáculos', 'icon': '📺', 'type': 'seccion'}
]

SEARCH_KEYWORDS = {
    'Eléctrico': 'electromovilidad OR energía solar',
    'Automotriz': 'autos OR vehículos',
    'Belleza': 'belleza OR cosmética',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias Chile',
    'Tecnología': 'tecnología OR 5G',
    'Economía': 'economía OR dólar OR inflación',
    'Nacional': 'Chile',
    'Internacional': 'internacional',
    'Valparaíso': 'Valparaíso',
    'Metropolitana': 'Santiago',
    'Biobío': 'Biobío OR Concepción',
    'Araucanía': 'Araucanía OR Temuco',
    'Los Ríos': 'Valdivia',
    'Los Lagos': 'Puerto Montt',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Dopamina': 'redes sociales OR viral',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos'
}

# ==================== SISTEMA DE PREDICCIÓN INFALIBLE ====================

def get_seed_topics():
    """Temas que siempre son relevantes en Chile para validar en tiempo real"""
    return [
        {'topic': 'Reforma de pensiones en Chile', 'category': 'Nacional'},
        {'topic': 'Delincuencia y seguridad en Santiago', 'category': 'Sociedad'},
        {'topic': 'Precio del dólar y economía chilena', 'category': 'Economía'},
        {'topic': 'Selección chilena de fútbol', 'category': 'Deportes'},
        {'topic': 'Crisis habitacional en Chile', 'category': 'Sociedad'},
        {'topic': 'Avance de la inteligencia artificial en Chile', 'category': 'Tecnología'},
        {'topic': 'Nuevas leyes de tránsito en Chile', 'category': 'Nacional'},
        {'topic': 'Precio del cobre y minería', 'category': 'Economía'},
        {'topic': 'Salud pública y listas de espera en Chile', 'category': 'Salud'},
        {'topic': 'Educación y universidades en Chile', 'category': 'Sociedad'},
        {'topic': 'Farándula y televisión en Chile', 'category': 'TV y Espectáculos'},
        {'topic': 'Medio ambiente y cambio climático en Chile', 'category': 'Ciencia y Tecnología'}
    ]

def get_predictions():
    """Valida temas semilla en tiempo real con NewsAPI para generar predicciones reales"""
    print("[PREDICT] Generando predicciones con validación en tiempo real...")
    newsapi_key = os.getenv('NEWSAPI_KEY')
    
    if not newsapi_key:
        print("[PREDICT] Sin API key, no se pueden generar predicciones")
        return []
    
    seed_topics = get_seed_topics()
    predictions = []
    
    for seed in seed_topics:
        topic = seed['topic']
        category = seed['category']
        
        try:
            # Buscar noticias de las últimas 24 horas para este tema
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': topic,
                'from': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d'),
                'sortBy': 'publishedAt',
                'language': 'es',
                'pageSize': 5,
                'apiKey': newsapi_key
            }
            response = requests.get(url, params=params, timeout=8)
            
            news_items = []
            news_count = 0
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                news_count = len(articles)
                
                for article in articles[:3]:
                    title = article.get('title', '').strip()
                    if title and len(title) > 10:
                        news_items.append({
                            'titulo': title,
                            'fuente': article.get('source', {}).get('name', 'Medio'),
                            'url': article.get('url', ''),
                            'fecha': article.get('publishedAt', '')[:10]
                        })
            
            # Calcular score basado en volumen de noticias en 24h
            # 0 noticias = 20 pts, 1-2 noticias = 50 pts, 3+ noticias = 80+ pts
            if news_count == 0:
                score = 20
            elif news_count <= 2:
                score = 50
            else:
                score = min(80 + (news_count * 5), 95)
            
            # Solo mostrar si tiene actividad reciente (score >= 40)
            if score >= 40:
                alert_level = 'critical' if score >= 85 else ('high' if score >= 70 else None)
                
                predictions.append({
                    'topic': topic,
                    'score': score,
                    'category': category,
                    'news_count': news_count,
                    'news': news_items,
                    'alert_level': alert_level,
                    'source': 'NewsAPI 24h',
                    'is_realtime': True,
                    'timestamp': datetime.now().isoformat()
                })
                
        except Exception as e:
            print(f"[PREDICT] Error validando '{topic}': {str(e)}")
            continue
    
    # Ordenar por score descendente
    predictions.sort(key=lambda x: x['score'], reverse=True)
    print(f"[PREDICT] ✅ Generadas {len(predictions)} predicciones válidas")
    
    return predictions[:8]

def is_spanish_title(title):
    spanish_words = ['el', 'la', 'los', 'las', 'de', 'del', 'al', 'y', 'que', 'por', 'para', 'con', 'chile', 'santiago', 'gobierno', 'presidente', 'ley', 'nuevo', 'más']
    title_lower = title.lower()
    words = title_lower.split()
    spanish_count = sum(1 for word in words if word in spanish_words)
    return spanish_count >= 2

def get_trends_for_category(category):
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
                trends = []
                seen = set()
                for article in data.get('articles', []):
                    title = article.get('title', '').strip()
                    if title and title not in seen and len(title) > 15 and is_spanish_title(title):
                        seen.add(title)
                        trends.append({
                            'topic': title,
                            'source': article.get('source', {}).get('name', 'Medio'),
                            'region': 'Chile'
                        })
                    if len(trends) >= 5:
                        break
                if trends:
                    print(f"[TRENDS] ✅ NewsAPI: {len(trends)} tendencias")
                    return trends
        except Exception as e:
            print(f"[TRENDS] NewsAPI error: {str(e)}")
    
    return []

def search_news(topic, max_results=5):
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
    
    return []

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
        response = requests.post('https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation', headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            analysis_text = None
            try:
                analysis_text = result['output']['choices'][0]['message']['content']
            except:
                try:
                    analysis_text = result['output']['text']
                except:
                    pass
            
            if not analysis_text or not isinstance(analysis_text, str):
                return None, "Respuesta vacía"
            
            match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            json_str = match.group(0) if match else analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                return json.loads(json_str), None
            except json.JSONDecodeError as e:
                return None, f"Error JSON: {str(e)}"
        return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        return None, f"Error: {str(e)}"

def generate_analysis(topic, topic2, category, region, mode, lens, news):
    news_text = "\n\nNoticias:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    
    if mode == 'briefing':
        prompt = f"""Eres editor experto. BRIEFING sobre:
TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON:
{{"resumen_ejecutivo": "Párrafo claro (3-4 oraciones)", "preguntas_fuente": ["Pregunta 1", "Pregunta 2", "Pregunta 3"], "datos_duros": ["Dato 1", "Dato 2"], "timeline_sugerido": "Cuándo publicar", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'devil':
        prompt = f"""Editor crítico. ABOGADO DEL DIABLO:
TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON:
{{"cobertura_mainstream": "Lo que todos dicen", "angulo_ciego": "Lo que NADIE pregunta", "riesgos_sesgos": ["Riesgo 1", "Riesgo 2"], "pregunta_incomoda": "Pregunta incómoda", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'compare' and topic2:
        prompt = f"""Editor estratégico. COMPARA:
TEMA A: {topic} | TEMA B: {topic2} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON:
{{"tema_a": "{topic}", "tema_b": "{topic2}", "mas_recorrido": "Cuál tiene más recorrido", "fuentes_comunes": ["Fuente 1", "Fuente 2"], "angulo_conector": "Ángulo conector", "recomendacion": "Cuál cubrir primero", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    else:
        lens_instruction = ""
        if lens == 'data': lens_instruction = "\nENFOQUE: Estadísticas y cifras."
        elif lens == 'controversy': lens_instruction = "\nENFOQUE: Conflictos y debates."
        elif lens == 'human': lens_instruction = "\nENFOQUE: Impacto en personas."
        elif lens == 'economic': lens_instruction = "\nENFOQUE: Impacto financiero."
        
        prompt = f"""Analiza tendencia:
TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}{lens_instruction}
Responde SOLO JSON:
{{"puntaje_relevancia": 7, "justificacion_puntaje": "Explicación", "hipotesis": "Hipótesis 2-3 oraciones", "senales_clave": ["Señal 1", "Señal 2"], "angulos_periodisticos": ["Ángulo 1", "Ángulo 2"], "fuentes_sugeridas": ["Fuente 1", "Fuente 2"], "titulares_ejemplo": ["Titular 1", "Titular 2"], "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    return prompt

def generate_fallback(topic, topic2, category, region, mode, news):
    if mode == 'briefing':
        return {'resumen_ejecutivo': f'Tema "{topic}" en {region or "Chile"} requiere atención.', 'preguntas_fuente': ['¿Qué pasa?', '¿Quiénes afectados?', '¿Qué sigue?'], 'datos_duros': ['Verificar cifras', 'Confirmar fuentes'], 'timeline_sugerido': 'Esta semana', 'noticias_reales': news if news else []}
    elif mode == 'devil':
        return {'cobertura_mainstream': f'Medios cubren "{topic}" convencionalmente.', 'angulo_ciego': 'Nadie pregunta consecuencias largo plazo.', 'riesgos_sesgos': ['Sesgo confirmación', 'Falta fuentes'], 'pregunta_incomoda': '¿Qué interés hay?', 'noticias_reales': news if news else []}
    elif mode == 'compare' and topic2:
        return {'tema_a': topic, 'tema_b': topic2, 'mas_recorrido': f'{topic} tiene más recorrido.', 'fuentes_comunes': ['Expertos', 'Organismos'], 'angulo_conector': 'Ambos reflejan cambios.', 'recomendacion': f'Cubrir {topic} primero.', 'noticias_reales': news if news else []}
    return {'puntaje_relevancia': 5, 'justificacion_puntaje': 'Análisis automático', 'hipotesis': f'Tendencia "{topic}" muestra relevancia.', 'senales_clave': ['Aumento menciones', 'Nuevas regulaciones'], 'angulos_periodisticos': ['Impacto económico', 'Perspectivas expertos'], 'fuentes_sugeridas': ['Organismos', 'Expertos'], 'titulares_ejemplo': [f"Análisis: {topic}"], 'noticias_reales': news if news else []}

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
    return jsonify(get_trends_for_category(category)[:limit])

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route():
    return jsonify(get_predictions())

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
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
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
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news if news else []
        
        score = analysis.get('puntaje_relevancia', 5)
        conn = get_db()
        conn.cursor().execute('INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)',
                              (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score))
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
