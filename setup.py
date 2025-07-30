#!/usr/bin/env python3
"""
Setup script for Qrew development/testing
"""
import sys
import os
import subprocess

def main():
    """Setup Qrew for development or testing"""
    print("🎵 Qrew Setup Script")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {sys.version}")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Install in development mode
    try:
        print("\n📦 Installing Qrew in development mode...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])
        print("✅ Installation completed successfully")
        
        print("\n🚀 You can now run Qrew with:")
        print("   python -m qrew")
        print("   or simply: qrew")
        
        print("\n📖 Make sure to:")
        print("   1. Install and start Room EQ Wizard (REW)")
        print("   2. Enable REW API on port 4735")
        print("   3. Install VLC Media Player")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
