import sys

def main():
    if '--smoke-test' in sys.argv:
        from .validation import main as validate
        return validate()
    from .gui import launch
    return launch()

if __name__ == '__main__':
    sys.exit(main())
