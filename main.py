if __name__ == '__main__':
    import sys

    if sys.platform == 'win32':
        # 显式设置应用标识，Windows 通知才会显示 椰果启动器 的名称和图标，而不是宿主 Python。
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('etg227.YeguoLauncher')
        except Exception:
            pass

    from config import config
    from ok import OK

    config = config
    ok = OK(config)
    ok.start()
