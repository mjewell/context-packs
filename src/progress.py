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
    """Print each label as an item waiting, `[ ]`, then mark it running, `[-]`, as start is called with its index,
    and done, `[x]` with a note, as tick is. Marking an item running shows only on a terminal: elsewhere it would add
    a line per item that says nothing a finished one doesn't."""

    def __init__(self, labels):
        self.labels = labels
        self.width = max(len(label) for label in labels)
        self.lock = threading.Lock()
        for label in labels:
            print(f'  [ ] {label}', flush=True)

    def start(self, index):
        if sys.stdout.isatty():
            self.redraw(index, f'  [-] {self.labels[index]}')

    def tick(self, index, note):
        line = f'  [x] {self.labels[index].ljust(self.width)}  {note}'
        if sys.stdout.isatty():
            self.redraw(index, line)
        else:
            with self.lock:
                print(line, flush=True)

    def redraw(self, index, line):
        """Replace the item's line in place, then go back below the list."""
        up = len(self.labels) - index
        with self.lock:
            sys.stdout.write(f'{UP.format(up)}{CLEAR}{line}{DOWN.format(up)}\r')
            sys.stdout.flush()


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
