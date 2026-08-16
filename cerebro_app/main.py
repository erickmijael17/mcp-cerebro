import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cerebro_app.app import CerebroApp


def main():
    app = CerebroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
