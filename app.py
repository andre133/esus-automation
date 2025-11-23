from flask import Flask, render_template, jsonify
from datetime import datetime
import pandas as pd

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({"status": "online", "timestamp": datetime.now().isoformat()})

# Importante: gunicorn ignora app.run(), mas não causa erro.
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
