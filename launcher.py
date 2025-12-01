#!/usr/bin/env python3
"""
Mentanova Application Launcher
Starts backend, frontend, and required services without Docker
"""

import os
import sys
import subprocess
import time
import signal
import platform
from pathlib import Path
from typing import List, Optional

class Color:
    """ANSI color codes"""
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

class MentanovaLauncher:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.backend_dir = self.project_root / "backend"
        self.frontend_dir = self.project_root / "frontend"
        self.processes: List[subprocess.Popen] = []
        self.is_windows = platform.system() == "Windows"
        
    def print_info(self, message: str):
        print(f"{Color.BLUE}ℹ {message}{Color.END}")
        
    def print_success(self, message: str):
        print(f"{Color.GREEN}✓ {message}{Color.END}")
        
    def print_warning(self, message: str):
        print(f"{Color.YELLOW}⚠ {message}{Color.END}")
        
    def print_error(self, message: str):
        print(f"{Color.RED}✗ {message}{Color.END}")
        
    def print_header(self, message: str):
        print(f"\n{Color.BOLD}{Color.BLUE}{'='*60}{Color.END}")
        print(f"{Color.BOLD}{Color.BLUE}{message.center(60)}{Color.END}")
        print(f"{Color.BOLD}{Color.BLUE}{'='*60}{Color.END}\n")

    def check_prerequisites(self) -> bool:
        """Check if all required software is installed"""
        self.print_header("Checking Prerequisites")
        
        checks = {
            "Python 3.11+": ["python", "--version"],
            "Node.js": ["node", "--version"],
            "npm": ["npm", "--version"],
            "PostgreSQL": ["psql", "--version"],
            "Redis": ["redis-cli", "--version"] if not self.is_windows else ["redis-server", "--version"],
        }
        
        all_ok = True
        for name, command in checks.items():
            try:
                result = subprocess.run(
                    command, 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split('\n')[0]
                    self.print_success(f"{name}: {version}")
                else:
                    self.print_error(f"{name}: Not found")
                    all_ok = False
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.print_error(f"{name}: Not found or not in PATH")
                all_ok = False
                
        return all_ok

    def setup_database(self):
        """Initialize PostgreSQL database"""
        self.print_header("Setting up Database")
        
        # Database connection details
        db_name = "mentanova_db"
        db_user = "mentanova_user"
        db_password = "mentanova_secure_pass_2024"
        
        # Check if database exists
        try:
            check_cmd = f'psql -U postgres -lqt | cut -d \\| -f 1 | grep -qw {db_name}'
            if self.is_windows:
                check_cmd = f'psql -U postgres -c "SELECT 1 FROM pg_database WHERE datname=\'{db_name}\'"'
            
            # Create database and user
            commands = [
                f"CREATE USER {db_user} WITH PASSWORD '{db_password}';",
                f"CREATE DATABASE {db_name} OWNER {db_user};",
                f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};",
            ]
            
            for cmd in commands:
                try:
                    subprocess.run(
                        ["psql", "-U", "postgres", "-c", cmd],
                        capture_output=True,
                        text=True
                    )
                except Exception as e:
                    self.print_warning(f"Database setup: {e}")
            
            # Install extensions
            ext_commands = [
                "CREATE EXTENSION IF NOT EXISTS vector;",
                "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
                "CREATE EXTENSION IF NOT EXISTS btree_gin;",
            ]
            
            for cmd in ext_commands:
                subprocess.run(
                    ["psql", "-U", db_user, "-d", db_name, "-c", cmd],
                    capture_output=True,
                    text=True
                )
            
            self.print_success("Database initialized successfully")
            
        except Exception as e:
            self.print_error(f"Database setup failed: {e}")
            self.print_info("Please ensure PostgreSQL is running and you have admin access")

    def setup_backend(self):
        """Setup Python backend"""
        self.print_header("Setting up Backend")
        
        os.chdir(self.backend_dir)
        
        # Create virtual environment
        venv_path = self.backend_dir / "venv"
        if not venv_path.exists():
            self.print_info("Creating virtual environment...")
            subprocess.run([sys.executable, "-m", "venv", "venv"])
            self.print_success("Virtual environment created")
        
        # Determine pip path
        pip_path = venv_path / ("Scripts" if self.is_windows else "bin") / "pip"
        
        # Install dependencies
        self.print_info("Installing Python dependencies...")
        subprocess.run([str(pip_path), "install", "-r", "requirements.txt"])
        self.print_success("Backend dependencies installed")
        
        # Run database migrations
        python_path = venv_path / ("Scripts" if self.is_windows else "bin") / "python"
        alembic_path = venv_path / ("Scripts" if self.is_windows else "bin") / "alembic"
        
        if alembic_path.exists():
            self.print_info("Running database migrations...")
            subprocess.run([str(alembic_path), "upgrade", "head"])
            self.print_success("Database migrations completed")
        
        os.chdir(self.project_root)

    def setup_frontend(self):
        """Setup React frontend"""
        self.print_header("Setting up Frontend")
        
        os.chdir(self.frontend_dir)
        
        # Install dependencies
        if not (self.frontend_dir / "node_modules").exists():
            self.print_info("Installing Node dependencies...")
            subprocess.run(["npm", "install"])
            self.print_success("Frontend dependencies installed")
        
        os.chdir(self.project_root)

    def start_redis(self) -> Optional[subprocess.Popen]:
        """Start Redis server"""
        self.print_info("Starting Redis server...")
        try:
            if self.is_windows:
                process = subprocess.Popen(
                    ["redis-server"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                process = subprocess.Popen(
                    ["redis-server", "--daemonize", "yes"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            time.sleep(2)
            self.print_success("Redis server started on port 6379")
            return process
        except Exception as e:
            self.print_error(f"Failed to start Redis: {e}")
            return None

    def start_backend(self) -> subprocess.Popen:
        """Start FastAPI backend"""
        self.print_info("Starting Backend server...")
        
        venv_path = self.backend_dir / "venv"
        python_path = venv_path / ("Scripts" if self.is_windows else "bin") / "python"
        
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.backend_dir)
        
        process = subprocess.Popen(
            [str(python_path), "-m", "uvicorn", "app.main:app", 
             "--host", "0.0.0.0", "--port", "8000", "--reload"],
            cwd=self.backend_dir,
            env=env
        )
        
        time.sleep(3)
        self.print_success("Backend server started at http://localhost:8000")
        return process

    def start_frontend(self) -> subprocess.Popen:
        """Start React frontend"""
        self.print_info("Starting Frontend server...")
        
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=self.frontend_dir,
            shell=self.is_windows
        )
        
        time.sleep(3)
        self.print_success("Frontend server started at http://localhost:5173")
        return process

    def cleanup(self, signum=None, frame=None):
        """Cleanup and stop all processes"""
        self.print_header("Shutting Down")
        
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        self.print_success("All services stopped")
        sys.exit(0)

    def run(self):
        """Main launcher logic"""
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)
        
        try:
            # Check prerequisites
            if not self.check_prerequisites():
                self.print_error("Missing prerequisites. Please install required software.")
                sys.exit(1)
            
            # Setup components
            self.setup_database()
            self.setup_backend()
            self.setup_frontend()
            
            # Start services
            self.print_header("Starting Services")
            
            redis_process = self.start_redis()
            if redis_process:
                self.processes.append(redis_process)
            
            backend_process = self.start_backend()
            self.processes.append(backend_process)
            
            frontend_process = self.start_frontend()
            self.processes.append(frontend_process)
            
            # Print access info
            self.print_header("Mentanova is Running!")
            print(f"{Color.GREEN}Frontend:  http://localhost:5173{Color.END}")
            print(f"{Color.GREEN}Backend:   http://localhost:8000{Color.END}")
            print(f"{Color.GREEN}API Docs:  http://localhost:8000/docs{Color.END}")
            print(f"\n{Color.YELLOW}Press Ctrl+C to stop all services{Color.END}\n")
            
            # Keep running
            while True:
                time.sleep(1)
                # Check if any process died
                for process in self.processes:
                    if process.poll() is not None:
                        self.print_error(f"Process {process.pid} died unexpectedly")
                        self.cleanup()
                        
        except KeyboardInterrupt:
            self.cleanup()
        except Exception as e:
            self.print_error(f"Error: {e}")
            self.cleanup()


if __name__ == "__main__":
    launcher = MentanovaLauncher()
    launcher.run()