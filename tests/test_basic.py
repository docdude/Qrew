"""
Basic test to verify Qrew package imports correctly
"""
import pytest


def test_qrew_import():
    """Test that qrew package can be imported"""
    import qrew
    assert hasattr(qrew, '__version__')
    assert qrew.__version__ == "1.0.0"


def test_main_components():
    """Test that main components can be imported"""
    from qrew import MainWindow, shutdown_handler
    assert MainWindow is not None
    assert shutdown_handler is not None


def test_settings_import():
    """Test that settings module works"""
    from qrew import qs
    assert qs is not None
    # Basic settings operations should work
    assert callable(qs.get)
    assert callable(qs.set)


if __name__ == "__main__":
    pytest.main([__file__])
