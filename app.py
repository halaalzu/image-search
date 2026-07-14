from flask import Flask, render_template, request, session, jsonify
import json
import configparser
import os
import signal
import webbrowser
from threading import Timer
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename

# Get the base directory of the app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, 
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = 'mysecretkey'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
app.config['SESSION_COOKIE_HTTPONLY'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Load configuration
config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, 'config.ini'))

TRUSTWORTHY_FOLDER = config.get('paths', 'trustworthy_folder', fallback='static/images/trustworthy')
UNTRUSTWORTHY_FOLDER = config.get('paths', 'untrustworthy_folder', fallback='static/images/untrustworthy')
BASELINE_FOLDER = config.get('paths', 'baseline_folder', fallback='static/images/baseline')
QUESTIONS_FILE = config.get('paths', 'questions_file', fallback='text.json')
SESSION_FOLDER = 'sessions'

DEFAULT_DURATION = config.getint('settings', 'duration', fallback=2)
DEFAULT_SET = config.get('settings', 'default_set', fallback='set1')
AUTOMATION_ENABLED = config.getboolean('settings', 'automation', fallback=False)
RECORDING_DURATION = config.getint('settings', 'recording_duration', fallback=5)
FEEDBACK_COUNTDOWN = config.getint('settings', 'feedback_countdown', fallback=3)
AUTOMATION_POPUP_DELAY = config.getint('settings', 'automation_popup_delay', fallback=1)

# Ensure the sessions directory exists
os.makedirs(SESSION_FOLDER, exist_ok=True)

# Load image sets from config
SETS = {}
for set_name in ['set1', 'set2']:
    set_data = config.get('image_sets', set_name, fallback=None)
    if set_data:
        SETS[set_name] = json.loads(set_data)
    else:
        SETS[set_name] = []

# Add cache-busting headers to prevent browser caching
@app.after_request
def add_cache_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    duration = DEFAULT_DURATION
    automation = AUTOMATION_ENABLED
    recording_duration = RECORDING_DURATION
    feedback_countdown = FEEDBACK_COUNTDOWN
    automation_popup_delay = AUTOMATION_POPUP_DELAY

    with open(os.path.join(BASE_DIR, QUESTIONS_FILE)) as f:
        questions = json.load(f)

    def folder_files(folder_name):
        folder_path = os.path.join(BASE_DIR, 'static', 'images', folder_name)
        if not os.path.isdir(folder_path):
            return []
        return sorted(
            filename for filename in os.listdir(folder_path)
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
        )

    def build_sequence():
        layout = [
            ('baseline', 2),
            ('reliable', 3),
            ('unreliable', 3),
            ('reliable', 3),
        ]
        photos = []

        for folder_name, count in layout:
            files = folder_files(folder_name)
            if not files:
                continue

            for i in range(count):
                filename = files[i % len(files)]
                key = f'{folder_name}/{filename}'
                data = questions.get(key, {})
                photos.append({
                    'src': f'images/{key}',
                    'question': data.get('question', ''),
                })

        return photos

    photos = build_sequence()
    
    session['automation'] = automation
    session['photos'] = photos
    session['duration'] = duration
    session['recording_duration'] = recording_duration
    session['feedback_countdown'] = feedback_countdown
    session['automation_popup_delay'] = automation_popup_delay
    session.permanent = True

    return render_template('slideshow.html')

@app.route('/slideshow-data')
def slideshow_data():
    return jsonify({
        'photos': session.get('photos', []),
        'duration': session.get('duration', 2),
        'automation': session.get('automation', False),
        'recordingDuration': session.get('recording_duration', 5),
        'feedbackCountdown': session.get('feedback_countdown', 3),
        'automationPopupDelay': session.get('automation_popup_delay', 1)
    })

@app.route('/get-questions')
def get_questions():
    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)
    return jsonify(questions)

@app.route('/get-session-id', methods=['GET'])
def get_session_id():
    session.permanent = True
    if 'session_id' not in session:
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        session['session_id'] = session_id
        
        session_file = os.path.join(SESSION_FOLDER, f"{session_id}.json")
        session_data = {
            'session_id': session_id,
            'created_at': datetime.now().isoformat(),
            'responses': []
        }
        try:
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            print(f"[SESSION] Created session: {session_id}")
        except Exception as e:
            print(f"[SESSION ERROR] Failed to create session file: {e}")
    
    return {'session_id': session['session_id']}, 200

@app.route('/save-response', methods=['POST'])
def save_response():
    session.permanent = True
    if 'session_id' not in session:
        print("[SESSION ERROR] No active session")
        return {'error': 'No active session'}, 400
    
    data = request.json
    session_id = session['session_id']
    session_file = os.path.join(SESSION_FOLDER, f"{session_id}.json")
    
    try:
        with open(session_file, 'r') as f:
            session_data = json.load(f)
        
        response_entry = {
            'timestamp': datetime.now().isoformat(),
            'image_filename': data.get('image_filename'),
            'question': data.get('question'),
            'user_response': data.get('user_response'), # Received directly as text from the browser!
            'correct_answer': data.get('correct_answer'),
            'is_correct': data.get('is_correct')
        }
        session_data['responses'].append(response_entry)
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        print(f"[SESSION] Saved response for {data.get('image_filename')}: {response_entry['user_response']}")
        return {'status': 'saved'}, 200
    except Exception as e:
        print(f"[SESSION ERROR] Failed to save response: {e}")
        return {'error': str(e)}, 500

@app.route('/done')
def done_page():
    return render_template('done.html')

@app.route('/shutdown', methods=['POST'])
def shutdown():
    def shutdown_server():
        os.kill(os.getpid(), signal.SIGTERM)
    
    from threading import Thread
    thread = Thread(target=shutdown_server)
    thread.daemon = True
    thread.start()
    
    return {'status': 'shutting down'}, 200

def open_in_chrome(url):
    """Try to launch the app in Chrome specifically, falling back to default browser."""
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
        "/usr/bin/google-chrome",  # Linux
        "/usr/bin/google-chrome-stable",
    ]

    for path in chrome_paths:
        if path and os.path.exists(path):
            try:
                webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(path))
                webbrowser.get('chrome').open(url)
                print(f"[BROWSER] Opened in Chrome: {path}")
                return
            except Exception as e:
                print(f"[BROWSER ERROR] Failed to open Chrome at {path}: {e}")

    # Fallback: system default browser (may not be Chrome)
    print("[BROWSER] Chrome not found in known locations, falling back to default browser")
    webbrowser.open(url)

if __name__ == '__main__':
    import os
    
    port = int(os.environ.get('PORT', 8000))
    host = os.environ.get('HOST', '127.0.0.1')
    environment = os.environ.get('ENVIRONMENT', 'development')
    
    if environment == 'development' and host in ('127.0.0.1', 'localhost'):
        def launch():
            open_in_chrome(f'http://localhost:{port}')
        Timer(1.5, launch).start()
    
    if environment == 'development':
        from waitress import serve
        print(f"Starting server on {host}:{port} (Web Speech Mode Active)")
        serve(app, host=host, port=port)
    else:
        print(f"Running in production mode on port {port}")