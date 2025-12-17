#!/usr/bin/env python3
"""
Pre-Deployment Checklist for Atina
Run this before deploying to production

Usage:
    python pre_deploy_check.py
    python pre_deploy_check.py --skip-tests  # Skip automated tests
"""

import sys
import os
import subprocess
import json
from datetime import datetime


class Colors:
    """Terminal colors"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}")
    print(f"{text}")
    print(f"{'='*70}{Colors.END}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def check_env_variables():
    """Check that required environment variables are set"""
    print_header("1. Checking Environment Variables")
    
    required_vars = [
        'DATABASE_URL',
        'CLAUDE_API_KEY',
        'KAPSO_API_KEY',
        'WHATSAPP_PHONE_NUMBER',
        'WEBHOOK_VERIFY_TOKEN',
        'POSTHOG_API_KEY'
    ]
    
    missing = []
    for var in required_vars:
        if os.getenv(var):
            print_success(f"{var} is set")
        else:
            print_error(f"{var} is missing")
            missing.append(var)
    
    if missing:
        print_warning(f"\nMissing {len(missing)} environment variable(s)")
        return False
    
    print_success("\nAll environment variables are set")
    return True


def check_python_version():
    """Check Python version"""
    print_header("2. Checking Python Version")
    
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major == 3 and version.minor >= 8:
        print_success(f"Python {version_str} (✓ >= 3.8)")
        return True
    else:
        print_error(f"Python {version_str} (✗ Need >= 3.8)")
        return False


def check_dependencies():
    """Check that all dependencies are installed"""
    print_header("3. Checking Dependencies")
    
    required_packages = [
        'flask',
        'anthropic',
        'psycopg2',
        'requests',
        'tenacity',
        'google-api-python-client',
        'google-auth',
        'posthog'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package} is installed")
        except ImportError:
            print_error(f"{package} is missing")
            missing.append(package)
    
    if missing:
        print_warning(f"\nMissing {len(missing)} package(s)")
        print_warning("Run: pip install -r requirements.txt")
        return False
    
    print_success("\nAll dependencies are installed")
    return True


def check_file_structure():
    """Check that all required files exist"""
    print_header("4. Checking File Structure")
    
    required_files = [
        'app.py',
        'claude_handler.py',
        'database_handler.py',
        'whatsapp_handler.py',
        'conversational_helper.py',
        'management_handler.py',
        'logger.py',
        'credentials.json'  # Google credentials
    ]
    
    missing = []
    for file in required_files:
        if os.path.exists(file):
            print_success(f"{file} exists")
        else:
            print_error(f"{file} is missing")
            missing.append(file)
    
    if missing:
        print_warning(f"\nMissing {len(missing)} file(s)")
        return False
    
    print_success("\nAll required files exist")
    return True


def run_automated_tests():
    """Run the test suite"""
    print_header("5. Running Automated Tests")
    
    if not os.path.exists('test_suite.py'):
        print_warning("test_suite.py not found, skipping tests")
        return True
    
    try:
        result = subprocess.run(
            ['python', 'test_suite.py'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print_success("All tests passed")
            return True
        else:
            print_error("Some tests failed")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print_error("Tests timed out after 60 seconds")
        return False
    except Exception as e:
        print_error(f"Error running tests: {str(e)}")
        return False


def check_database_connection():
    """Test database connectivity"""
    print_header("6. Checking Database Connection")
    
    try:
        import psycopg2
        
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            print_error("DATABASE_URL not set")
            return False
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        conn.close()
        
        print_success("Database connection successful")
        return True
        
    except Exception as e:
        print_error(f"Database connection failed: {str(e)}")
        return False


def check_api_keys():
    """Validate API keys (basic check)"""
    print_header("7. Validating API Keys")
    
    claude_key = os.getenv('CLAUDE_API_KEY')
    kapso_key = os.getenv('KAPSO_API_KEY')
    
    if claude_key and claude_key.startswith('sk-ant-'):
        print_success("Claude API key format looks valid")
    else:
        print_warning("Claude API key format may be invalid")
    
    if kapso_key and len(kapso_key) > 10:
        print_success("Kapso API key looks valid")
    else:
        print_warning("Kapso API key may be invalid")
    
    print_success("\nAPI key validation complete")
    return True


def lint_code():
    """Run basic linting checks"""
    print_header("8. Running Code Quality Checks")
    
    python_files = [
        'app.py',
        'claude_handler.py',
        'database_handler.py',
        'whatsapp_handler.py',
        'conversational_helper.py',
        'management_handler.py',
        'logger.py'
    ]
    
    issues_found = False
    
    for file in python_files:
        if not os.path.exists(file):
            continue
            
        # Basic syntax check
        try:
            with open(file, 'r') as f:
                compile(f.read(), file, 'exec')
            print_success(f"{file} - syntax OK")
        except SyntaxError as e:
            print_error(f"{file} - syntax error: {e}")
            issues_found = True
    
    if not issues_found:
        print_success("\nNo syntax errors found")
        return True
    else:
        print_error("\nSyntax errors found - fix before deploying")
        return False


def generate_deployment_report():
    """Generate a deployment report"""
    print_header("9. Generating Deployment Report")
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'git_branch': subprocess.run(['git', 'branch', '--show-current'], 
                                     capture_output=True, text=True).stdout.strip(),
        'git_commit': subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                                     capture_output=True, text=True).stdout.strip()
    }
    
    report_file = f"deployment_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(report_file, 'w') as f:
        json.dump(report, indent=2, fp=f)
    
    print_success(f"Deployment report saved: {report_file}")
    return True


def main():
    """Run all pre-deployment checks"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pre-deployment checks for Atina')
    parser.add_argument('--skip-tests', action='store_true', help='Skip automated tests')
    parser.add_argument('--skip-db', action='store_true', help='Skip database check')
    
    args = parser.parse_args()
    
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          ATINA - PRE-DEPLOYMENT CHECKLIST                       ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    checks = []
    
    # Run all checks
    checks.append(("Environment Variables", check_env_variables()))
    checks.append(("Python Version", check_python_version()))
    checks.append(("Dependencies", check_dependencies()))
    checks.append(("File Structure", check_file_structure()))
    
    if not args.skip_tests:
        checks.append(("Automated Tests", run_automated_tests()))
    
    if not args.skip_db:
        checks.append(("Database Connection", check_database_connection()))
    
    checks.append(("API Keys", check_api_keys()))
    checks.append(("Code Quality", lint_code()))
    checks.append(("Deployment Report", generate_deployment_report()))
    
    # Summary
    print_header("SUMMARY")
    
    passed = sum(1 for _, result in checks if result)
    total = len(checks)
    
    for name, result in checks:
        if result:
            print_success(f"{name}")
        else:
            print_error(f"{name}")
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} checks passed{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ ALL CHECKS PASSED - READY TO DEPLOY{Colors.END}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ SOME CHECKS FAILED - FIX BEFORE DEPLOYING{Colors.END}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
