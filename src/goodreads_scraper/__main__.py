"""Allow ``python -m goodreads_scraper``."""

import sys

from .cli import main

sys.exit(main())
