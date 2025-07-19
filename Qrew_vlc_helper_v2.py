# Qrew_vlc_helper_v2.py – non-blocking VLC wrapper
import os, platform, subprocess, threading, queue, time, shutil, re, signal
from pathlib import Path
from typing import Callable, Optional
import Qrew_common
import Qrew_settings as qs

try:
  #if platform.system() == "Windows":
        #os.add_dll_directory(r'C:\Users\centralmd\Downloads\vlc-3.0.21-win64\vlc-3.0.21')
    import vlc          # python-vlc
except ImportError:
    vlc = None          # optional

# ----------------------------------------------------------------------
class VLCPlayer:
    """
    Play a media file either with python-vlc (libvlc) or by launching the
    VLC executable.  Non-blocking; calls *on_finished* when playback ends.
    """
    def __init__(self):
        self._thread  = None
        self._playing = False
        self._player = None     # libvlc player
        self._instance = None   # libvlc instance
        self._process = None    # subprocess
        self._system = platform.system()


    # -------------------- public entry point --------------------------
    def play(self,
             path: str,
             show_gui: bool            = True,
             backend: str              = "auto",   # "libvlc" | "subprocess" | "auto"
             on_finished: Optional[Callable[[], None]] = None):
        """
        Start playback and return immediately.
        *on_finished* is called in a background thread when playback ends.
        """
        self.stop_and_exit()

        if backend == "auto":
            backend = "libvlc" if vlc else "subprocess"
        try:
            if backend == "libvlc":
                if not vlc:
                    raise RuntimeError("python-vlc not installed")
                self._play_libvlc(path, show_gui, on_finished)
            elif backend == "subprocess":
                self._play_subproc(path, show_gui, on_finished)
            else:
                raise ValueError("backend must be 'libvlc', 'subprocess', or 'auto'")
        except Exception as e:
            print(f"Playback error: {e}")
            self.stop_and_exit()

    # -------------------- libvlc path --------------------------------
    def _play_libvlc(self, path, show_gui, on_finished):
        intf_flag = "" if show_gui else "--intf=dummy"
        self._instance  = vlc.Instance("--play-and-exit", intf_flag)
        self._player    = self._instance.media_player_new()
        self._player.set_media(self._instance.media_new(Path(path).as_posix()))
        self._player.audio_set_volume(100)
        # Finish queue + callback
        done_q = queue.Queue()

        def _on_end(ev):
            done_q.put(True)

        evmgr = self._player.event_manager()
        evmgr.event_attach(vlc.EventType.MediaPlayerEndReached, _on_end)
        self._player.play()
        self._playing = True

        # watchdog thread waits for queue then fires callback
        def _watch():
            done_q.get()               # blocks until signal
            self._playing = False
            if on_finished:
                on_finished()
            player.release()
            self.stop_and_exit()

        threading.Thread(target=_watch, daemon=True).start()

    # -------------------- subprocess path ----------------------------
    def _play_subproc(self, path, show_gui, on_finished):
        vlc_path = self._find_vlc_exe()
        if not vlc_path:
            raise RuntimeError("VLC executable not found")

        cmd = [vlc_path, "--play-and-exit", "--auhal-volume=256", path]
        if not show_gui:
            cmd += ["--intf", "dummy"]

        # Ensure process group for better termination on Unix-like systems
        if self._system != "Windows":
            self._process = subprocess.Popen(cmd, start_new_session=True)
        else:
            self._process = subprocess.Popen(cmd)

        self._playing = True

        def _watch():
            self._process.wait()
            self._playing = False
            if on_finished:
                on_finished()
            self.stop_and_exit()

        threading.Thread(target=_watch, daemon=True).start()
    
    def stop_and_exit(self):
        try:
            proc = self._process  # local copy

            if self._player and hasattr(self._player, 'stop'):
                try:
                    self._player.stop()
                except Exception as e:
                    print(f"Error stopping libvlc player: {e}")

            if self._player:
                try:
                    self._player.release()
                except Exception as e:
                    print(f"Error releasing libvlc player: {e}")
                self._player = None

            if self._instance:
                try:
                    self._instance.release()
                except Exception as e:
                    print(f"Error releasing libvlc instance: {e}")
                self._instance = None

            if proc is not None and isinstance(proc, subprocess.Popen):
                try:
                    if proc.poll() is None:
                        try:
                            if self._system == 'Windows':
                                subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)])
                            else:
                                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                                time.sleep(0.1)
                                if proc.poll() is None:
                                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except Exception as e:
                            print(f"Error terminating process: {e}")
                    else:
                        print("Process already terminated")
                except Exception as e:
                    print(f"Error checking process status: {e}")
            else:
                print("No process to terminate or invalid process object")

            self._process = None
            self._playing = False

        except Exception as e:
            print(f"Unexpected error in stop_and_exit: {e}")


    # -------------------- helpers ------------------------------------
    @staticmethod
    def _find_vlc_exe() -> Optional[str]:
        """
        Comprehensive cross-platform VLC executable finder
        
        Returns:
            str: Path to VLC executable or 'vlc' if found in PATH
            None: If no VLC executable found
        """
        # Try PATH first (most reliable method)
        vlc_path = shutil.which("vlc")
        if vlc_path:
            return vlc_path

        system = platform.system()
        
        # Expanded macOS search paths
        if system == "Darwin":
            possible_paths = [
                "/Applications/VLC.app/Contents/MacOS/VLC",
                "/opt/homebrew/bin/vlc",
                "/usr/local/bin/vlc",
                "/Applications/VLC.app/Contents/MacOS/VLC.app/Contents/MacOS/VLC",
                os.path.expanduser("~/Applications/VLC.app/Contents/MacOS/VLC"),
                "/Applications/VLC.app/Contents/MacOS/VLC"
            ]
        
        # Expanded Windows search paths
        elif system == "Windows":
            possible_drives = ['C:', 'D:']
            possible_program_files = [
                os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
            ]
            possible_paths = []
            for drive in possible_drives:
                for pf in possible_program_files:
                    possible_paths.extend([
                        rf"{pf}\VideoLAN\VLC\vlc.exe",
                        rf"{drive}\Program Files\VideoLAN\VLC\vlc.exe",
                        rf"{drive}\Program Files (x86)\VideoLAN\VLC\vlc.exe"
                    ])
        
        # Expanded Linux search paths
        elif system == "Linux":
            possible_paths = [
                "/usr/bin/vlc",
                "/usr/local/bin/vlc",
                "/snap/bin/vlc",
                "/opt/vlc/bin/vlc",
                os.path.expanduser("~/.local/bin/vlc")
            ]
        
        else:
            possible_paths = []

        # Additional PATH search
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        possible_paths.extend([os.path.join(path_dir, "vlc") for path_dir in path_dirs])

        # Check each possible path
        for p in possible_paths:
            # Expand user directory and normalize path
            full_path = os.path.abspath(os.path.expanduser(p))
            if os.path.exists(full_path) and os.access(full_path, os.X_OK):
                return full_path

        return None


    # -------------------- status -------------------------------------
    def is_playing(self) -> bool:
        return self._playing


