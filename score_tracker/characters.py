"""Known character names, for roster autocomplete and correcting OCR'd names.

Not exhaustive: names typed in the roster and names saved in your data are
offered too, and any name can be typed by hand.
"""

from difflib import get_close_matches

KNOWN_CHARACTERS = (
    "Admire Vega", "Agnes Digital", "Agnes Tachyon", "Air Groove", "Air Shakur",
    "Aston Machan", "Bamboo Memory", "Biko Pegasus", "Biwa Hayahide", "Cheval Grand",
    "Curren Chan", "Daitaku Helios", "Daiwa Scarlet", "Eishin Flash", "El Condor Pasa",
    "Fine Motion", "Fuji Kiseki", "Gold City", "Gold Ship", "Grass Wonder",
    "Haru Urara", "Hishi Akebono", "Hishi Amazon", "Ikuno Dictus", "Inari One",
    "Ines Fujin", "Kawakami Princess", "King Halo", "Kitasan Black", "Manhattan Cafe",
    "Maruzensky", "Marvelous Sunday", "Matikane Tannhauser", "Matikanefukukitaru",
    "Mayano Top Gun", "Meisho Doto", "Mejiro Ardan", "Mejiro Bright", "Mejiro Dober",
    "Mejiro McQueen", "Mejiro Palmer", "Mejiro Ryan", "Mihono Bourbon", "Mr. C.B.",
    "Nakayama Festa", "Narita Brian", "Narita Taishin", "Narita Top Road", "Nice Nature",
    "Nishino Flower", "Oguri Cap", "Rice Shower", "Sakura Bakushin O", "Sakura Chiyono O",
    "Sakura Laurel", "Satono Diamond", "Seeking the Pearl", "Seiun Sky", "Shinko Windy",
    "Silence Suzuka", "Sirius Symboli", "Smart Falcon", "Special Week", "Super Creek",
    "Sweep Tosho", "Symboli Kris S", "Symboli Rudolf", "T.M. Opera O", "Taiki Shuttle",
    "Tamamo Cross", "Tanino Gimlet", "Tokai Teio", "Tosen Jordan", "Tsurumaru Tsuyoshi",
    "Twin Turbo", "Vodka", "Winning Ticket", "Yaeno Muteki", "Yamanin Zephyr",
    "Yukino Bijin", "Zenno Rob Roy",
)


def best_name(text, extra=()) -> str:
    """The known name closest to OCR'd text, or the text itself."""
    candidates = list(dict.fromkeys([*extra, *KNOWN_CHARACTERS]))
    match = get_close_matches(text, candidates, n=1, cutoff=0.75)
    return match[0] if match else text
