import sqlite3, os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, g

app = Flask(__name__)
app.config['DEBUG'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'qa.db')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT DEFAULT '',
            vote_count INTEGER DEFAULT 0,
            answer_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );
    ''')
    db.commit()
    db.close()

# Initialize DB on startup
init_db()

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/questions', methods=['GET'])
def list_questions():
    sort = request.args.get('sort', 'newest')
    db = get_db()
    order = 'q.created_at DESC' if sort == 'newest' else 'q.vote_count DESC'
    db.execute('UPDATE questions SET answer_count = (SELECT COUNT(*) FROM answers WHERE answers.question_id = questions.id)')
    db.commit()
    rows = db.execute(f'SELECT q.* FROM questions q ORDER BY {order}').fetchall()
    questions = []
    for r in rows:
        answers = db.execute('SELECT * FROM answers WHERE question_id = ? ORDER BY created_at ASC', (r['id'],)).fetchall()
        questions.append({
            'id': r['id'], 'title': r['title'], 'body': r['body'],
            'vote_count': r['vote_count'], 'answer_count': r['answer_count'],
            'created_at': r['created_at'],
            'answers': [{'id': a['id'], 'body': a['body'], 'created_at': a['created_at']} for a in answers]
        })
    return jsonify(questions)

@app.route('/api/questions', methods=['POST'])
def create_question():
    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '标题不能为空'}), 400
    title = data['title'].strip()[:200]
    body = data.get('body', '').strip()[:2000]
    db = get_db()
    db.execute('INSERT INTO questions (title, body, created_at) VALUES (?, ?, ?)', (title, body, now_iso()))
    db.commit()
    return jsonify({'ok': True}), 201

@app.route('/api/questions/<int:qid>/vote', methods=['POST'])
def vote_question(qid):
    data = request.get_json()
    delta = data.get('delta', 1)
    if delta not in (1, -1):
        return jsonify({'error': 'Delta must be 1 or -1'}), 400
    db = get_db()
    db.execute('UPDATE questions SET vote_count = vote_count + ? WHERE id = ?', (delta, qid))
    db.commit()
    row = db.execute('SELECT vote_count FROM questions WHERE id = ?', (qid,)).fetchone()
    return jsonify({'vote_count': row['vote_count'] if row else 0})

@app.route('/api/questions/<int:qid>/answers', methods=['POST'])
def create_answer(qid):
    data = request.get_json()
    if not data or not data.get('body', '').strip():
        return jsonify({'error': '内容不能为空'}), 400
    body = data['body'].strip()[:2000]
    db = get_db()
    db.execute('INSERT INTO answers (question_id, body, created_at) VALUES (?, ?, ?)', (qid, body, now_iso()))
    db.execute('UPDATE questions SET answer_count = answer_count + 1 WHERE id = ?', (qid,))
    db.commit()
    return jsonify({'ok': True}), 201

@app.route('/api/questions/<int:qid>', methods=['DELETE'])
def delete_question(qid):
    db = get_db()
    db.execute('DELETE FROM answers WHERE question_id = ?', (qid,))
    db.execute('DELETE FROM questions WHERE id = ?', (qid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/answers/<int:aid>', methods=['DELETE'])
def delete_answer(aid):
    db = get_db()
    row = db.execute('SELECT question_id FROM answers WHERE id = ?', (aid,)).fetchone()
    if row:
        db.execute('DELETE FROM answers WHERE id = ?', (aid,))
        db.execute('UPDATE questions SET answer_count = answer_count - 1 WHERE id = ?', (row['question_id'],))
        db.commit()
    return jsonify({'ok': True})

if __name__ == '__main__':
    print('=' * 55)
    print('  QA Site is running!')
    print('  Open http://127.0.0.1:5000 in your browser')
    print('=' * 55)
    app.run(host='127.0.0.1', port=5000, debug=True)