# ----------------------------------------------------------------------
# Global player instance
_global_player = VLCPlayer()

def find_sweep_file(channel):
    """
    Locate the .mlp or .mp4 sweep file for the given channel in the stimulus_dir.
    Returns the full path if found, else None.
    Uses regex for precise matching with custom word boundaries.
    """
    if not Qrew_common.stimulus_dir or not os.path.isdir(Qrew_common.stimulus_dir):
        return None
    if 'SW' in channel:
        channel = 'LE'
    # Custom pattern that treats common separators as boundaries
    # (?:^|[^A-Za-z0-9]) = start of string OR non-alphanumeric character
    # (?:[^A-Za-z0-9]|$) = non-alphanumeric character OR end of string
    pattern = r'(?:^|[^A-Za-z0-9])' + re.escape(channel) + r'(?:[^A-Za-z0-9]|$)'
    
    for fname in os.listdir(Qrew_common.stimulus_dir):
        if fname.endswith('.mlp') or fname.endswith('.mp4'):
            name_without_ext = os.path.splitext(fname)[0]
            
            if re.search(pattern, name_without_ext, re.IGNORECASE):
                return os.path.join(Qrew_common.stimulus_dir, fname)

    return None

def play_file(filepath):
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
    
    try:
        backend   = qs.get("vlc_backend", "auto")
        show_interface  = qs.get("show_vlc_gui", False)
        print(f"🎵 Starting playback: {os.path.basename(filepath)} (GUI: {show_interface}, Backend: {backend})")
        
        _global_player.play(
            path=filepath,
            show_gui=show_interface,
            backend=backend,
            on_finished=lambda: print(f"✅ Finished playing: {os.path.basename(filepath)}")
        )
        return True
        
    except Exception as e:
        print(f"❌ Playback failed: {e}")
        return False

