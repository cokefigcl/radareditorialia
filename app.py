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
    {'name': 'Eléctrico', 'icon': '⚡'},
    {'name': 'Automotriz', 'icon': '🚗'},
    {'name': 'Belleza', 'icon': '💄'},
    {'name': 'Minería', 'icon': '️'},
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

# ==================== GDELT: NOTICIAS Y EVOLUCIÓN ====================

def search_gdelt_news(query, max_results=5, days_back=7):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        start_str = start_date.strftime('%Y%m%d%H%M%S')
        end_str = end_date.strftime('%Y%m%d%H%M%S')
        
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        
        params = {
            'query': query,
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': start_str,
            'enddatetime': end_str,
            'maxrecords': max_results * 3,
            'sourcelang': 'spa',
            'sort': 'DateDesc'
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            
            news_items = []
            seen_titles = set()
            
            for article in articles:
                title = article.get('title', '').strip()
                url_article = article.get('url', '')
                source = article.get('domain', '')
                date = article.get('seendate', '')
                
                if title and title not in seen_titles and len(title) > 10:
                    seen_titles.add(title)
                    news_items.append({
                        'titulo': title,
                        'fuente': source,
                        'url': url_article,
                        'fecha': date[:10] if date else ''
                    })
                
                if len(news_items) >= max_results:
                    break
            
            return news_items
        else:
            return []
            
    except Exception as e:
        print(f"Error GDELT: {str(e)}")
        return []

def get_trend_evolution(query, weeks=4):
    """
    Obtiene la evolución del interés en un tema durante las últimas N semanas.
    Consulta GDELT por cada semana y cuenta artículos.
    """
    evolution = []
    end_date = datetime.now()
    
    for i in range(weeks, 0, -1):
        week_end = end_date - timedelta(weeks=i-1)
        week_start = week_end - timedelta(days=7)
        
        start_str = week_start.strftime('%Y%m%d%H%M%S')
        end_str = week_end.strftime('%Y%m%d%H%M%S')
        
        try:
            url = 'https://api.gdeltproject.org/api/v2/doc/doc'
            params = {
                'query': query,
                'mode': 'artlist',
                'format': 'json',
                'startdatetime': start_str,
                'enddatetime': end_str,
                'maxrecords': 200,
                'sourcelang': 'spa'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                count = len(data.get('articles', []))
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

@app.route('/api/news', methods=['GET'])
def get_news():
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 5))
    
    if not query:
        return jsonify({'error': 'Falta el query'}), 400
    
    news = search_gdelt_news(query, limit)
    return jsonify(news)

@app.route('/api/evolution', methods=['GET'])
def get_evolution():
    query = request.args.get('q', '')
    weeks = int(request.args.get('weeks', 4))
    
    if not query:
        return jsonify({'error': 'Falta el query'}), 400
    
    evolution = get_trend_evolution(query, weeks)
    return jsonify(evolution)

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 20))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, topic, category, region, analysis, score, created_at 
        FROM trends 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
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
        topic = data.get('topic', '')
        category = data.get('category')
        region = data.get('region')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        api_key = os.getenv('QWEN_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key de Qwen no configurada'}), 500
        
        # Buscar noticias reales
        real_news = search_gdelt_news(topic, max_results=5, days_back=14)
        
        # Obtener evolución del tema
        evolution = get_trend_evolution(topic, weeks=4)
        
        # Calcular tendencia (si está subiendo o bajando)
        if len(evolution) >= 2:
            first_week = evolution[0]['articulos']
            last_week = evolution[-1]['articulos']
            if last_week > first_week:
                trend_direction = 'subiendo'
                trend_percent = round(((last_week - first_week) / max(first_week, 1)) * 100)
            elif last_week < first_week:
                trend_direction = 'bajando'
                trend_percent = round(((first_week - last_week) / max(first_week, 1)) * 100)
            else:
                trend_direction = 'estable'
                trend_percent = 0
        else:
            trend_direction = 'sin datos'
            trend_percent = 0
        
        news_context = ""
        if real_news:
            news_context = "\n\nNOTICIAS RECIENTES:\n"
            for i, news in enumerate(real_news[:5], 1):
                news_context += f"{i}. {news['titulo']} ({news['fuente']}, {news['fecha']})\n"
        
        evolution_context = f"\n\nEVOLUCIÓN (últimas 4 semanas): {trend_direction} {trend_percent}%\n"
        for e in evolution:
            evolution_context += f"- {e['semana']} ({e['fecha_inicio']}-{e['fecha_fin']}): {e['articulos']} artículos\n"
        
        prompt = f"""Eres un editor jefe y analista de inteligencia informativa. Analiza:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}
{evolution_context}{news_context}
Responde SOLO con JSON válido con esta estructura:
{{
  "puntaje_relevancia": 8,
  "justificacion_puntaje": "Explicación breve",
  "hipotesis": "Hipótesis de 2-3 oraciones",
  "senales_clave": ["Señal 1", "Señal 2", "Señal 3"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2", "Ángulo 3"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2", "Fuente 3"],
  "titulares_ejemplo": ["Titular 1", "Titular 2", "Titular 3"],
  "noticias_reales": {json.dumps(real_news[:5], ensure_ascii=False) if real_news else '[]'}
}}

Puntaje: 1-3 (Baja), 4-6 (Media), 7-8 (Alta), 9-10 (Crítica)"""

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'qwen-plus',
            'input': {
                'messages': [
                    {'role': 'user', 'content': prompt}
                ]
            },
            'parameters': {
                'temperature': 0.7,
                'max_tokens': 1500
            }
        }
        
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=45
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
            except:
                analysis = {
                    'puntaje_relevancia': 5,
                    'justificacion_puntaje': 'Análisis generado',
                    'hipotesis': f'La tendencia "{topic}" muestra relevancia en el contexto {region or "chileno"}.',
                    'senales_clave': ['Aumento de menciones', 'Nuevas regulaciones', 'Cambio en el sector'],
                    'angulos_periodisticos': ['Impacto económico', 'Perspectivas de expertos', 'Casos de éxito'],
                    'fuentes_sugeridas': ['Organismos oficiales', 'Expertos', 'Datos estadísticos'],
                    'titulares_ejemplo': [f"Análisis: {topic}", f"Las claves de {topic}"],
                    'noticias_reales': real_news
                }
        else:
            return jsonify({'error': f'Error API Qwen: {response.status_code}'}), 500
        
        score = analysis.get('puntaje_relevancia', 5)
        
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
            'evolution': evolution,
            'trend_direction': trend_direction,
            'trend_percent': trend_percent,
            'noticias_encontradas': len(real_news),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
