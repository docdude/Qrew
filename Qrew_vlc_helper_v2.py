# Qrew_vlc_helper_v2.py – non-blocking VLC wrapper
import os, platform, subprocess, threading, queue, time, shutil, re
from pathlib import Path
from typing import Callable, Optional
import Qrew_common

try:
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
        if backend == "auto":
            backend = "libvlc" if vlc else "subprocess"

        if backend == "libvlc":
            if not vlc:
                raise RuntimeError("python-vlc not installed")
            self._play_libvlc(path, show_gui, on_finished)
        elif backend == "subprocess":
            self._play_subproc(path, show_gui, on_finished)
        else:
            raise ValueError("backend must be 'libvlc', 'subprocess', or 'auto'")

    # -------------------- libvlc path --------------------------------
    def _play_libvlc(self, path, show_gui, on_finished):
        intf_flag = "--intf=qt" if show_gui else "--intf=dummy"
        instance  = vlc.Instance("--play-and-exit", intf_flag)
        player    = instance.media_player_new()
        player.set_media(instance.media_new(Path(path).as_posix()))
        player.audio_set_volume(100)

        # Finish queue + callback
        done_q = queue.Queue()

        def _on_end(ev):
            done_q.put(True)

        evmgr = player.event_manager()
        evmgr.event_attach(vlc.EventType.MediaPlayerEndReached, _on_end)
        player.play()
        self._playing = True

        # watchdog thread waits for queue then fires callback
        def _watch():
            done_q.get()               # blocks until signal
            self._playing = False
            if on_finished:
                on_finished()
            player.release()
            instance.release()

        threading.Thread(target=_watch, daemon=True).start()

    # -------------------- subprocess path ----------------------------
    def _play_subproc(self, path, show_gui, on_finished):
        vlc_path = self._find_vlc_exe()
        if not vlc_path:
            raise RuntimeError("VLC executable not found")

        cmd = [vlc_path, "--play-and-exit", "--auhal-volume=256", path]
        if not show_gui:
            cmd += ["--intf", "dummy"]

        proc = subprocess.Popen(cmd)
        self._playing = True

        def _watch():
            proc.wait()
            self._playing = False
            if on_finished:
                on_finished()

        threading.Thread(target=_watch, daemon=True).start()

    # -------------------- helpers ------------------------------------
    @staticmethod
    def _find_vlc_exe() -> Optional[str]:
        # Try PATH first
        if shutil.which("vlc"):
            return "vlc"

        system = platform.system()
        if system == "Darwin":   # macOS
            for p in (
                "/Applications/VLC.app/Contents/MacOS/VLC",
                "/opt/homebrew/bin/vlc",
                "/usr/local/bin/vlc",
            ):
                if os.path.exists(p):
                    return p
        elif system == "Windows":
            possible = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            for p in (
                rf"{possible}\VideoLAN\VLC\vlc.exe",
                rf"{possible} (x86)\VideoLAN\VLC\vlc.exe",
            ):
                if os.path.exists(p):
                    return p
        # Linux fall-back handled by PATH earlier
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
    
    try:
        backend = getattr(Qrew_common, 'vlc_backend', 'auto')
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

def play_file_with_callback(filepath, show_interface=False, completion_callback=None):
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
        backend = getattr(Qrew_common, 'vlc_backend', 'auto')
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
