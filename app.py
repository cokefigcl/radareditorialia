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
    {'name': 'Eléctrico', 'icon': ''},
    {'name': 'Automotriz', 'icon': '🚗'},
    {'name': 'Belleza', 'icon': '💄'},
    {'name': 'Minería', 'icon': '⛏️'},
    {'name': 'IA', 'icon': '🤖'},
    {'name': 'Tendencias', 'icon': '📈'},
    {'name': 'Tecnología', 'icon': '💻'},
    {'name': 'Economía', 'icon': '💰'}
]

# Solo Chile por defecto
REGIONS = ['Chile']

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
    region = request.args.get('region', 'Chile')  # Default Chile
    limit = int(request.args.get('limit', 5))
    
    # Solo tendencias de Chile
    trends_chile = [
        "Reforma de pensiones y su impacto en jóvenes",
        "Precio del cobre alcanza nuevos máximos históricos",
        "Sequía en la zona central y nuevas medidas hídricas",
        "Avance de la electromovilidad en transporte público",
        "Nuevas regulaciones para el comercio electrónico",
        "Deuda de los jóvenes y medios de pago digitales",
        "Inteligencia Artificial en el sector minero",
        "Crisis habitacional en Santiago",
        "Transición energética y energías renovables",
        "Educación superior y financiamiento estudiantil"
    ]
    
    return jsonify([{'topic': t, 'source': 'Tendencias Chile', 'region': 'Chile'} for t in trends_chile[:limit]])

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
            
            # Manejar diferentes formatos de respuesta de DashScope
            try:
                # Intentar formato nuevo: output.choices[0].message.content
                if 'output' in result and 'choices' in result['output']:
                    analysis_text = result['output']['choices'][0]['message']['content']
                # Intentar formato antiguo: output.text
                elif 'output' in result and 'text' in result['output']:
                    analysis_text = result['output']['text']
                # Fallback: buscar en output directamente
                elif 'output' in result:
                    analysis_text = str(result['output'])
                else:
                    analysis_text = str(result)
            except (KeyError, IndexError, TypeError) as e:
                print(f"Error parseando respuesta: {e}")
                analysis_text = str(result)
            
            # Limpiar texto
            analysis_text = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(analysis_text)
            except json.JSONDecodeError:
                # Si no es JSON válido, crear análisis básico
                analysis = {
                    'hipotesis': f'La tendencia "{topic}" muestra relevancia en el contexto {region or "chileno"}. Se recomienda monitorear su evolución.',
                    'senales_clave': [
                        f'Aumento de menciones sobre "{topic}" en medios',
                        'Nuevas propuestas legislativas relacionadas',
                        'Cambio en el comportamiento del sector'
                    ],
                    'angulos_periodisticos': [
                        f'Impacto económico y social de "{topic}"',
                        'Perspectivas de expertos y actores clave',
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
        
        # Guardar en BD
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
