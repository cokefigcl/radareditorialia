from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

# TEMPORAL: Hardcode para test (ELIMINAR DESPUÉS)
NEWSAPI_KEY_HARDCODE = '89f88...'  # Reemplaza con tu key completa

if not os.getenv('NEWSAPI_KEY'):
    os.environ['NEWSAPI_KEY'] = 89f88b93d0634e1ab94c3a5fd018bc1a
    print("⚠️ NEWSAPI_KEY hardcodeada para test")

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

# ==================== BÚSQUEDA DE NOTICIAS ====================

def search_news(topic, max_results=5):
    print(f"[DEBUG] Buscando noticias para: {topic}")
    
    newsapi_key = os.getenv('NEWSAPI_KEY')
    print(f"[DEBUG] NEWSAPI_KEY length: {len(newsapi_key) if newsapi_key else 0}")
    
    if newsapi_key and len(newsapi_key) > 10:
        print(f"[DEBUG] Usando NewsAPI...")
        try:
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': topic,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d'),
                'sortBy': 'publishedAt',
                'language': 'es',
                'pageSize': max_results * 2,
                'apiKey': newsapi_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            print(f"[DEBUG] NewsAPI status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                print(f"[DEBUG] NewsAPI artículos: {len(articles)}")
                
                news_items = []
                seen = set()
                
                for article in articles:
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
                    print("[DEBUG] NewsAPI no encontró artículos válidos")
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
            articles = data.get('articles', [])
            print(f"[DEBUG] GDELT artículos: {len(articles)}")
            
            news_items = []
            seen = set()
            
            for article in articles:
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
    print(f"[DEBUG] Iniciando análisis con Qwen para: {topic}")
    
    api_key = os.getenv('QWEN_API_KEY')
    
    if not api_key:
        print("[DEBUG] ERROR: QWEN_API_KEY no configurada")
        return None, "API key no configurada"
    
    print(f"[DEBUG] QWEN_API_KEY encontrada: {api_key[:8]}...")
    
    news_text = ""
    if news:
        news_text = "\n\nNoticias encontradas:\n" + "\n".join([f"- {n['titulo']}" for n in news[:3]])
    
    prompt = f"""Analiza esta tendencia periodística:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido (sin markdown):
{{
  "puntaje_relevancia": 7,
  "justificacion_puntaje": "Explicación breve del puntaje",
  "hipotesis": "Hipótesis de 2-3 oraciones sobre cómo evolucionará",
  "senales_clave": ["Señal 1", "Señal 2", "Señal 3"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2", "Ángulo 3"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2", "Fuente 3"],
  "titulares_ejemplo": ["Titular 1", "Titular 2", "Titular 3"],
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}

Sé específico y práctico. El puntaje debe ser 1-10."""

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.7, 'max_tokens': 1500}
    }
    
    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=60
        )
        
        print(f"[DEBUG] Qwen response status: {response.status_code}")
        
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
            
            if not analysis_text:
                print(f"[DEBUG] No se pudo extraer texto. Response: {str(result)[:500]}")
                return None, "No se pudo extraer texto"
            
            print(f"[DEBUG] Texto recibido: {len(analysis_text)} caracteres")
            
            analysis_text = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(analysis_text)
                print(f"[DEBUG] JSON parseado exitosamente")
                return analysis, None
            except json.JSONDecodeError as e:
                print(f"[DEBUG] Error parseando JSON: {e}")
                return None, f"Error parseando JSON: {str(e)}"
        else:
            error_msg = f"Error HTTP {response.status_code}: {response.text[:300]}"
            print(f"[DEBUG] {error_msg}")
            return None, error_msg
            
    except requests.exceptions.Timeout:
        print("[DEBUG] Timeout de Qwen API")
        return None, "Timeout de la API"
    except Exception as e:
        print(f"[DEBUG] Error de conexión: {str(e)}")
        return None, f"Error de conexión: {str(e)}"

