# Qrew_vlc_helper.py
import time
import platform
import subprocess
import shutil
import os
import re
import threading
from pathlib import Path
import Qrew_common

try:
    import vlc          # python-vlc
except ImportError:
    vlc = None          # optional

class VLCPlayer:
    """Non-blocking VLC player that doesn't interfere with messaging/coordination"""
    
    def __init__(self):
        self.current_player = None
        self.current_instance = None
        
    def stop_current(self):
        """Stop any currently playing media"""
        if self.current_player:
            try:
                self.current_player.stop()
                self.current_player.release()
            except:
                pass
            self.current_player = None
            
        if self.current_instance:
            try:
                self.current_instance.release()
            except:
                pass
            self.current_instance = None


def find_sweep_file(channel):
    """
    Locate the .mlp or .mp4 sweep file for the given channel in the stimulus_dir.
    Returns the full path if found, else None.
    Uses regex for precise matching with custom word boundaries.
    """
    if not Qrew_common.stimulus_dir or not os.path.isdir(Qrew_common.stimulus_dir):
        return None

    # Custom pattern that treats common separators as boundaries
    # (?:^|[^A-Za-z0-9]) = start of string OR non-alphanumeric character
    # (?:[^A-Za-z0-9]|$) = non-alphanumeric character OR end of string
    if 'SW' in channel:
        channel = 'LFE'
    
    pattern = r'(?:^|[^A-Za-z0-9])' + re.escape(channel) + r'(?:[^A-Za-z0-9]|$)'
    
    for fname in os.listdir(Qrew_common.stimulus_dir):
        if fname.endswith('.mlp') or fname.endswith('.mp4'):
            name_without_ext = os.path.splitext(fname)[0]
            
            if re.search(pattern, name_without_ext, re.IGNORECASE):
                return os.path.join(Qrew_common.stimulus_dir, fname)

    return None

def play_file_old(filepath, show_interface=False):
    #Play sweep media file using VLC as default, with fallback per OS and auto-detect on Windows.
    system = platform.system()

    try:
        vlc_path = find_vlc_installation()
        
        if vlc_path:
            # Build command arguments
            cmd = [vlc_path, filepath, '--play-and-exit']
            
            if not show_interface:
                cmd.extend(['--intf', 'dummy'])

            if system == 'Windows':
                # Windows-specific: Use DETACHED_PROCESS to prevent blocking
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                CREATE_NO_WINDOW = 0x08000000
                
                creation_flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                if not show_interface:
                    creation_flags |= CREATE_NO_WINDOW
                
                subprocess.Popen(
                    cmd,
                    creationflags=creation_flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL
                )
            else:
                # Non-Windows platforms
                subprocess.Popen(cmd)
            # Add Windows-specific debugging
            if system == "Windows":
                print(f"🔍 VLC Path: {vlc_path}")
                print(f"🔍 File Path: {filepath}")
                print(f"🔍 File Exists: {os.path.exists(filepath)}")
                print(f"🔍 Command: {' '.join(cmd)}")


            interface_msg = "with interface" if show_interface else "headless"
            print(f"✅ Started VLC subprocess ({interface_msg}): {os.path.basename(filepath)}")
            return True
        
        else:
            # Platform-specific fallbacks (all non-blocking)
            if system == "Darwin":  # macOS
                if filepath.lower().endswith(('.wav', '.aiff', '.m4a')):
                    subprocess.Popen(['afplay', filepath])
                    print(f"✅ Started afplay: {os.path.basename(filepath)}")
                else:
                    subprocess.Popen(['open', filepath])
                    print(f"✅ Started with system default: {os.path.basename(filepath)}")
                return True
                
            elif system == "Linux":
                # Try other players
                players = ['mpv', 'mplayer', 'totem']
                for player_cmd in players:
                    if shutil.which(player_cmd):
                        subprocess.Popen([player_cmd, filepath])
                        print(f"✅ Started {player_cmd}: {os.path.basename(filepath)}")
                        return True
                
                # Final fallback
                subprocess.Popen(['xdg-open', filepath])
                print(f"✅ Started with system default: {os.path.basename(filepath)}")
                return True
                
            elif system == "Windows":
                os.startfile(filepath)
                print(f"✅ Started with system default: {os.path.basename(filepath)}")
                return True
        
        return False
        
    except Exception as e:
        print(f"⚠️ Subprocess fallback failed: {e}")
        return False



