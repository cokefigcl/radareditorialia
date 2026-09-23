from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# 1. DEFINIR LA APP (Esto es lo que faltaba y causaba el error)
app = Flask(__name__)

# 2. RUTA PRINCIPAL (Muestra el HTML)
@app.route('/')
def index():
    return render_template('index.html')

# 3. RUTA DE ANÁLISIS (Recibe el tema y responde)
@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        topic = data.get('topic', '')
        
        # Verificar API Key
        api_key = os.getenv('QWEN_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada en Variables de Railway'}), 500
        
        # RESPUESTA DE PRUEBA (Para confirmar que la conexión funciona)
        # Cuando esto funcione, reemplazaremos esto con la llamada real a Qwen
        return jsonify({
            'topic': topic,
            'analysis': {
                'hipotesis': '¡Conexión exitosa! Tu servidor y API Key están funcionando correctamente.',
                'senales_clave': ['Señal de prueba 1', 'Señal de prueba 2'],
                'angulos_periodisticos': ['Ángulo periodístico de prueba'],
                'fuentes_sugeridas': ['Fuente de prueba 1']
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 4. INICIAR EL SERVIDOR
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
