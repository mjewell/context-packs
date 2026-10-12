"""Feedback while slow work runs: a checklist printed up front whose items are ticked as they finish, and a short
pause to read it before starting. On a terminal, items are ticked in place; otherwise each finished item prints a
line, so a log or an agent reading the output sees the same thing in order."""
import select
import sys
import threading

UP = '\x1b[{}A'
DOWN = '\x1b[{}B'
CLEAR = '\r\x1b[K'


def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


class Checklist:
    """Print each label as an unticked item, then tick it, with a note, as tick is called with its index."""

    def __init__(self, labels):
        self.labels = labels
        self.width = max(len(label) for label in labels)
        self.lock = threading.Lock()
        for label in labels:
            print(f'  [ ] {label}', flush=True)

    def tick(self, index, note):
        line = f'  [x] {self.labels[index].ljust(self.width)}  {note}'
        with self.lock:
            if sys.stdout.isatty():
                up = len(self.labels) - index
                sys.stdout.write(f'{UP.format(up)}{CLEAR}{line}{DOWN.format(up)}\r')
                sys.stdout.flush()
            else:
                print(line, flush=True)


def pause(seconds):
    """On a terminal, wait seconds before going on, or until Enter; Ctrl-C stops. Elsewhere, go on at once."""
    if not interactive():
        return
    print(f'Starting in {seconds}s. Enter starts now, Ctrl-C cancels.', end='', flush=True)
    try:
        # Enter echoes a newline, so the message is then a line up. A closed stdin reads as ready but echoes nothing.
        if select.select([sys.stdin], [], [], seconds)[0] and sys.stdin.readline():
            sys.stdout.write(UP.format(1))
    except KeyboardInterrupt:
        print()
        sys.exit('context-packs: cancelled.')
    sys.stdout.write(CLEAR)
    sys.stdout.flush()