def generate_simple_analysis(topic, category, region, news):
    return {
        'puntaje_relevancia': 5,
        'justificacion_puntaje': 'Análisis automático (IA no disponible)',
        'hipotesis': f'La tendencia "{topic}" en la categoría {category or "General"} para {region or "Chile"} muestra relevancia periodística. Se recomienda monitorear su evolución.',
        'senales_clave': [
            f'Aumento de menciones sobre "{topic}" en medios',
            'Nuevas propuestas o regulaciones',
            'Cambios en el comportamiento del público'
        ],
        'angulos_periodisticos': [
            f'Impacto económico y social en {region or "Chile"}',
            'Perspectivas de expertos y actores clave',
            'Casos de éxito, fracaso o controversia'
        ],
        'fuentes_sugeridas': [
            'Organismos oficiales y gubernamentales',
            'Expertos y académicos del sector',
            'Datos estadísticos y reportes'
        ],
        'titulares_ejemplo': [
            f"Análisis en profundidad: {topic}",
            f"Las claves de {topic} en {region or 'Chile'}",
            f"Expertos advierten sobre {topic}"
        ],
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
    return jsonify([
        {'topic': t, 'source': 'Tendencias ' + (category if category != 'all' else 'Chile'), 'region': 'Chile'}
        for t in trends[:limit]
    ])

@app.route('/api/debug', methods=['GET'])
def debug():
    qwen_key = os.getenv('QWEN_API_KEY')
    news_key = os.getenv('NEWSAPI_KEY')
    
    return jsonify({
        'qwen_configured': qwen_key is not None,
        'qwen_key_length': len(qwen_key) if qwen_key else 0,
        'qwen_key_starts_with': qwen_key[:8] if qwen_key else 'N/A',
        'newsapi_configured': news_key is not None,
        'newsapi_key_length': len(news_key) if news_key else 0,
        'newsapi_key_starts_with': news_key[:8] if news_key else 'N/A',
        'db_exists': os.path.exists(DB_PATH),
        'timestamp': datetime.now().isoformat()
    })

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
        print(f"\n{'='*60}")
        print(f"[ANALYZE] Iniciando análisis")
        
        data = request.json
        topic = data.get('topic', '').strip()
        category = data.get('category')
        region = data.get('region')
        
        print(f"[ANALYZE] Topic: '{topic}'")
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        # 1. Buscar noticias
        print("[ANALYZE] Paso 1: Buscando noticias...")
        news = search_news(topic, max_results=5)
        print(f"[ANALYZE] Noticias encontradas: {len(news)}")
        
        # 2. Intentar análisis con IA
        print("[ANALYZE] Paso 2: Intentando análisis con Qwen...")
        analysis, error = analyze_with_qwen(topic, category, region, news)
        
        if error or not analysis:
            print(f"[ANALYZE] Error de Qwen: {error}")
            print("[ANALYZE] Usando análisis de fallback...")
            analysis = generate_simple_analysis(topic, category, region, news)
            used_fallback = True
        else:
            print("[ANALYZE] Análisis de Qwen exitoso!")
            used_fallback = False
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news if news else []
        
        score = analysis.get('puntaje_relevancia', 5)
        
        # 3. Guardar
        print(f"[ANALYZE] Paso 3: Guardando en BD (score: {score})...")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO trends (topic, category, region, analysis, score) VALUES (?, ?, ?, ?, ?)',
            (topic, category, region, json.dumps(analysis, ensure_ascii=False), score)
        )
        conn.commit()
        conn.close()
        
        print(f"[ANALYZE] Análisis completado. Fallback: {used_fallback}")
        print(f"{'='*60}\n")
        
        return jsonify({
            'topic': topic,
            'category': category,
            'region': region,
            'analysis': analysis,
            'score': score,
            'used_fallback': used_fallback,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"[ANALYZE] Error crítico: {str(e)}")
        import traceback
        traceback.print_exc()
        
        topic = request.json.get('topic', 'Tema') if request.json else 'Tema'
        analysis = generate_simple_analysis(topic, None, None, [])
        
        return jsonify({
            'topic': topic,
            'analysis': analysis,
            'score': 5,
            'warning': f'Análisis básico por error: {str(e)}'
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
