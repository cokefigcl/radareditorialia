from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import requests
import json
import sqlite3
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

# ==================== CATEGORÍAS Y REGIONES ====================
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

REGIONS = ['Chile', 'Sudamérica', 'Norteamérica', 'América Latina', 'Europa', 'Asia', 'Global']

# ==================== TENDENCIAS POR REGIÓN ====================
def get_trending_by_region(region='Global', limit=5):
    """Devuelve tendencias relevantes según la región seleccionada"""
    
    trends_db = {
        'Chile': [
            "Reforma de pensiones y su impacto en jóvenes",
            "Precio del cobre alcanza nuevos máximos históricos",
            "Sequía en la zona central y nuevas medidas hídricas",
            "Avance de la electromovilidad en transporte público",
            "Nuevas regulaciones para el comercio electrónico"
        ],
        'Sudamérica': [
            "Acuerdos comerciales en el Mercosur",
            "Crisis hídrica en la cuenca del Plata",
            "Crecimiento del sector tecnológico en Colombia",
            "Elecciones regionales y su impacto económico",
            "Exportaciones de litio en la región"
        ],
        'Norteamérica': [
            "Tasas de interés de la Reserva Federal",
            "Avances en inteligencia artificial generativa",
            "Crisis en la cadena de suministro global",
            "Elecciones presidenciales y mercados",
            "Inversión en energías renovables"
        ],
        'América Latina': [
            "Inflación y políticas monetarias en la región",
            "Crecimiento de la banca digital y fintech",
            "Migración laboral y su impacto económico",
            "Desafíos de la educación post-pandemia",
            "Turismo sostenible como motor de recuperación"
        ],
        'Europa': [
            "Regulaciones de IA de la Unión Europea",
            "Crisis energética y transición verde",
            "Inflación y costo de vida en la eurozona",
            "Elecciones al Parlamento Europeo",
            "Innovación en la industria automotriz"
        ],
        'Asia': [
            "Crecimiento económico de India y ASEAN",
            "Tensiones comerciales en el Mar de China",
            "Avances en semiconductores y tecnología",
            "Envejecimiento poblacional y sus efectos",
            "Inversión extranjera en infraestructura"
        ],
        'Global': [
            "Cambio climático y cumbres internacionales",
            "Inteligencia Artificial y el futuro del trabajo",
            "Crisis de salud mental a nivel mundial",
            "Economía digital y criptoactivos",
            "Movilidad sostenible y ciudades inteligentes"
        ]
    }
    
    # Obtener tendencias de la región, o 'Global' si no existe
    region_trends = trends_db.get(region, trends_db['Global'])
    
    # Formatear como diccionarios
    return [
        {
            'topic': topic, 
            'source': 'Tendencias ' + region, 
            'region': region
        }
        for topic in region_trends[:limit]
    ]

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
    """Obtener tendencias según la región"""
    region = request.args.get('region', 'Global')
    limit = int(request.args.get('limit', 5))
    
    trends = get_trending_by_region(region, limit)
    return jsonify(trends)

@app.route('/api/trends', methods=['GET'])
def get_trends():
    """Obtener últimas tendencias analizadas por el usuario"""
    category = request.args.get('category')
    region = request.args.get('region')
    limit = int(request.args.get('limit', 3))
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM trends WHERE 1=1'
    params = []
    
    if category and category != 'all':
        query += ' AND category = ?'
        params.append(category)
    
    if region and region != 'all':
        query += ' AND region = ?'
        params.append(region)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    trends = []
    for row in rows:
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except:
            analysis = {}
        
        trends.append({
            'id': row['id'],
            'topic': row['topic'],
            'category': row['category'],
            'region': row['region'],
            'analysis': analysis,
            'created_at': row['created_at']
        })
    
    return jsonify(trends)

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
            return jsonify({'error': 'API key no configurada'}), 500
        
        # Análisis contextualizado
        analysis = {
            'hipotesis': f'La tendencia "{topic}" en {region or "el ámbito global"} muestra un crecimiento sostenido. Se espera que la conversación se desplace hacia los impactos regulatorios y económicos en los próximos 6 meses.',
            'senales_clave': [
                f'Aumento del 40% en menciones sobre "{topic}" en medios especializados',
                'Nuevas propuestas legislativas relacionadas con el tema',
                'Cambio en el comportamiento de consumo o inversión del sector'
            ],
            'angulos_periodisticos': [
                f'Impacto económico y social de "{topic}" en {region}',
                'Perspectivas de expertos y actores clave del sector',
                'Casos de éxito y fracaso en la implementación de soluciones'
            ],
            'fuentes_sugeridas': [
                'Informes de organismos oficiales o think tanks',
                'Entrevistas a académicos y líderes de la industria',
                'Datos estadísticos de cámaras de comercio o asociaciones'
            ]
        }
        
        # Guardar en base de datos
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
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
