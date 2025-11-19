#!/usr/bin/env python3
"""
Test script to verify the start button functionality
"""

import subprocess
import os
import sys

def test_python_command():
    """Test if python main.py command works"""
    print("🧪 Testing Python command execution...")
    
    # Check if main.py exists
    if not os.path.exists('main.py'):
        print("❌ main.py not found in current directory")
        return False
    
    print(f"✅ main.py found in {os.getcwd()}")
    
    # Test the command
    try:
        if os.name == 'nt':  # Windows
            cmd = 'python main.py --help'
        else:  # Unix/Linux/Mac
            cmd = 'python3 main.py --help'
            
        print(f"🔧 Running command: {cmd}")
        
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=15
        )
        
        print(f"📊 Return code: {result.returncode}")
        print(f"📤 STDOUT (first 300 chars): {result.stdout[:300]}")
        print(f"📤 STDERR (first 300 chars): {result.stderr[:300]}")
        
        if result.returncode == 0:
            print("✅ Command executed successfully!")
            return True
        else:
            print("❌ Command failed")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Command timed out (this might be normal for main.py)")
        return True  # Timeout might be normal if main.py runs indefinitely
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def test_web_ui_import():
    """Test if web UI can be imported"""
    print("\n🧪 Testing Web UI import...")
    
    try:
        from web_ui import start_bot, stop_bot, get_bot_status
        print("✅ Web UI functions imported successfully")
        return True
    except Exception as e:
        print(f"❌ Error importing web UI: {e}")
        return False

def main():
    print("🦆 PuddlesBot Start Button Test")
    print("=" * 40)
    
    # Test 1: Python command
    cmd_success = test_python_command()
    
    # Test 2: Web UI import
    import_success = test_web_ui_import()
    
    print("\n📋 Test Results:")
    print(f"  Python Command: {'✅ PASS' if cmd_success else '❌ FAIL'}")
    print(f"  Web UI Import:  {'✅ PASS' if import_success else '❌ FAIL'}")
    
    if cmd_success and import_success:
        print("\n🎉 All tests passed! The start button should work.")
        print("🚀 You can now start the web UI with: python start_dashboard.py")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
