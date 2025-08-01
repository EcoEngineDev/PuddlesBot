#!/usr/bin/env python3
"""
Quick fix script to remove Mistral model and download TinyLlama instead.
Run this if your bot crashes on startup due to Mistral model issues.
"""

import os
import shutil
from pathlib import Path

def main():
    models_dir = Path("models")
    
    if not models_dir.exists():
        print("❌ No models directory found.")
        return
    
    # Find Mistral models
    mistral_models = list(models_dir.glob("*mistral*.gguf"))
    
    if not mistral_models:
        print("✅ No Mistral models found to remove.")
        return
    
    print(f"🔍 Found Mistral model(s): {[m.name for m in mistral_models]}")
    
    # Ask for confirmation
    response = input("❓ Remove Mistral model(s)? (y/N): ").strip().lower()
    
    if response in ['y', 'yes']:
        for model in mistral_models:
            try:
                os.remove(model)
                print(f"🗑️ Removed: {model.name}")
            except Exception as e:
                print(f"❌ Failed to remove {model.name}: {e}")
        
        print("✅ Mistral models removed!")
        print("💡 The bot will now automatically download a Llama model on next startup.")
        print("🚀 You can now run: python main.py")
    else:
        print("❌ Operation cancelled.")

if __name__ == "__main__":
    main() 