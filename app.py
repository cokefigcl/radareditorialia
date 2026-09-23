from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

# ==================== BASE DE DATOS ====================
DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')
COUNTER_PATH = os.path.join(os.path.dirname(__file__), 'api_counter.json')

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
    'Eléctrico': [
        "Subsidios a la electromovilidad en Chile 2026",
        "Expansión de la red de carga para vehículos eléctricos",
        "Nuevas normativas de eficiencia energética",
        "Crecimiento de la energía solar en hogares chilenos",
        "Baterías de litio: Chile como actor global"
    ],
    'Automotriz': [
        "Caída en las ventas de autos nuevos en Chile",
        "Auge de los autos usados importados",
        "Nuevas regulaciones de emisiones vehiculares",
        "Competencia de marcas chinas en el mercado local",
        "Seguros automotrices: alzas y nuevas coberturas"
    ],
    'Belleza': [
        "Boom del skincare coreano en Latinoamérica",
        "Cosmética natural y sustentable en Chile",
        "Influencers de belleza y su impacto en ventas",
        "Tendencias de maquillaje para 2026",
        "Industria del cabello: tratamientos capilares en auge"
    ],
    'Minería': [
        "Precio del cobre alcanza máximos históricos",
        "Litio: Chile redefine su estrategia nacional",
        "Minería verde y descarbonización del sector",
        "Automatización y robots en faenas mineras",
        "Conflictos socioambientales en zonas mineras"
    ],
    'IA': [
        "Regulación de la inteligencia artificial en Chile",
        "IA generativa transforma el mundo laboral",
        "Startups chilenas de inteligencia artificial",
        "Deepfakes y desinformación: el nuevo desafío",
        "IA en la educación: oportunidades y riesgos"
    ],
    'Tendencias': [
        "Deuda de los jóvenes y medios de pago digitales",
        "Crisis habitacional en Santiago",
        "Migración y su impacto en el mercado laboral",
        "Turismo interno post-pandemia",
        "Alimentación saludable y foodtech en Chile"
    ],
    'Tecnología': [
        "Expansión del 5G en regiones de Chile",
        "Ciberseguridad: ataques a empresas chilenas",
        "Fintech y bancarización digital",
        "Gaming y esports: industria en crecimiento",
        "Transformación digital en pymes chilenas"
    ],
    'Economía': [
        "Tasa de interés del Banco Central de Chile",
        "Inflación y costo de la canasta básica",
        "Reforma tributaria: impactos y debates",
        "Desempleo y mercado laboral chileno",
        "Dólar y su efecto en la economía local"
    ]
}

def get_trends_for_category(category):
    if category and category != 'all' and category in TRENDS_BY_CATEGORY:
        return TRENDS_BY_CATEGORY[category]
    else:
        all_trends = []
        for trends in TRENDS_BY_CATEGORY.values():
            all_trends.extend(trends)
        import random
        random.shuffle(all_trends)
        return all_trends[:5]

# ==================== CONTADOR DE API ====================

def load_counter():
    try:
        if os.path.exists(COUNTER_PATH):
            with open(COUNTER_PATH, 'r') as f:
                data = json.load(f)
            today = datetime.now().strftime('%Y-%m-%d')
            if data.get('date') != today:
                return {'count': 0, 'date': today, 'force_gdelt': False}
            return data
        else:
            return {'count': 0, 'date': datetime.now().strftime('%Y-%m-%d'), 'force_gdelt': False}
    except:
        return {'count': 0, 'date': datetime.now().strftime('%Y-%m-%d'), 'force_gdelt': False}

def save_counter(data):
    try:
        with open(COUNTER_PATH, 'w') as f:
            json.dump(data, f)
    except:
        pass

def increment_counter():
    counter = load_counter()
    counter['count'] += 1
    if counter['count'] >= 90:
        counter['force_gdelt'] = True
    save_counter(counter)
    return counter

def get_api_status():
    counter = load_counter()
    remaining = max(0, 100 - counter['count'])
    return {
        'count': counter['count'],
        'remaining': remaining,
        'limit': 100,
        'force_gdelt': counter.get('force_gdelt', False),
        'date': counter.get('date', '')
    }

# ==================== BÚSQUEDA DE NOTICIAS ====================

