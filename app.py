from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import json
import sqlite3
from datetime import datetime
import requests

# Cargar variables de entorno
load_dotenv()

# 1. DEFINIR LA APP
app = Flask(__name__)

# 2. CONFIGURAR BASE DE DATOS SQLITE
DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializar base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_trend(topic, analysis):
    """Guardar tendencia en la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO trends (topic, analysis) VALUES (?, ?)',
        (topic, json.dumps(analysis))
    )
    
    conn.commit()
    conn.close()

def get_trends(limit=20):
    """Obtener tendencias recientes"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT topic, analysis, created_at FROM trends ORDER BY created_at DESC LIMIT ?',
        (limit,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            'topic': row['topic'],
            'analysis': json.loads(row['analysis']) if row['analysis'] else {},
            'created_at': row['created_at']
        }
        for row in rows
    ]

# Inicializar DB
init_db()

# 3. RUTA PRINCIPAL
@app.route('/')
def index():
    return render_template('index.html')

# 4. FUNCIÓN PARA ANALIZAR CON QWEN
def analyze_with_qwen(topic):
    """Llama a la API de Qwen para analizar la tendencia"""
    api_key = os.getenv('QWEN_API_KEY')
    
    if not api_key:
        return {'error': 'API key no configurada'}
    
    # Prompt para análisis periodístico
    prompt = f"""Eres un analista de inteligencia informativa experto. Analiza esta tendencia periodística:

TEMA: {topic}

Proporciona un análisis estructurado en formato JSON con:
1. "hipotesis": Tu hipótesis principal sobre cómo evolucionará esta tendencia (máximo 2 oraciones)
2. "senales_clave": Lista de 3-5 señales concretas que deberían monitorearse
3. "angulos_periodisticos": Lista de 3 ángulos periodísticos interesantes para investigar
4. "fuentes_sugeridas": Lista de 3-4 tipos de fuentes que deberían consultarse
5. "riesgos": Posibles riesgos o aspectos controvertidos a considerar

Sé específico, práctico y enfocado en el contexto latinoamericano/chileno cuando aplique. Formato JSON puro."""

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'model': 'qwen-plus',
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.7,
        'max_tokens': 1000
    }
    
    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            analysis_text = result['output']['text']
            
            # Intentar parsear el JSON
            try:
                analysis = json.loads(analysis_text)
            except:
                # Si no es JSON válido, devolver texto plano
                analysis = {
                    'hipotesis': analysis_text,
                    'senales_clave': [],
                    'angulos_periodisticos': [],
                    'fuentes_sugeridas': []
                }
            
            return analysis
        else:
            return {
                'error': f'Error API Qwen: {response.status_code}',
                'details': response.text
            }
            
    except Exception as e:
        return {
            'error': f'Error de conexión: {str(e)}',
            'status': 'failed'
        }

# 5. RUTA DE ANÁLISIS
@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Endpoint para analizar una tendencia con IA"""
    try:
        data = request.json
        topic = data.get('topic', '')
        
        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        
        # Verificar API Key
        api_key = os.getenv('QWEN_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada en Variables de Railway'}), 500
        
        # Analizar con Qwen
        analysis = analyze_with_qwen(topic)
        
        # Guardar en base de datos
        save_trend(topic, analysis)
        
        return jsonify({
            'topic': topic,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 6. RUTA PARA VER HISTORIAL
@app.route('/api/trends', methods=['GET'])
def trends():
    """Obtener tendencias analizadas"""
    return jsonify(get_trends())

# 7. INICIAR EL SERVIDOR
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
