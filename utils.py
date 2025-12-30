import sys


def update_line(text):
    """Update the current line in console"""
    sys.stdout.write(f'\r{text}')
    sys.stdout.flush()


def print_line(text):
    """Print a new line"""
    print(f'\r{text}')