def search_newsapi(topic, max_results=5, days_back=7):
    api_key = os.getenv('NEWSAPI_KEY')
    if not api_key:
        return None
    
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        url = 'https://newsapi.org/v2/everything'
        params = {
            'q': topic,
            'from': start_date.strftime('%Y-%m-%d'),
            'to': end_date.strftime('%Y-%m-%d'),
            'sortBy': 'publishedAt',
            'language': 'es',
            'pageSize': max_results * 2,
            'apiKey': api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            
            news_items = []
            seen_titles = set()
            
            for article in articles:
                title = article.get('title', '').strip()
                if title and title not in seen_titles and len(title) > 10:
                    seen_titles.add(title)
                    news_items.append({
                        'titulo': title,
                        'fuente': article.get('source', {}).get('name', ''),
                        'url': article.get('url', ''),
                        'fecha': article.get('publishedAt', '')[:10]
                    })
                if len(news_items) >= max_results:
                    break
            
            return news_items
        elif response.status_code == 429:
            counter = load_counter()
            counter['force_gdelt'] = True
            save_counter(counter)
            return 'rate_limit'
        else:
            return None
            
    except Exception as e:
        print(f"Error NewsAPI: {str(e)}")
        return None

def search_gdelt_news(topic, max_results=5, days_back=7):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': topic,
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': start_date.strftime('%Y%m%d%H%M%S'),
            'enddatetime': end_date.strftime('%Y%m%d%H%M%S'),
            'maxrecords': max_results * 3,
            'sourcelang': 'spa',
            'sort': 'DateDesc'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            
            news_items = []
            seen_titles = set()
            
            for article in articles:
                title = article.get('title', '').strip()
                if title and title not in seen_titles and len(title) > 10:
                    seen_titles.add(title)
                    news_items.append({
                        'titulo': title,
                        'fuente': article.get('domain', ''),
                        'url': article.get('url', ''),
                        'fecha': article.get('seendate', '')[:10]
                    })
                if len(news_items) >= max_results:
                    break
            
            return news_items
        return []
    except Exception as e:
        print(f"Error GDELT: {str(e)}")
        return []

def search_news_smart(topic, max_results=5, days_back=7):
    counter = load_counter()
    
    if counter.get('force_gdelt', False):
        print(f"Usando GDELT (límite NewsAPI alcanzado)")
        return search_gdelt_news(topic, max_results, days_back)
    
    print(f"Intentando NewsAPI (requests hoy: {counter['count']}/100)")
    result = search_newsapi(topic, max_results, days_back)
    
    if result is None:
        print("NewsAPI no disponible, usando GDELT")
        return search_gdelt_news(topic, max_results, days_back)
    
    if result == 'rate_limit':
        print("Rate limit de NewsAPI alcanzado, cambiando a GDELT")
        counter = load_counter()
        counter['force_gdelt'] = True
        save_counter(counter)
        return search_gdelt_news(topic, max_results, days_back)
    
    increment_counter()
    return result

def get_trend_evolution(topic, weeks=2):
    evolution = []
    end_date = datetime.now()
    
    for i in range(weeks, 0, -1):
        week_end = end_date - timedelta(weeks=i-1)
        week_start = week_end - timedelta(days=7)
        
        try:
            url = 'https://api.gdeltproject.org/api/v2/doc/doc'
            params = {
                'query': topic,
                'mode': 'artlist',
                'format': 'json',
                'startdatetime': week_start.strftime('%Y%m%d%H%M%S'),
                'enddatetime': week_end.strftime('%Y%m%d%H%M%S'),
                'maxrecords': 100,
                'sourcelang': 'spa'
            }
            
            response = requests.get(url, params=params, timeout=8)
            
            if response.status_code == 200:
                count = len(response.json().get('articles', []))
            else:
                count = 0
        except:
            count = 0
        
        evolution.append({
            'semana': f'Semana {weeks - i + 1}',
            'fecha_inicio': week_start.strftime('%d/%m'),
            'fecha_fin': week_end.strftime('%d/%m'),
            'articulos': count
        })
    
    return evolution

# ==================== ANÁLISIS CON IA ====================

def generate_analysis_with_qwen(topic, category, region, real_news):
    """Generar análisis usando Qwen"""
    api_key = os.getenv('QWEN_API_KEY')
    
    if not api_key:
        return None, "API key no configurada"
    
    news_context = ""
    if real_news:
        news_context = "\n\nNOTICIAS ENCONTRADAS:\n" + "\n".join([f"- {n['titulo']}" for n in real_news])
    
    prompt = f"""Analiza esta tendencia periodística:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}
{news_context}

Responde SOLO con JSON válido:
{{
  "puntaje_relevancia": 7,
  "justificacion_puntaje": "Breve explicación",
  "hipotesis": "Hipótesis de 2-3 oraciones",
  "senales_clave": ["Señal 1", "Señal 2"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2"],
  "titulares_ejemplo": ["Titular 1", "Titular 2"],
  "noticias_reales": {json.dumps(real_news if real_news else [], ensure_ascii=False)}
}}"""

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.7, 'max_tokens': 1000}
    }
    
    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            
            try:
                if 'output' in result and 'choices' in result['output']:
                    analysis_text = result['output']['choices'][0]['message']['content']
                elif 'output' in result and 'text' in result['output']:
                    analysis_text = result['output']['text']
                else:
                    analysis_text = str(result.get('output', result))
            except:
                analysis_text = str(result)
            
            analysis_text = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(analysis_text)
                return analysis, None
            except json.JSONDecodeError as e:
                return None, f"Error parseando JSON: {str(e)}"
        else:
            return None, f"Error API Qwen: {response.status_code}"
    except Exception as e:
        return None, f"Error de conexión: {str(e)}"

