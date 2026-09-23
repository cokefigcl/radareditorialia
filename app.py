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
    {'name': 'Eléctrico', 'icon': ''},
    {'name': 'Automotriz', 'icon': ''},
    {'name': 'Belleza', 'icon': '💄'},
    {'name': 'Minería', 'icon': '️'},
    {'name': 'IA', 'icon': ''},
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
    """Busca noticias usando NewsAPI o GDELT"""
    
    # Intentar con NewsAPI primero (si está configurada)
    newsapi_key = os.getenv('NEWSAPI_KEY')
    if newsapi_key:
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
            
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
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
                    return news_items
        except:
            pass
    
    # Fallback a GDELT
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': topic,
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=7)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': max_results * 3,
            'sourcelang': 'spa'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            
            news_items = []
            seen = set()
            
            for article in articles:
                title = article.get('title', '').strip()
                if title and title not in seen and len(title) > 10:
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
    except:
        pass
    
    return []

# ==================== ANÁLISIS CON IA ====================

def analyze_with_qwen(topic, category, region, news):
    """Genera análisis usando Qwen"""
    api_key = os.getenv('QWEN_API_KEY')
    
    if not api_key:
        return None
    
    news_text = ""
    if news:
        news_text = "\n\nNoticias encontradas:\n" + "\n".join([f"- {n['titulo']}" for n in news[:3]])
    
    prompt = f"""Analiza esta tendencia:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON:
{{
  "puntaje_relevancia": 7,
  "justificacion_puntaje": "Explicación breve",
  "hipotesis": "Hipótesis de 2-3 oraciones",
  "senales_clave": ["Señal 1", "Señal 2"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2"],
  "titulares_ejemplo": ["Titular 1", "Titular 2"],
  "noticias_reales": {json.dumps(news, ensure_ascii=False)}
}}"""

    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'qwen-plus',
                'input': {'messages': [{'role': 'user', 'content': prompt}]},
                'parameters': {'temperature': 0.7, 'max_tokens': 1000}
            },
            timeout=45
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('output', {}).get('choices', [{}])[0].get('message', {}).get('content', '')
            text = text.replace('```json', '').replace('```', '').strip()
            
            try:
                return json.loads(text)
            except:
                return None
    except:
        pass
    
    return None

def generate_simple_analysis(topic, category, region, news):
    """Genera análisis simple cuando Qwen falla"""
    return {
        'puntaje_relevancia': 5,
        'justificacion_puntaje': 'Análisis automático',
        'hipotesis': f'La tendencia "{topic}" en {region or "Chile"} muestra relevancia. Se recomienda monitorear.',
        'senales_clave': [
            f'Aumento de menciones sobre "{topic}"',
            'Nuevas regulaciones o propuestas',
            'Cambios en el comportamiento'
        ],
        'angulos_periodisticos': [
            f'Impacto en {region or "Chile"}',
            'Perspectivas de expertos',
            'Casos relevantes'
        ],
        'fuentes_sugeridas': [
            'Organismos oficiales',
            'Expertos del sector',
            'Datos estadísticos'
        ],
        'titulares_ejemplo': [
            f"Análisis: {topic}",
            f"Las claves de {topic}"
        ],
        'noticias_reales': news
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
        data = request.json
        topic = data.get('topic', '').strip()
        category = data.get('category')
        region = data.get('region')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        # 1. Buscar noticias
        news = search_news(topic, max_results=5)
        
        # 2. Intentar análisis con IA
        analysis = analyze_with_qwen(topic, category, region, news)
        
        # 3. Si falla, análisis simple
        if not analysis:
            analysis = generate_simple_analysis(topic, category, region, news)
        
        # 4. Asegurar campos
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news
        
        score = analysis.get('puntaje_relevancia', 5)
        
        # 5. Guardar
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO trends (topic, category, region, analysis, score) VALUES (?, ?, ?, ?, ?)',
            (topic, category, region, json.dumps(analysis, ensure_ascii=False), score)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'topic': topic,
            'category': category,
            'region': region,
            'analysis': analysis,
            'score': score,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        topic = request.json.get('topic', 'Tema') if request.json else 'Tema'
        analysis = generate_simple_analysis(topic, None, None, [])
        
        return jsonify({
            'topic': topic,
            'analysis': analysis,
            'score': 5,
            'warning': 'Análisis básico por error técnico'
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
