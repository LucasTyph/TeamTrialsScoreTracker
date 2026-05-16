"""Configuration settings for the score extraction system.

Edit CHARACTER_NAMES to match the actual 15 in-game character names.
"""

CHARACTER_NAMES = [
    # TODO: Replace with the 15 actual character names from your game
    "Maruzensky",
    "Oguri Cap",
    "Curren Chan",
    "Gold Ship",
    "Mihono Bourbon",
    "Sakura Chiyono O",
    "Kitasan Black",
    "Smart Falcon",
    "Agnes Tachyon",
    "Narita Taishin",
    "El Condor Pasa",
    "Agnes Digital",
    "Sakura Bakushin O",
    "Biwa Hayahide",
    "King Halo",
]

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

ROW_TOLERANCE = 20

FUZZY_MATCH_THRESHOLD = 0.6

ADJUSTED_SCORE_K = 0.5

DATA_DIR = "data"

CSV_FILENAME = "dataset.csv"
