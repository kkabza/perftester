from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import subprocess
import os
from functools import wraps
from appinsights import AppInsightsClient

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Admin credentials (in production, use proper authentication system)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

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
        result = subprocess.run(['moo', 'logout'], capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({'success': True, 'message': 'MOO logout successful', 'output': result.stdout})
        else:
            return jsonify({'success': False, 'message': 'MOO logout failed', 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/execute-command', methods=['POST'])
@login_required
def execute_command():
    try:
        import time
        start_time = time.time()
        
        data = request.json
        cmd = ['moo'] + data.get('args', [])
        
        # Set timeout for subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        end_time = time.time()
        server_time_ms = (end_time - start_time) * 1000
        
        return jsonify({
            'success': result.returncode == 0,
            'message': 'Command executed successfully' if result.returncode == 0 else 'Command failed',
            'output': result.stdout,
            'error': result.stderr,
            'serverTiming': server_time_ms  # Add server-side timing
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'message': 'Command timed out after 300 seconds',
            'error': 'Timeout'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
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
    app.run(debug=True) 