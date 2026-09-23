from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
from datetime import datetime

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

# TENDENCIAS POR CATEGORÍA
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
    """Devuelve tendencias según la categoría"""
    if category and category != 'all' and category in TRENDS_BY_CATEGORY:
        return TRENDS_BY_CATEGORY[category]
    else:
        # Si es 'all' o no existe, devolver mezcla de todas
        all_trends = []
        for trends in TRENDS_BY_CATEGORY.values():
            all_trends.extend(trends)
        # Mezclar y tomar 5
        import random
        random.shuffle(all_trends)
        return all_trends[:5]

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
        
        prompt = f"""Eres un editor jefe y analista de inteligencia informativa. Analiza esta tendencia:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}

Responde SOLO con JSON válido (sin markdown) con esta estructura:
{{
  "hipotesis": "Hipótesis de 2-3 oraciones",
  "senales_clave": ["Señal 1", "Señal 2", "Señal 3"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2", "Ángulo 3"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2", "Fuente 3"],
  "titulares_ejemplo": ["Titular 1", "Titular 2", "Titular 3"]
}}"""

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
                'max_tokens': 1000
            }
        }
        
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Manejar diferentes formatos de respuesta
            try:
                if 'output' in result and 'choices' in result['output']:
                    analysis_text = result['output']['choices'][0]['message']['content']
                elif 'output' in result and 'text' in result['output']:
                    analysis_text = result['output']['text']
                elif 'output' in result:
                    analysis_text = str(result['output'])
                else:
                    analysis_text = str(result)
            except (KeyError, IndexError, TypeError):
                analysis_text = str(result)
            
            analysis_text = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(analysis_text)
            except json.JSONDecodeError:
                analysis = {
                    'hipotesis': f'La tendencia "{topic}" muestra relevancia en el contexto {region or "chileno"}.',
                    'senales_clave': [
                        f'Aumento de menciones sobre "{topic}" en medios',
                        'Nuevas propuestas legislativas',
                        'Cambio en el comportamiento del sector'
                    ],
                    'angulos_periodisticos': [
                        f'Impacto económico y social de "{topic}"',
                        'Perspectivas de expertos',
                        'Casos de éxito y fracaso'
                    ],
                    'fuentes_sugeridas': [
                        'Organismos oficiales',
                        'Expertos del sector',
                        'Datos estadísticos'
                    ],
                    'titulares_ejemplo': [
                        f"Análisis: {topic} - ¿Qué está pasando?",
                        f"Las claves de {topic} en Chile",
                        f"Expertos advierten sobre {topic}"
                    ]
                }
        else:
            return jsonify({'error': f'Error API Qwen: {response.status_code}'}), 500
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO trends (topic, category, region, analysis) VALUES (?, ?, ?, ?)',
            (topic, category, region, json.dumps(analysis))
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'topic': topic,
            'category': category,
            'region': region,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error en analyze: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
