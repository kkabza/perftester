from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import subprocess
import os
import time
import uuid
import tempfile
import shutil
from functools import wraps
from appinsights import AppInsightsClient
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# User credentials
USERS = {
    'admin': {'password': 'password', 'role': 'admin'},
    'tester1': {'password': 'tester1', 'role': 'user'},
    'tester2': {'password': 'tester2', 'role': 'user'}
}

# WSL configuration
USE_WSL = True  # Default to True since we're using WSL
MOO_LOCATION = os.getenv('MOO_LOCATION', '/home/kkabza/cli/moo')  # Update to correct path

# Store WSL sessions and their environments
wsl_sessions = {}

def set_wsl_mode(enabled):
    global USE_WSL
    USE_WSL = enabled

def authenticate_user(username, password):
    """Authenticate user against the USERS dictionary"""
    if username in USERS and USERS[username]['password'] == password:
        return {
            'user_id': str(uuid.uuid4()),
            'username': username,
            'role': USERS[username]['role']
        }
    return None

def prepare_command(cmd, use_sudo=False):
    """Prepare the command for execution."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    
    # Always use ./moo in WSL since we cd to the directory
    if cmd[0] == 'moo':
        cmd[0] = './moo'
    
    if use_sudo:
        sudo_password = os.getenv('SUDO_PASSWORD')
        if sudo_password:
            # Properly handle sudo with password
            escaped_password = sudo_password.replace('"', '\\"')
            return ['echo', f'"{escaped_password}"', '|', 'sudo', '-S', '-E'] + cmd
        else:
            raise ValueError("Sudo password not found in environment variables")
    
    return cmd

def create_wsl_session(user_id, username):
    """Create a new WSL session with isolated environment for a user"""
    session_id = str(uuid.uuid4())
    
    # Create unique home directory for the user
    user_home = Path(tempfile.gettempdir()) / f"moo_cli_{user_id}"
    user_home.mkdir(parents=True, exist_ok=True)
    
    try:
        # Create necessary directories
        (user_home / '.moo').mkdir(parents=True, exist_ok=True)
        (user_home / '.cache' / 'moo').mkdir(parents=True, exist_ok=True)
        
        # Store session info without creating a persistent process
        wsl_sessions[user_id] = {
            'session_id': session_id,
            'created_at': time.time(),
            'home_dir': str(user_home),
            'username': username
        }
        
        return session_id
        
    except Exception as e:
        # Clean up if something goes wrong
        shutil.rmtree(user_home, ignore_errors=True)
        raise Exception(f"Failed to create WSL session: {str(e)}")

def execute_wsl_command(cmd, user_id):
    """Execute a command in WSL with user's isolated environment"""
    if user_id not in wsl_sessions:
        raise Exception("No active session found")
    
    session = wsl_sessions[user_id]
    user_home = session['home_dir']
    
    # Convert Windows path to WSL path format
    wsl_home = '/mnt/c' + user_home[2:].replace('\\', '/')
    
    # Ensure we use ./moo for the command if it starts with moo
    if cmd[0] == 'moo':
        cmd[0] = './moo'
    
    print(f"[DEBUG] Executing command: {' '.join(cmd)}")  # Only show the command being executed
    
    # Create the bash script content
    bash_script = f"""#!/bin/bash
cd /home/kkabza/cli || exit 1
export HOME="{wsl_home}"
export MOO_USER_HOME="{wsl_home}"
export MOO_CONFIG_DIR="{wsl_home}/.moo"
export MOO_CACHE_DIR="{wsl_home}/.cache/moo"
export WSL_USER_HOME="{wsl_home}"
export PATH="/home/kkabza/cli:$PATH"
mkdir -p "{wsl_home}/.moo" "{wsl_home}/.cache/moo"

# Execute the command
{' '.join(f"'{str(x)}'" if ' ' in str(x) or any(c in str(x) for c in '@%!') else str(x) for x in cmd)}
"""
    
    # Create a temporary script file
    script_path = Path(user_home) / "moo_command.sh"
    try:
        with open(script_path, "w", newline='\n') as f:
            f.write(bash_script)
        
        # Make the script executable in WSL
        subprocess.run(['wsl', '-d', 'Ubuntu-22.04', 'chmod', '+x', f'/mnt/c{script_path.as_posix()[2:]}'])
        
        # Execute the script
        wsl_cmd = ['wsl', '-d', 'Ubuntu-22.04', 'bash', f'/mnt/c{script_path.as_posix()[2:]}']
        result = subprocess.run(wsl_cmd, capture_output=True, text=True)
        
        # Only show output if there is any
        if result.stdout:
            print(f"Command output:\n{result.stdout}")
        if result.stderr:
            print(f"Command error:\n{result.stderr}")
        
        # If there's no error message but command failed, use stdout as error
        if result.returncode != 0 and not result.stderr and result.stdout:
            result.stderr = result.stdout
            result.stdout = ""
        
        return result
        
    finally:
        # Clean up the temporary script
        try:
            script_path.unlink()
        except:
            pass

def get_wsl_session(user_id):
    """Get or create a WSL session for a user"""
    if user_id not in wsl_sessions:
        return None
    return wsl_sessions[user_id]

