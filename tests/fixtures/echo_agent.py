#!/usr/bin/env python3
"""Echo agent — reads PCM from stdin, writes it back to stdout.

Used for testing the exec: connector. Simplest possible voice agent.
Protocol: stdin=PCM 16kHz 16-bit mono, stdout=same, stderr=JSON metadata.
"""

import json
import sys


def main() -> None:
    # Write metadata to stderr
    metadata = {"turn_count": 1, "agent": "echo", "version": "1.0"}
    sys.stderr.write(json.dumps(metadata) + "\n")
    sys.stderr.flush()

    # Read audio from stdin and echo it back
    while True:
        chunk = sys.stdin.buffer.read(3200)  # 100ms at 16kHz 16-bit
        if not chunk:
            break
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
