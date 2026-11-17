import sys

def main():
    if '--gui-smoke-test' in sys.argv:
        from .gui_validation import main as validate_gui
        return validate_gui()
    if '--smoke-test' in sys.argv:
        from .validation import main as validate
        return validate()
    from .startup import launch_gui
    return launch_gui()

if __name__ == '__main__':
    sys.exit(main())
