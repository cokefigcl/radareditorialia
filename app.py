from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

# ==============================================================================
# TEMPORAL: Fallback por si Railway no carga la variable (SINTAXIS CORRECTA)
# Reemplaza "89f88b93d0634e1ab94c3a5fd018bc1a" con tu clave REAL de NewsAPI
# ¡MANTÉN LAS COMILLAS DOBLES ""!
# ==============================================================================
if not os.getenv('NEWSAPI_KEY'):
    os.environ['NEWSAPI_KEY'] = "89f88b93d0634e1ab94c3a5fd018bc1a"  # <-- PEGA TU KEY AQUÍ ENTRE COMILLAS
    print("⚠️ AVISO: Usando NEWSAPI_KEY hardcodeada porque Railway no la cargó.")

# ==================== BASE DE DATOS ====================
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
            category TEXT,
            region TEXT,
            analysis TEXT,
            score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== CONFIGURACIÓN ====================
CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '⚡'},
    {'name': 'Automotriz', 'icon': '🚗'},
    {'name': 'Belleza', 'icon': '💄'},
    {'name': 'Minería', 'icon': '⛏️'},
    {'name': 'IA', 'icon': '🤖'},
    {'name': 'Tendencias', 'icon': '📈'},
    {'name': 'Tecnología', 'icon': '💻'},
    {'name': 'Economía', 'icon': '💰'}
]

REGIONS = ['Chile']

TRENDS_BY_CATEGORY = {
    'Eléctrico': ["Subsidios a la electromovilidad en Chile 2026", "Expansión de la red de carga", "Nuevas normativas de eficiencia energética", "Energía solar en hogares", "Baterías de litio: Chile como actor global"],
    'Automotriz': ["Caída en ventas de autos nuevos", "Auge de autos usados importados", "Nuevas regulaciones de emisiones", "Competencia de marcas chinas", "Seguros automotrices: alzas"],
    'Belleza': ["Boom del skincare coreano", "Cosmética natural en Chile", "Influencers de belleza y ventas", "Tendencias de maquillaje 2026", "Tratamientos capilares en auge"],
    'Minería': ["Precio del cobre en máximos", "Litio: estrategia nacional", "Minería verde y descarbonización", "Automatización en faenas", "Conflictos socioambientales"],
    'IA': ["Regulación de IA en Chile", "IA generativa y mundo laboral", "Startups chilenas de IA", "Deepfakes y desinformación", "IA en la educación"],
    'Tendencias': ["Deuda de jóvenes y pagos digitales", "Crisis habitacional en Santiago", "Migración y mercado laboral", "Turismo interno post-pandemia", "Foodtech en Chile"],
    'Tecnología': ["Expansión del 5G en regiones", "Ciberseguridad: ataques a empresas", "Fintech y bancarización digital", "Gaming y esports en crecimiento", "Transformación digital pymes"],
    'Economía': ["Tasa de interés del Banco Central", "Inflación y canasta básica", "Reforma tributaria: impactos", "Desempleo y mercado laboral", "Dólar y economía local"]
}

def get_trends_for_category(category):
    if category and category != 'all' and category in TRENDS_BY_CATEGORY:
        return TRENDS_BY_CATEGORY[category]
    all_trends = [t for trends in TRENDS_BY_CATEGORY.values() for t in trends]
    import random
    random.shuffle(all_trends)
    return all_trends[:5]

# ==================== BÚSQUEDA DE NOTICIAS ====================

def search_news(topic, max_results=5):
    print(f"[DEBUG] Buscando noticias para: {topic}")
    
    newsapi_key = os.getenv('NEWSAPI_KEY')
    print(f"[DEBUG] NEWSAPI_KEY detectada, longitud: {len(newsapi_key) if newsapi_key else 0}")
    
    if newsapi_key and len(newsapi_key) > 10:
        print(f"[DEBUG] Intentando NewsAPI...")
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
            print(f"[DEBUG] NewsAPI status: {response.status_code}")
            
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
                    print(f"[DEBUG] NewsAPI encontró {len(news_items)} noticias")
                    return news_items
                else:
                    print("[DEBUG] NewsAPI no devolvió artículos válidos")
            else:
                print(f"[DEBUG] NewsAPI error: {response.text[:200]}")
        except Exception as e:
            print(f"[DEBUG] NewsAPI error: {str(e)}")
    
    # Fallback a GDELT
    print("[DEBUG] Fallback a GDELT...")
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

def analyze_with_qwen(topic, category, region, news):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return None, "QWEN_API_KEY no configurada"
    
    news_text = "\n\nNoticias:\n" + "\n".join([f"- {n['titulo']}" for n in news[:3]]) if news else ""
    
    prompt = f"""Analiza esta tendencia:
TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

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

    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': 'qwen-plus', 'input': {'messages': [{'role': 'user', 'content': prompt}]}, 'parameters': {'temperature': 0.7, 'max_tokens': 1500}},
            timeout=60
        )
        if response.status_code == 200:
            result = response.json()
            text = result.get('output', {}).get('choices', [{}])[0].get('message', {}).get('content', '')
            text = text.replace('```json', '').replace('```', '').strip()
            return json.loads(text), None
        return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        return None, str(e)

def generate_simple_analysis(topic, category, region, news):
    return {
        'puntaje_relevancia': 5,
        'justificacion_puntaje': 'Análisis automático (IA no disponible)',
        'hipotesis': f'La tendencia "{topic}" en {region or "Chile"} muestra relevancia. Se recomienda monitorear.',
        'senales_clave': ['Aumento de menciones', 'Nuevas regulaciones', 'Cambios en el comportamiento'],
        'angulos_periodisticos': ['Impacto económico', 'Perspectivas de expertos', 'Casos relevantes'],
        'fuentes_sugeridas': ['Organismos oficiales', 'Expertos del sector', 'Datos estadísticos'],
        'titulares_ejemplo': [f"Análisis: {topic}", f"Las claves de {topic}"],
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
    return jsonify([{'topic': t, 'source': 'Tendencias ' + (category if category != 'all' else 'Chile'), 'region': 'Chile'} for t in get_trends_for_category(category)[:limit]])

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
    rows = conn.cursor().execute('SELECT id, topic, category, region, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    history = []
    for row in rows:
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except:
            analysis = {}
        history.append({'id': row['id'], 'topic': row['topic'], 'category': row['category'], 'region': row['region'], 'analysis': analysis, 'score': row['score'] or 0, 'created_at': row['created_at']})
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
        category = data.get('category')
        region = data.get('region')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        news = search_news(topic, max_results=5)
        analysis, error = analyze_with_qwen(topic, category, region, news)
        
        used_fallback = False
        if error or not analysis:
            print(f"[DEBUG] Fallback activado: {error}")
            analysis = generate_simple_analysis(topic, category, region, news)
            used_fallback = True
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news if news else []
        
        score = analysis.get('puntaje_relevancia', 5)
        
        conn = get_db()
        conn.cursor().execute('INSERT INTO trends (topic, category, region, analysis, score) VALUES (?, ?, ?, ?, ?)',
                              (topic, category, region, json.dumps(analysis, ensure_ascii=False), score))
        conn.commit()
        conn.close()
        
        return jsonify({
            'topic': topic, 'category': category, 'region': region,
            'analysis': analysis, 'score': score, 'used_fallback': used_fallback,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        topic = request.json.get('topic', 'Tema') if request.json else 'Tema'
        return jsonify({'topic': topic, 'analysis': generate_simple_analysis(topic, None, None, []), 'score': 5, 'warning': f'Error: {str(e)}'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
