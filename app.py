from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import requests
import json

load_dotenv()

app = Flask(__name__)

# Ruta principal
@app.route('/')
def index():
    return render_template('index.html')

# Ruta de análisis
@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        topic = data.get('topic', '')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        api_key = os.getenv('QWEN_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500
        
        # Respuesta de prueba
        return jsonify({
            'topic': topic,
            'analysis': {
                'hipotesis': 'Análisis de prueba - Funciona correctamente',
                'senales_clave': ['Señal 1', 'Señal 2'],
                'angulos_periodisticos': ['Ángulo 1'],
                'fuentes_sugeridas': ['Fuente 1']
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