def cleanup_wsl_session(user_id):
    """Cleanup WSL session and its environment"""
    if user_id in wsl_sessions:
        session = wsl_sessions[user_id]
        try:
            # Remove user's temporary directory
            shutil.rmtree(session['home_dir'], ignore_errors=True)
            # Remove session from tracking
            del wsl_sessions[user_id]
        except Exception as e:
            print(f"Error cleaning up session for {user_id}: {str(e)}")

def cleanup_old_sessions():
    """Cleanup WSL sessions older than 1 hour"""
    current_time = time.time()
    for user_id in list(wsl_sessions.keys()):
        if current_time - wsl_sessions[user_id]['created_at'] > 3600:  # 1 hour
            cleanup_wsl_session(user_id)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
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
    if 'user_id' in session and 'username' in session:
        return render_template('dashboard.html', username=session['username'], role=session['role'])
    return render_template('login.html')

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = authenticate_user(username, password)
    if user:
        # Generate new user_id for this session
        user_id = str(uuid.uuid4())
        
        # Store user info in session
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = user['role']
        
        # Create new WSL session for user
        create_wsl_session(user_id, username)
        
        return jsonify({
            'success': True,
            'message': f'Welcome {username}!',
            'role': user['role']
        })
    
    return jsonify({
        'success': False,
        'message': 'Invalid credentials'
    }), 401

@app.route('/admin/logout', methods=['POST'])
@login_required
def admin_logout():
    user_id = session['user_id']
    cleanup_wsl_session(user_id)
    session.clear()
    return jsonify({'success': True})

@app.route('/api/moo-login', methods=['POST'])
@login_required
def moo_login():
    try:
        user_id = session['user_id']
        if user_id not in wsl_sessions:
            return jsonify({
                'success': False,
                'message': 'No active session found. Please log in again.',
                'error': 'SESSION_NOT_FOUND'
            }), 401

        data = request.json
        cmd = ['./moo', 'login']  # Use relative path since we cd to the directory
        
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
            cmd.extend(['--ropc', '-u', data['username']])  # Changed to -u flag
        if data.get('password'):
            cmd.extend(['-p', data['password']])  # Changed to -p flag
        
        print(f"Executing MOO login command: {' '.join(cmd)}")  # Debug logging
        result = execute_wsl_command(cmd, user_id)
        
        print(f"Raw command result - stdout: {result.stdout}, stderr: {result.stderr}, returncode: {result.returncode}")  # Additional debug
        
        # Always include both stdout and stderr in the response
        response_data = {
            'success': result.returncode == 0,
            'output': result.stdout.strip() if result.stdout else '',
            'error': result.stderr.strip() if result.stderr else '',
            'message': None
        }
        
        # Set an appropriate message based on the result
        if result.returncode == 0:
            response_data['message'] = 'MOO login successful'
            if not response_data['output']:
                response_data['output'] = 'Login completed successfully'
        else:
            response_data['message'] = 'MOO login failed'
            if not response_data['error'] and result.stdout:
                response_data['error'] = result.stdout
            if not response_data['error']:
                response_data['error'] = 'Login failed with no error message'
                
        print(f"Sending response to UI: {response_data}")  # Debug logging
        return jsonify(response_data)
        
    except Exception as e:
        print(f"MOO login error: {str(e)}")  # Debug logging
        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(e),
            'output': ''
        })

@app.route('/api/moo-logout', methods=['POST'])
@login_required
def moo_logout():
    try:
        user_id = session['user_id']
        if user_id not in wsl_sessions:
            return jsonify({
                'success': False,
                'message': 'No active session found. Please log in again.',
                'error': 'SESSION_NOT_FOUND'
            }), 401

        data = request.json or {}
        cmd = prepare_command(['moo', 'logout'], use_sudo=data.get('use_sudo', False))
        result = execute_wsl_command(cmd, user_id)
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'MOO logout successful',
                'output': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'message': 'MOO logout failed',
                'error': result.stderr,
                'output': result.stdout
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/execute-command', methods=['POST'])
@login_required
@measure_execution
def execute_command():
    user_id = session['user_id']
    
    if user_id not in wsl_sessions:
        return jsonify({
            'success': False,
            'message': 'No active session found. Please log in again.',
            'error': 'SESSION_NOT_FOUND'
        }), 401
    
    data = request.json
    args = data.get('args', [])
    use_sudo = data.get('use_sudo', False)
    
    # Prepare the command
    cmd = prepare_command(args, use_sudo=use_sudo)
    
    start_time = time.time()
    try:
        # Execute command in a fresh WSL process
        result = execute_wsl_command(cmd, user_id)
        
        success = result.returncode == 0
        message = "Command executed successfully" if success else result.stderr
        
        end_time = time.time()
        timing = {
            'total_time': end_time - start_time,
            'command_time': end_time - start_time,
            'server_processing_time': 0
        }
        
        return jsonify({
            'success': success,
            'message': message,
            'output': result.stdout,
            'error': result.stderr,
            'timing': timing,
            'command': ' '.join(cmd)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e),
            'timing': {
                'total_time': time.time() - start_time,
                'command_time': 0,
                'server_processing_time': 0
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

# Run cleanup periodically
@app.before_request
def before_request():
    cleanup_old_sessions()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='MOO CLI Performance Tester')
    parser.add_argument('-wsl', '--wsl', action='store_true', help='Enable WSL mode to execute MOO commands through WSL')
    args = parser.parse_args()
    
    set_wsl_mode(args.wsl)
    app.run(debug=True) 