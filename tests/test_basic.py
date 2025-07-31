"""
Basic test to verify Qrew package structure and imports
"""
import pytest
import sys
import os


def test_package_structure():
    """Test that qrew package has expected structure"""
    import qrew
    # Check that package has expected attributes
    assert hasattr(qrew, '__file__')
    
    # Check version if available
    if hasattr(qrew, '__version__'):
        assert isinstance(qrew.__version__, str)


def test_module_imports():
    """Test that individual modules can be imported without full initialization"""
    # Test that we can import the main module file directly
    import qrew.main
    assert hasattr(qrew.main, 'main')
    assert callable(qrew.main.main)


def test_settings_module():
    """Test that settings module can be imported"""
    try:
        import qrew.Qrew_settings as settings
        # Should be able to import without VLC
        assert settings is not None
    except ImportError as e:
        # If it fails due to missing dependencies, that's expected in CI
        if "vlc" in str(e).lower():
            pytest.skip("VLC not available in test environment")
        else:
            raise


def test_vlc_graceful_handling():
    """Test that VLC import issues are handled gracefully"""
    try:
        # Try to import VLC-dependent modules
        import qrew
        # If this works, VLC is available
        if hasattr(qrew, '__version__'):
            assert qrew.__version__ == "1.0.0"
    except (ImportError, OSError) as e:
        # Expected in CI environments without VLC
        if any(term in str(e).lower() for term in ['vlc', 'libvlc', 'dylib']):
            pytest.skip(f"VLC not available: {e}")
        else:
            raise


def test_package_metadata():
    """Test package metadata without importing main modules"""
    # Test that we can access package directory
    import qrew
    package_dir = os.path.dirname(qrew.__file__)
    assert os.path.isdir(package_dir)
    
    # Check for expected files
    expected_files = ['main.py', '__init__.py', '__main__.py']
    for filename in expected_files:
        filepath = os.path.join(package_dir, filename)
        assert os.path.isfile(filepath), f"Missing {filename}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