def generate_fallback_analysis(topic, category, region, real_news):
    """Generar análisis de fallback cuando Qwen falla"""
    return {
        'puntaje_relevancia': 5,
        'justificacion_puntaje': 'Análisis generado automáticamente (IA no disponible)',
        'hipotesis': f'La tendencia "{topic}" en la categoría {category or "General"} para {region or "Chile"} muestra relevancia periodística. Se recomienda monitorear su evolución en los próximos días.',
        'senales_clave': [
            f'Aumento de menciones sobre "{topic}" en medios de comunicación',
            'Nuevas propuestas o regulaciones relacionadas con el tema',
            'Cambios en el comportamiento o interés del público'
        ],
        'angulos_periodisticos': [
            f'Impacto económico y social de "{topic}" en {region or "Chile"}',
            'Perspectivas de expertos y actores clave del sector',
            'Casos de éxito, fracaso o controversia relacionados'
        ],
        'fuentes_sugeridas': [
            'Organismos oficiales y gubernamentales',
            'Expertos y académicos del sector',
            'Datos estadísticos y reportes de la industria'
        ],
        'titulares_ejemplo': [
            f"Análisis en profundidad: {topic}",
            f"Las claves de {topic} en {region or 'Chile'}",
            f"Expertos advierten sobre {topic}"
        ],
        'noticias_reales': real_news if real_news else []
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
    return jsonify([
        {'topic': t, 'source': 'Tendencias ' + (category if category != 'all' else 'Chile'), 'region': 'Chile'}
        for t in trends[:limit]
    ])

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(get_api_status())

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 20))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, topic, category, region, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?',
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except:
            analysis = {}
        history.append({
            'id': row['id'],
            'topic': row['topic'],
            'category': row['category'],
            'region': row['region'],
            'analysis': analysis,
            'score': row['score'] if row['score'] else 0,
            'created_at': row['created_at']
        })
    return jsonify(history)

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM trends WHERE id = ?', (analysis_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        print(f"\n{'='*50}")
        print(f"Iniciando análisis...")
        
        data = request.json
        topic = data.get('topic', '').strip()
        category = data.get('category')
        region = data.get('region')
        
        print(f"Tema: '{topic}'")
        print(f"Categoría: {category}")
        print(f"Región: {region}")
        
        if not topic:
            print("Error: Tema vacío")
            return jsonify({'error': 'Falta el tema'}), 400
        
        # 1. Buscar noticias
        print("Buscando noticias...")
        real_news = search_news_smart(topic, max_results=5, days_back=14)
        print(f"Noticias encontradas: {len(real_news) if real_news else 0}")
        
        # 2. Evolución
        print("Obteniendo evolución...")
        evolution = get_trend_evolution(topic, weeks=2)
        print(f"Semanas de evolución: {len(evolution)}")
        
        # 3. Calcular tendencia
        if len(evolution) >= 2:
            first = evolution[0]['articulos']
            last = evolution[-1]['articulos']
            if last > first:
                trend_direction = 'subiendo'
                trend_percent = round(((last - first) / max(first, 1)) * 100)
            elif last < first:
                trend_direction = 'bajando'
                trend_percent = round(((first - last) / max(first, 1)) * 100)
            else:
                trend_direction = 'estable'
                trend_percent = 0
        else:
            trend_direction = 'estable'
            trend_percent = 0
        
        # 4. Generar análisis con IA
        print("Generando análisis con IA...")
        analysis, error = generate_analysis_with_qwen(topic, category, region, real_news)
        
        if error:
            print(f"Error de IA: {error}")
            print("Usando análisis de fallback...")
            analysis = generate_fallback_analysis(topic, category, region, real_news)
        
        if not analysis:
            print("Análisis vacío, usando fallback...")
            analysis = generate_fallback_analysis(topic, category, region, real_news)
        
        # Asegurar que tenga todos los campos
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = real_news if real_news else []
        
        score = analysis.get('puntaje_relevancia', 5)
        
        # 5. Guardar en BD
        print("Guardando en base de datos...")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO trends (topic, category, region, analysis, score) VALUES (?, ?, ?, ?, ?)',
            (topic, category, region, json.dumps(analysis, ensure_ascii=False), score)
        )
        conn.commit()
        conn.close()
        
        print(f"Análisis completado exitosamente. Score: {score}")
        print(f"{'='*50}\n")
        
        return jsonify({
            'topic': topic,
            'category': category,
            'region': region,
            'analysis': analysis,
            'score': score,
            'evolution': evolution,
            'trend_direction': trend_direction,
            'trend_percent': trend_percent,
            'noticias_encontradas': len(real_news) if real_news else 0,
            'api_status': get_api_status(),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error crítico: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Retornar análisis de fallback incluso en caso de error
        topic = request.json.get('topic', 'Tema desconocido') if request.json else 'Tema desconocido'
        analysis = generate_fallback_analysis(topic, None, None, [])
        
        return jsonify({
            'topic': topic,
            'category': None,
            'region': None,
            'analysis': analysis,
            'score': 5,
            'evolution': [],
            'trend_direction': 'estable',
            'trend_percent': 0,
            'noticias_encontradas': 0,
            'api_status': get_api_status(),
            'timestamp': datetime.now().isoformat(),
            'warning': 'Se generó un análisis básico debido a un error técnico'
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
