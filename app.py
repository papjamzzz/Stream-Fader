from flask import Flask, render_template, jsonify, request
from engine import get_top_content

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/content')
def content():
    force = request.args.get('force', 'false') == 'true'
    try:
        return jsonify(get_top_content(force=force))
    except Exception as e:
        return jsonify({'movies': [], 'tv': [], 'error': str(e), 'fetched_at': None}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5556, debug=False)
