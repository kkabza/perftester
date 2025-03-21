# MOO CLI Performance Tester

A web-based interface for testing the MOO CLI tool performance.

## Prerequisites

1. Make sure you have Python 3.7+ installed
2. Windows Subsystem for Linux (WSL2) with Ubuntu 22.04 installed
3. MOO CLI tool installed in your WSL environment

## WSL Setup

1. Install WSL2 and Ubuntu 22.04:
   ```powershell
   wsl --install -d Ubuntu-22.04
   ```

2. After installation, create a directory for the MOO CLI:
   ```bash
   mkdir -p /home/kkabza/cli
   ```

3. Copy your MOO CLI executable to the `/home/kkabza/cli` directory and ensure it's named `moo`

4. Make the MOO CLI executable:
   ```bash
   chmod +x /home/kkabza/cli/moo
   ```

5. Export your WSL environment for portability:
   ```powershell
   # Stop the WSL instance
   wsl --terminate Ubuntu-22.04
   
   # Export the WSL environment to a file
   wsl --export Ubuntu-22.04 Ubuntu-22.04-moo-cli.tar
   ```

6. To import the WSL environment on another PC:
   ```powershell
   # Import the WSL environment
   wsl --import Ubuntu-22.04 C:\path\to\wsl\Ubuntu-22.04 Ubuntu-22.04-moo-cli.tar
   
   # Set Ubuntu-22.04 as the default distribution
   wsl --set-default Ubuntu-22.04
   ```

## Application Setup

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. Start the Flask application:
   ```bash
   python app.py --wsl
   ```
   Note: The `--wsl` flag is required to enable WSL mode for executing MOO commands.

2. Open your web browser and navigate to `http://localhost:5000`

## Features

- Web-based interface for MOO CLI operations
- Login functionality with username and password
- Logout functionality
- Real-time command output display
- Error handling and status feedback
- WSL integration for MOO CLI execution

## Usage

1. Enter your username and password in the provided fields
2. Click "Login" to authenticate
3. Use the available MOO commands:
   - Login: Configure MOO CLI authentication
   - LS: List MOOSE resources
   - GET: Download MOOSE resources
   - PUT: Upload resources to MOOSE
   - SI: Show system information
   - PROJINFO: Display project information
4. Use the "Logout" button to end your session
5. The output section will display the results of each operation

## Troubleshooting

1. If you see "No active session found" errors:
   - Make sure you're logged in to the web interface
   - Try logging out and logging back in

2. If MOO commands fail:
   - Verify that WSL is running: `wsl --status`
   - Check that the MOO CLI is properly installed in `/home/kkabza/cli/`
   - Ensure the MOO executable has proper permissions
   - Run `moo login` to authenticate with MOOSE

3. If WSL is not working:
   - Ensure WSL2 is installed: `wsl --version`
   - Verify Ubuntu-22.04 is installed: `wsl --list --verbose`
   - Make sure virtualization is enabled in your BIOS 