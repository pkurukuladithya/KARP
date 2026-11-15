import sys
from pathlib import Path

PI_BRAIN = Path(__file__).resolve().parents[1]
if str(PI_BRAIN) not in sys.path:
    sys.path.insert(0, str(PI_BRAIN))
