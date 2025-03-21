from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import subprocess
import os
import time
from functools import wraps
from appinsights import AppInsightsClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Admin credentials (in production, use proper authentication system)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"

# WSL configuration
USE_WSL = False  # Default to False, can be set via command line argument
MOO_LOCATION = os.getenv('MOO_LOCATION', 'moo')  # Default to 'moo' if not specified

def set_wsl_mode(enabled):
    global USE_WSL
    USE_WSL = enabled

def prepare_command(cmd):
    """Prepare command for execution, handling WSL if enabled"""
    if USE_WSL:
        # Use the configured MOO location when using WSL
        if cmd[0] == 'moo':
            cmd[0] = MOO_LOCATION
        return ['wsl'] + cmd
    return cmd

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def measure_execution(func):
    """Decorator to measure execution time of functions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        timestamps = {
            'start': time.time(),
            'pre_execute': None,
            'post_execute': None,
            'end': None
        }
        
        result = func(*args, **kwargs)
        
        if hasattr(result, 'get') and callable(result.get):
            if isinstance(result, dict):
                result['timing'] = timestamps
            else:
                response_data = result.get_json()
                response_data['timing'] = timestamps
                result.set_data(jsonify(response_data).get_data())
        
        return result
    return wrapper

@app.route('/')
def index():
    if 'admin_logged_in' in session:
        return render_template('dashboard.html')
    return render_template('login.html')

@app.route('/admin/login', methods=['POST'])
def admin_login():
    username = request.json.get('username')
    password = request.json.get('password')
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({'success': True, 'message': 'Login successful'})
    return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/moo-login', methods=['POST'])
@login_required
def moo_login():
    try:
        data = request.json
        cmd = ['moo', 'login']
        
        # Add optional arguments based on the request
        if data.get('device_code'):
            cmd.extend(['--device-code'])
        if data.get('interactive'):
            cmd.extend(['--interactive'])
        if data.get('managed_identity'):
            cmd.extend(['--managed-identity'])
        if data.get('service_principal'):
            cmd.extend(['--service-principal'])
        if data.get('refresh'):
            cmd.extend(['--refresh'])
        if data.get('username'):
            cmd.extend(['--username', data['username']])
        if data.get('password'):
            cmd.extend(['--password', data['password']])
            
        cmd = prepare_command(cmd)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({'success': True, 'message': 'MOO login successful', 'output': result.stdout})
        else:
            return jsonify({'success': False, 'message': 'MOO login failed', 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/moo-logout', methods=['POST'])
@login_required
def moo_logout():
    try:
        cmd = prepare_command(['moo', 'logout'])
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({'success': True, 'message': 'MOO logout successful', 'output': result.stdout})
        else:
            return jsonify({'success': False, 'message': 'MOO logout failed', 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/execute-command', methods=['POST'])
@login_required
@measure_execution
def execute_command():
    timestamps = {
        'request_received': time.time(),
        'command_start': None,
        'command_end': None,
        'response_ready': None
    }
    
    try:
        data = request.json
        cmd = ['moo'] + data.get('args', [])
        cmd = prepare_command(cmd)
        
        timestamps['command_start'] = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        timestamps['command_end'] = time.time()
        
        response_data = {
            'success': result.returncode == 0,
            'message': 'Command executed successfully' if result.returncode == 0 else 'Command failed',
            'output': result.stdout,
            'error': result.stderr,
            'timing': {
                'total_time': timestamps['command_end'] - timestamps['request_received'],
                'command_time': timestamps['command_end'] - timestamps['command_start'],
                'server_processing_time': timestamps['command_start'] - timestamps['request_received'],
                'timestamps': timestamps
            }
        }
        
        timestamps['response_ready'] = time.time()
        return jsonify(response_data)
        
    except Exception as e:
        timestamps['error_time'] = time.time()
        return jsonify({
            'success': False,
            'message': str(e),
            'timing': {
                'total_time': timestamps['error_time'] - timestamps['request_received'],
                'timestamps': timestamps
            }
        })

@app.route('/api/search-appinsights', methods=['POST'])
@login_required
def search_appinsights():
    data = request.get_json()
    api_key = data.get('apiKey')
    app_id = data.get('appId')
    command_id = data.get('commandId')
    time_range = data.get('timeRange', '24h')

    if not api_key or not app_id or not command_id:
        return jsonify({
            'success': False,
            'message': 'API Key, Application ID, and Command ID are required'
        }), 400

    try:
        client = AppInsightsClient(api_key, app_id)
        result = client.search_command(command_id, time_range)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='MOO CLI Performance Tester')
    parser.add_argument('-wsl', '--wsl', action='store_true', help='Enable WSL mode to execute MOO commands through WSL')
    args = parser.parse_args()
    
    set_wsl_mode(args.wsl)
    app.run(debug=True) 