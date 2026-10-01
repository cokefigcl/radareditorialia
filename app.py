from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>🐾 ¡Cora está viva y funcionando!</h1><p>Si ves esto, el servidor responde correctamente.</p>"

@app.route('/dashboard')
def dashboard():
    return "<h1>📊 Dashboard de Prueba</h1>"

if __name__ == '__main__':
    # Railway usa la variable de entorno PORT. Si no existe, usa 8080 por defecto.
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Iniciando Cora en el puerto {port}...")
    app.run(host='0.0.0.0', port=port)
