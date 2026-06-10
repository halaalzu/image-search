from flask import Flask, render_template, request, session, jsonify
import json
import configparser
import os
import signal
import webbrowser
from threading import Timer
from datetime import datetime
import uuid
from faster_whisper import WhisperModel
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
config.read('config.ini')

TRUSTWORTHY_FOLDER = config.get('paths', 'trustworthy_folder', fallback='static/images/trustworthy')
UNTRUSTWORTHY_FOLDER = config.get('paths', 'untrustworthy_folder', fallback='static/images/untrustworthy')
BASELINE_FOLDER = config.get('paths', 'baseline_folder', fallback='static/images/baseline')
QUESTIONS_FILE = config.get('paths', 'questions_file', fallback='text.json')
UPLOAD_FOLDER = config.get('paths', 'upload_folder', fallback='uploads')

DEFAULT_DURATION = config.getint('settings', 'duration', fallback=2)
DEFAULT_SET = config.get('settings', 'default_set', fallback='set1')
AUTOMATION_ENABLED = config.getboolean('settings', 'automation', fallback=False)
RECORDING_DURATION = config.getint('settings', 'recording_duration', fallback=5)
FEEDBACK_COUNTDOWN = config.getint('settings', 'feedback_countdown', fallback=3)
AUTOMATION_POPUP_DELAY = config.getint('settings', 'automation_popup_delay', fallback=1)
WHISPER_MODEL = config.get('settings', 'whisper_model', fallback='base')
WHISPER_DEVICE = config.get('settings', 'whisper_device', fallback='cpu')

# Create uploads and sessions folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
SESSION_FOLDER = 'sessions'
os.makedirs(SESSION_FOLDER, exist_ok=True)

# Load Whisper model
try:
    whisper_model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type="int8")
except Exception as e:
    print(f"Warning: Could not load Whisper model: {e}")
    whisper_model = None

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
    # Load configuration on startup
    duration = DEFAULT_DURATION
    selected_set = DEFAULT_SET
    automation = AUTOMATION_ENABLED
    recording_duration = RECORDING_DURATION
    feedback_countdown = FEEDBACK_COUNTDOWN
    automation_popup_delay = AUTOMATION_POPUP_DELAY

    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)

    photos = []
    for filename in SETS[selected_set]:
        data = questions.get(filename, {})
        photos.append({'src': f'images/{filename}',
                        'question': data.get('question', '')
                        })
    
    session['automation'] = automation
    session['photos'] = photos
    session['duration'] = duration
    session['recording_duration'] = recording_duration
    session['feedback_countdown'] = feedback_countdown
    session['automation_popup_delay'] = automation_popup_delay
    session.permanent = True

    return render_template('training.html')

@app.route('/slideshow')
def slideshow():
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

@app.route('/transcribe', methods=['POST'])
def transcribe():
    if not whisper_model:
        return {'error': 'Whisper model not available'}, 500
    
    if 'audio' not in request.files:
        return {'error': 'No audio file'}, 400
    
    file = request.files['audio']
    if file.filename == '':
        return {'error': 'No file selected'}, 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        segments, info = whisper_model.transcribe(filepath)
        text = "".join([segment.text for segment in segments])
        return {'text': text, 'language': info.language}
    except Exception as e:
        return {'error': str(e)}, 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

@app.route('/get-session-id', methods=['GET'])
def get_session_id():
    """Get or create a session ID for tracking user responses"""
    session.permanent = True
    if 'session_id' not in session:
        # Create new session ID with timestamp
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        session['session_id'] = session_id
        
        # Create session file
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
            print(f"[SESSION] File saved to: {session_file}")
        except Exception as e:
            print(f"[SESSION ERROR] Failed to create session file: {e}")
    
    return {'session_id': session['session_id']}, 200

@app.route('/save-response', methods=['POST'])
def save_response():
    """Save user's response to the session file"""
    session.permanent = True
    if 'session_id' not in session:
        print("[SESSION ERROR] No active session")
        return {'error': 'No active session'}, 400
    
    data = request.json
    session_id = session['session_id']
    session_file = os.path.join(SESSION_FOLDER, f"{session_id}.json")
    
    try:
        # Read existing session data
        with open(session_file, 'r') as f:
            session_data = json.load(f)
        
        # Add response
        response_entry = {
            'timestamp': datetime.now().isoformat(),
            'image_filename': data.get('image_filename'),
            'question': data.get('question'),
            'user_response': data.get('user_response'),
            'correct_answer': data.get('correct_answer'),
            'is_correct': data.get('is_correct')
        }
        session_data['responses'].append(response_entry)
        
        # Write back to file
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        print(f"[SESSION] Saved response for {data.get('image_filename')}: {response_entry['user_response']}")
        return {'status': 'saved'}, 200
    except Exception as e:
        print(f"[SESSION ERROR] Failed to save response: {e}")
        return {'error': str(e)}, 500

@app.route('/done')
def done_page():
    """Display the done page"""
    return render_template('done.html')

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shutdown the server gracefully"""
    def shutdown_server():
        os.kill(os.getpid(), signal.SIGTERM)
    
    # Schedule shutdown in a separate thread to allow response to send
    from threading import Thread
    thread = Thread(target=shutdown_server)
    thread.daemon = True
    thread.start()
    
    return {'status': 'shutting down'}, 200

if __name__ == '__main__':
    import os
    
    # Get port from environment variable (for Render, Heroku, etc.) or default to 8000
    port = int(os.environ.get('PORT', 8000))
    host = os.environ.get('HOST', '127.0.0.1')
    environment = os.environ.get('ENVIRONMENT', 'development')
    
    # Only open browser in local development
    if environment == 'development' and host in ('127.0.0.1', 'localhost'):
        def open_browser():
            webbrowser.open(f'http://localhost:{port}')
        Timer(1.5, open_browser).start()
    
    # Use waitress for development, gunicorn for production
    if environment == 'development':
        from waitress import serve
        print(f"Starting development server on {host}:{port}")
        serve(app, host=host, port=port)
    else:
        # Production - let gunicorn handle it
        print(f"Running in production mode on port {port}")