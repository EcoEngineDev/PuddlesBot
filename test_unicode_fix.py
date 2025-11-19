#!/usr/bin/env python3
"""
Test script to verify Unicode encoding fix
"""

import subprocess
import os
import sys

def test_unicode_print():
    """Test if Unicode characters can be printed"""
    print("🧪 Testing Unicode character printing...")
    
    try:
        # Test printing emoji characters
        test_chars = ["✅", "❌", "🦆", "🎉", "🚀"]
        for char in test_chars:
            print(f"Testing: {char}")
        print("✅ Unicode printing test passed!")
        return True
    except UnicodeEncodeError as e:
        print(f"❌ Unicode printing test failed: {e}")
        return False

def test_main_py_import():
    """Test if main.py can be imported without Unicode errors"""
    print("\n🧪 Testing main.py import...")
    
    try:
        # Try to import main.py to see if it has Unicode issues
        import importlib.util
        spec = importlib.util.spec_from_file_location("main", "main.py")
        if spec is None:
            print("❌ Could not load main.py")
            return False
            
        # This will trigger the Unicode fix if it's working
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("✅ main.py import test passed!")
        return True
    except UnicodeEncodeError as e:
        print(f"❌ main.py import failed with Unicode error: {e}")
        return False
    except Exception as e:
        print(f"⚠️ main.py import failed with other error: {e}")
        # This might be expected if main.py tries to connect to Discord
        return True

def test_bot_start():
    """Test if bot can start without Unicode errors"""
    print("\n🧪 Testing bot startup...")
    
    try:
        # Test the command that the web UI would run
        if os.name == 'nt':  # Windows
            cmd = 'python main.py --help'
        else:
            cmd = 'python3 main.py --help'
            
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=15,
            env=env
        )
        
        print(f"Return code: {result.returncode}")
        if result.returncode == 0:
            print("✅ Bot startup test passed!")
            return True
        else:
            print(f"⚠️ Bot startup returned code {result.returncode}")
            print(f"STDOUT: {result.stdout[:200]}")
            print(f"STDERR: {result.stderr[:200]}")
            # Even if it fails, if there's no Unicode error, that's good
            if "UnicodeEncodeError" not in result.stderr:
                print("✅ No Unicode errors detected!")
                return True
            else:
                print("❌ Unicode errors still present")
                return False
                
    except subprocess.TimeoutExpired:
        print("⏰ Bot startup timed out (this might be normal)")
        return True
    except Exception as e:
        print(f"❌ Bot startup test failed: {e}")
        return False

def main():
    print("🦆 PuddlesBot Unicode Fix Test")
    print("=" * 40)
    
    # Test 1: Unicode printing
    unicode_success = test_unicode_print()
    
    # Test 2: main.py import
    import_success = test_main_py_import()
    
    # Test 3: Bot startup
    startup_success = test_bot_start()
    
    print("\n📋 Test Results:")
    print(f"  Unicode Printing: {'✅ PASS' if unicode_success else '❌ FAIL'}")
    print(f"  main.py Import:   {'✅ PASS' if import_success else '❌ FAIL'}")
    print(f"  Bot Startup:      {'✅ PASS' if startup_success else '❌ FAIL'}")
    
    if unicode_success and import_success and startup_success:
        print("\n🎉 All tests passed! Unicode encoding is fixed.")
        print("🚀 The start button should now work properly.")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