def find_vlc_installation():
    """Find VLC installation path across different platforms"""
    system = platform.system()
    
    # First check if vlc is in PATH
    vlc_path = shutil.which("vlc")
    if vlc_path:
        return vlc_path
    
    if system == "Windows":
        # Common Windows installation paths
        possible_paths = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\VideoLAN\VLC\vlc.exe"),
            r"D:\Program Files\VideoLAN\VLC\vlc.exe",
            r"D:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
        
        # Also check registry for VLC installation (Windows specific)
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\VideoLAN\VLC"),
            ]
            for hkey, reg_path in reg_paths:
                try:
                    with winreg.OpenKey(hkey, reg_path) as key:
                        install_dir = winreg.QueryValueEx(key, "InstallDir")[0]
                        vlc_exe = os.path.join(install_dir, "vlc.exe")
                        if os.path.exists(vlc_exe):
                            possible_paths.insert(0, vlc_exe)  # Prioritize registry path
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass  # winreg not available on non-Windows
            
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
    elif system == "Darwin":  # macOS
        possible_paths = [
            "/Applications/VLC.app/Contents/MacOS/VLC",
            "/usr/local/bin/vlc",
            "/opt/homebrew/bin/vlc",  # Apple Silicon Homebrew
            "/usr/bin/vlc",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
    elif system == "Linux":
        possible_paths = [
            "/usr/bin/vlc",
            "/usr/local/bin/vlc",
            "/snap/bin/vlc",  # Snap package
            "/var/lib/flatpak/exports/bin/org.videolan.VLC",  # Flatpak
            os.path.expanduser("~/.local/share/flatpak/exports/bin/org.videolan.VLC"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    
    return None

# Global player instance to manage playback
vlc_player = VLCPlayer()

def play_file_vlc_nonblocking(filepath, show_interface=False):
    """Non-blocking VLC playback using python-vlc"""
    try:
        # Stop any current playback
        vlc_player.stop_current()
        
        # Set VLC arguments based on interface preference
        if show_interface:
            vlc_args = [
                '--no-xlib',
                '--play-and-exit',
                '--no-video-title-show',
            ]
        else:
            vlc_args = [
                '--intf', 'dummy',  # No interface
                '--play-and-exit',
                '--no-video-title-show',
                '--quiet',
            ]
        
        # Try to set VLC path if found
        vlc_path = find_vlc_installation()
        if vlc_path:
            # If we found VLC, tell python-vlc where it is
            os.environ['VLC_PLUGIN_PATH'] = os.path.dirname(vlc_path)
        
        # Create VLC instance
        instance = vlc.Instance(vlc_args)
        if not instance:
            raise Exception("Could not create VLC instance")
        
        # Create media player
        player = instance.media_player_new()
        if not player:
            raise Exception("Could not create media player")
        
        # Load media
        media = instance.media_new(filepath)
        if not media:
            raise Exception(f"Could not load media: {filepath}")
        
        player.set_media(media)
        player.audio_set_volume(100)
        
        # Start playback (non-blocking)
        result = player.play()
        if result != 0:
            raise Exception(f"Failed to start playback, error code: {result}")
        
        # Brief wait to ensure playback starts
        #time.sleep(0.5)
        
        # Check if playback actually started
        if player.get_state() in [vlc.State.Error, vlc.State.Ended]:
            raise Exception("Playback failed to start or ended immediately")
        
        # Store references for cleanup later (but don't wait for completion)
        vlc_player.current_player = player
        vlc_player.current_instance = instance
        
        interface_msg = "with interface" if show_interface else "headless"
        print(f"✅ Started VLC playback ({interface_msg}): {os.path.basename(filepath)}")
        
        # Optional: Start a background thread to cleanup when done
        def cleanup_when_done():
            try:
                time.sleep(1)
                # Check periodically if playback is done
                max_wait = 300  # 5 minutes max
                waited = 0
                while waited < max_wait and player.get_state() == vlc.State.Playing:
                    time.sleep(1)
                    waited += 1
                
                # Cleanup
                if player == vlc_player.current_player:  # Only cleanup if it's still current
                    vlc_player.stop_current()
                    
            except Exception as e:
                print(f"Background cleanup error: {e}")
        
        # Start cleanup thread (daemon so it won't prevent app exit)
        cleanup_thread = threading.Thread(target=cleanup_when_done, daemon=True)
        cleanup_thread.start()
        
        return True
        
    except Exception as e:
        print(f"⚠️ python-vlc failed: {e}")
        # Cleanup on error
        vlc_player.stop_current()
        return False

def play_file_subprocess_nonblocking(filepath, show_interface=False):
    """Non-blocking subprocess VLC playback"""
    system = platform.system()
    
    try:
        vlc_path = find_vlc_installation()
        
        if vlc_path:
            # Build command arguments
            cmd = [vlc_path, filepath, '--play-and-exit']
            
            if not show_interface:
                cmd.extend(['--intf', 'dummy'])
            
            # Start VLC process (non-blocking)
            process = subprocess.Popen(cmd, 
                                     stdout=subprocess.DEVNULL, 
                                     stderr=subprocess.DEVNULL)
            
            interface_msg = "with interface" if show_interface else "headless"
            print(f"✅ Started VLC subprocess ({interface_msg}): {os.path.basename(filepath)}")
            return True
        
        else:
            # Platform-specific fallbacks (all non-blocking)
            if system == "Darwin":  # macOS
                if filepath.lower().endswith(('.wav', '.aiff', '.m4a')):
                    subprocess.Popen(['afplay', filepath])
                    print(f"✅ Started afplay: {os.path.basename(filepath)}")
                else:
                    subprocess.Popen(['open', filepath])
                    print(f"✅ Started with system default: {os.path.basename(filepath)}")
                return True
                
            elif system == "Linux":
                # Try other players
                players = ['mpv', 'mplayer', 'totem']
                for player_cmd in players:
                    if shutil.which(player_cmd):
                        subprocess.Popen([player_cmd, filepath])
                        print(f"✅ Started {player_cmd}: {os.path.basename(filepath)}")
                        return True
                
                # Final fallback
                subprocess.Popen(['xdg-open', filepath])
                print(f"✅ Started with system default: {os.path.basename(filepath)}")
                return True
                
            elif system == "Windows":
                os.startfile(filepath)
                print(f"✅ Started with system default: {os.path.basename(filepath)}")
                return True
        
        return False
        
    except Exception as e:
        print(f"⚠️ Subprocess fallback failed: {e}")
        return False

def play_file(filepath, show_interface=False):
    """
    Non-blocking, cross-platform media file player.
    
    Args:
        filepath (str): Path to media file to play
        show_interface (bool): Whether to show VLC interface (default: False for headless)
    
    Returns:
        bool: True if playback started successfully
    """
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    print(f"🎵 Starting playback: {os.path.basename(filepath)} (GUI: {show_interface})")
    
    # If GUI not needed, prefer python-vlc
    if not show_interface:
        # Strategy 1: Try python-vlc (non-blocking)
        if play_file_vlc_nonblocking(filepath, show_interface):
            return True
    
    # Strategy 2: Try subprocess VLC (non-blocking)
    print("🔄 Trying subprocess fallback...")
    if play_file_subprocess_nonblocking(filepath, show_interface):
        return True
    
    print(f"❌ All playback methods failed for: {filepath}")
    return False

def stop_playback():
    """Stop any currently playing VLC media"""
    vlc_player.stop_current()
    print("⏹️ Stopped VLC playback")


# Test function
def test_vlc_nonblocking():
    """Test non-blocking VLC functionality"""
    print("🔍 Testing non-blocking VLC...")
    
    vlc_path = find_vlc_installation()
    if vlc_path:
        print(f"✅ VLC found at: {vlc_path}")
    else:
        print("⚠️ VLC not found in standard locations")
    
    try:
        import vlc
        instance = vlc.Instance(['--intf', 'dummy'])
        if instance:
            print("✅ python-vlc library working")
            instance.release()
        else:
            print("⚠️ python-vlc instance creation failed")
    except Exception as e:
        print(f"⚠️ python-vlc test failed: {e}")
    
    print(f"🖥️ Platform: {platform.system()}")

# Usage example:
if __name__ == "__main__":
    test_vlc_nonblocking()
    
    # Test with a file
    # play_file("path/to/your/media/file.mp4")
