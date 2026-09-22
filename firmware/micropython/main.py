"""LumosAir node entry point — runs on boot."""

import sys

sys.path.append("/lib")

try:
    import config
except ImportError:                                   # first flash, nothing configured yet
    import config_example as config
    print("config.py not found — running with config_example.py; edit and upload config.py")

from lumosair.node import Node


def main():
    print("LumosAir node '%s'" % config.NODE_ID)
    node = Node(config)
    while True:
        try:
            node.run()
        except KeyboardInterrupt:
            raise
        except Exception as e:                        # noqa: BLE001 — never die in a duct
            sys.print_exception(e) if hasattr(sys, "print_exception") else print(e)
            try:
                import time
                time.sleep(2)
            except Exception:
                pass


main()
