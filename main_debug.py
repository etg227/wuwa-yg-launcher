if __name__ == '__main__':
    import sys

    if sys.platform == 'win32':
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('etg227.YeguoLauncher')
        except Exception:
            pass

    from config import config
    from ok import OK

    config = config
    config['debug'] = True
    # config['click_screenshots_folder'] = "click_screenshots"  # debug用 点击后截图文件夹]
    ok = OK(config)
    ok.start()
