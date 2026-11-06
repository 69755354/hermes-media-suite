try:
    from .updater import start_background
    start_background()
except Exception:
    pass

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