def play_file_with_callback(filepath, completion_callback=None):
    """
    Play file with completion callback for RTA verification.
    
    Args:
        filepath (str): Path to media file to play
        show_interface (bool): Whether to show VLC interface
        completion_callback (callable): Function to call when playback completes
    
    Returns:
        bool: True if playback started successfully
    """
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    try:
        backend   = qs.get("vlc_backend", "auto")
        show_interface  = qs.get("show_vlc_gui", False)        
        print(f"🎵 Starting callback playback: {os.path.basename(filepath)} (GUI: {show_interface}, Backend: {backend})")
            
        def on_finished():
            print(f"✅ Callback playback finished: {os.path.basename(filepath)}")
            if completion_callback:
                try:
                    completion_callback()
                except Exception as e:
                    print(f"Error in completion callback: {e}")
        
        _global_player.play(
            path=filepath,
            show_gui=show_interface,
            backend=backend,
            on_finished=on_finished
        )
        return True
        
    except Exception as e:
        print(f"❌ Callback playback failed: {e}")
        return False

def stop_playback():
    """Stop any currently playing media"""
    # Note: Your VLCPlayer doesn't have a stop method, but we can check status
    if _global_player.is_playing():
        print("⏹️ Media is still playing (cannot force stop with current implementation)")
    else:
        print("⏹️ No media currently playing")

def is_playing():
    """Check if media is currently playing"""
    return _global_player.is_playing()

def stop_vlc_and_exit():
    """stop vlc player either backend and kill process"""
    _global_player.stop_and_exit()

# Legacy compatibility functions
def stop_callback_playback():
    """Legacy function for compatibility"""
    stop_playback()

def play_file_old(filepath, show_interface=False):
    """Legacy function for backward compatibility"""
    return play_file(filepath, show_interface)

def find_vlc_installation():
    """Legacy function for backward compatibility"""
    return VLCPlayer._find_vlc_exe()

def test_vlc_nonblocking():
    """Test VLC functionality"""
    print("🔍 Testing VLC...")
    
    vlc_path = VLCPlayer._find_vlc_exe()
    if vlc_path:
        print(f"✅ VLC found at: {vlc_path}")
    else:
        print("⚠️ VLC not found in standard locations")
    
    if vlc:
        print("✅ python-vlc library available")
    else:
        print("⚠️ python-vlc library not available")
    
    print(f"🖥️ Platform: {platform.system()}")

# ----------------------------------------------------------------------
# Example usage and testing
if __name__ == "__main__":
    def done():
        print("✓ playback finished")

    player = VLCPlayer()

    # Pick any file you have
    media_file = "example.mp4"

    if os.path.exists(media_file):
        # A) libvlc without GUI
        player.play(media_file, show_gui=False, backend="auto", on_finished=done)

        # do other things while video plays …
        while player.is_playing():
            print("main loop alive")
            time.sleep(0.5)
    else:
        print(f"Test file {media_file} not found")
        test_vlc_nonblocking()
