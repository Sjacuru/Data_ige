import os
from infrastructure.web import driver


def test_build_prefs_headless_blocks_images_and_fonts():
    prefs = driver._build_prefs(use_headless=True, download_dir=None, anti_detection=False)
    assert prefs.get("profile.managed_default_content_settings.images") == 2
    assert prefs.get("profile.managed_default_content_settings.fonts") == 2
    # no anti-detection keys should be present
    assert "profile.default_content_setting_values.notifications" not in prefs


def test_build_prefs_interactive_leaves_images_and_fonts():
    prefs = driver._build_prefs(use_headless=False, download_dir=None, anti_detection=False)
    assert "profile.managed_default_content_settings.images" not in prefs
    assert "profile.managed_default_content_settings.fonts" not in prefs


def test_build_prefs_anti_detection_includes_notifications_and_download():
    dl = os.getcwd()  # use cwd as dummy
    prefs = driver._build_prefs(use_headless=False, download_dir=dl, anti_detection=True)
    assert prefs.get("profile.default_content_setting_values.notifications") == 2
    assert prefs.get("credentials_enable_service") is False
    assert prefs.get("profile.password_manager_enabled") is False
    # download directory keys should also exist when download_dir provided
    assert prefs.get("download.default_directory") == str(dl)
    assert prefs.get("download.prompt_for_download") is False


def test_create_driver_accepts_user_data_dir(tmp_path):
    # passing a user_data_dir should not crash; we use headless mode so the
    # test runs in CI without a visible window.  only coexistence is checked.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    drv = driver.create_driver(headless=True, user_data_dir=str(profile_dir))
    try:
        assert drv is not None
    finally:
        driver.close_driver(drv)
