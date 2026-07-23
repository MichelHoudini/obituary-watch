"""
catalog.py - Curated public watchlist pages for Mortivox.

These are seed pages for discovery and monitoring. A catalog entry is not a
biographical assertion that the person is alive; page status is based on what
Mortivox has detected in its own database.
"""

import re

RAW_CATALOG = [
    ("Clint_Eastwood", "Clint Eastwood", "Actors", 1930),
    ("Dick_Van_Dyke", "Dick Van Dyke", "Actors", 1925),
    ("Mel_Brooks", "Mel Brooks", "Actors", 1926),
    ("Michael_Caine", "Michael Caine", "Actors", 1933),
    ("Sophia_Loren", "Sophia Loren", "Actors", 1934),
    ("Julie_Andrews", "Julie Andrews", "Actors", 1935),
    ("Robert_Redford", "Robert Redford", "Actors", 1936),
    ("Dustin_Hoffman", "Dustin Hoffman", "Actors", 1937),
    ("Morgan_Freeman", "Morgan Freeman", "Actors", 1937),
    ("Jack_Nicholson", "Jack Nicholson", "Actors", 1937),
    ("Jane_Fonda", "Jane Fonda", "Actors", 1937),
    ("Anthony_Hopkins", "Anthony Hopkins", "Actors", 1937),
    ("Lily_Tomlin", "Lily Tomlin", "Actors", 1939),
    ("Al_Pacino", "Al Pacino", "Actors", 1940),
    ("Martin_Sheen", "Martin Sheen", "Actors", 1940),
    ("Patrick_Stewart", "Patrick Stewart", "Actors", 1940),
    ("Robert_De_Niro", "Robert De Niro", "Actors", 1943),
    ("Christopher_Walken", "Christopher Walken", "Actors", 1943),
    ("Danny_DeVito", "Danny DeVito", "Actors", 1944),
    ("Helen_Mirren", "Helen Mirren", "Actors", 1945),
    ("Sylvester_Stallone", "Sylvester Stallone", "Actors", 1946),
    ("Arnold_Schwarzenegger", "Arnold Schwarzenegger", "Actors", 1947),
    ("Samuel_L._Jackson", "Samuel L. Jackson", "Actors", 1948),
    ("Meryl_Streep", "Meryl Streep", "Actors", 1949),
    ("Bill_Murray", "Bill Murray", "Actors", 1950),
    ("Mark_Hamill", "Mark Hamill", "Actors", 1951),
    ("Liam_Neeson", "Liam Neeson", "Actors", 1952),
    ("Jackie_Chan", "Jackie Chan", "Actors", 1954),
    ("Tom_Hanks", "Tom Hanks", "Actors", 1956),
    ("Denzel_Washington", "Denzel Washington", "Actors", 1954),
    ("Whoopi_Goldberg", "Whoopi Goldberg", "Actors", 1955),
    ("Frances_McDormand", "Frances McDormand", "Actors", 1957),

    ("Willie_Nelson", "Willie Nelson", "Musicians", 1933),
    ("Yoko_Ono", "Yoko Ono", "Musicians", 1933),
    ("Dionne_Warwick", "Dionne Warwick", "Musicians", 1940),
    ("Bob_Dylan", "Bob Dylan", "Musicians", 1941),
    ("Paul_McCartney", "Paul McCartney", "Musicians", 1942),
    ("Barbra_Streisand", "Barbra Streisand", "Musicians", 1942),
    ("Mick_Jagger", "Mick Jagger", "Musicians", 1943),
    ("Keith_Richards", "Keith Richards", "Musicians", 1943),
    ("Roger_Daltrey", "Roger Daltrey", "Musicians", 1944),
    ("Pete_Townshend", "Pete Townshend", "Musicians", 1945),
    ("Rod_Stewart", "Rod Stewart", "Musicians", 1945),
    ("Eric_Clapton", "Eric Clapton", "Musicians", 1945),
    ("Neil_Young", "Neil Young", "Musicians", 1945),
    ("Dolly_Parton", "Dolly Parton", "Musicians", 1946),
    ("Cher", "Cher", "Musicians", 1946),
    ("Elton_John", "Elton John", "Musicians", 1947),
    ("Stevie_Nicks", "Stevie Nicks", "Musicians", 1948),
    ("Billy_Joel", "Billy Joel", "Musicians", 1949),
    ("Bruce_Springsteen", "Bruce Springsteen", "Musicians", 1949),
    ("Stevie_Wonder", "Stevie Wonder", "Musicians", 1950),
    ("Sting_(musician)", "Sting", "Musicians", 1951),
    ("Cyndi_Lauper", "Cyndi Lauper", "Musicians", 1953),
    ("Madonna", "Madonna", "Musicians", 1958),
    ("Beyoncé", "Beyoncé", "Musicians", 1981),
    ("Taylor_Swift", "Taylor Swift", "Musicians", 1989),
    ("Rihanna", "Rihanna", "Musicians", 1988),
    ("Lady_Gaga", "Lady Gaga", "Musicians", 1986),
    ("Adele", "Adele", "Musicians", 1988),
    ("Kendrick_Lamar", "Kendrick Lamar", "Musicians", 1987),

    ("Noam_Chomsky", "Noam Chomsky", "Writers", 1928),
    ("Joyce_Carol_Oates", "Joyce Carol Oates", "Writers", 1938),
    ("Margaret_Atwood", "Margaret Atwood", "Writers", 1939),
    ("Isabel_Allende", "Isabel Allende", "Writers", 1942),
    ("Stephen_King", "Stephen King", "Writers", 1947),
    ("Haruki_Murakami", "Haruki Murakami", "Writers", 1949),
    ("Salman_Rushdie", "Salman Rushdie", "Writers", 1947),
    ("George_R._R._Martin", "George R. R. Martin", "Writers", 1948),
    ("J._K._Rowling", "J. K. Rowling", "Writers", 1965),
    ("Neil_Gaiman", "Neil Gaiman", "Writers", 1960),

    ("David_Attenborough", "David Attenborough", "Presenters", 1926),
    ("Jane_Goodall", "Jane Goodall", "Scientists", 1934),
    ("Roger_Penrose", "Roger Penrose", "Scientists", 1931),
    ("Richard_Dawkins", "Richard Dawkins", "Scientists", 1941),
    ("Brian_Greene", "Brian Greene", "Scientists", 1963),
    ("Neil_deGrasse_Tyson", "Neil deGrasse Tyson", "Scientists", 1958),
    ("Michio_Kaku", "Michio Kaku", "Scientists", 1947),
    ("Temple_Grandin", "Temple Grandin", "Scientists", 1947),
    ("Tim_Berners-Lee", "Tim Berners-Lee", "Scientists", 1955),
    ("Yoshua_Bengio", "Yoshua Bengio", "Scientists", 1964),
    ("Geoffrey_Hinton", "Geoffrey Hinton", "Scientists", 1947),
    ("Andrew_Ng", "Andrew Ng", "Scientists", 1976),

    ("Dalai_Lama", "Dalai Lama", "Public figures", 1935),
    ("King_Charles_III", "King Charles III", "Public figures", 1948),
    ("Queen_Camilla", "Queen Camilla", "Public figures", 1947),
    ("Joe_Biden", "Joe Biden", "Politicians", 1942),
    ("Donald_Trump", "Donald Trump", "Politicians", 1946),
    ("Bill_Clinton", "Bill Clinton", "Politicians", 1946),
    ("George_W._Bush", "George W. Bush", "Politicians", 1946),
    ("Barack_Obama", "Barack Obama", "Politicians", 1961),
    ("Hillary_Clinton", "Hillary Clinton", "Politicians", 1947),
    ("Nancy_Pelosi", "Nancy Pelosi", "Politicians", 1940),
    ("Bernie_Sanders", "Bernie Sanders", "Politicians", 1941),
    ("Vladimir_Putin", "Vladimir Putin", "Politicians", 1952),
    ("Xi_Jinping", "Xi Jinping", "Politicians", 1953),
    ("Luiz_Inácio_Lula_da_Silva", "Luiz Inácio Lula da Silva", "Politicians", 1945),
    ("Fernando_Henrique_Cardoso", "Fernando Henrique Cardoso", "Politicians", 1931),

    ("Magic_Johnson", "Magic Johnson", "Athletes", 1959),
    ("Michael_Jordan", "Michael Jordan", "Athletes", 1963),
    ("Mike_Tyson", "Mike Tyson", "Athletes", 1966),
    ("Serena_Williams", "Serena Williams", "Athletes", 1981),
    ("Tiger_Woods", "Tiger Woods", "Athletes", 1975),
    ("Lionel_Messi", "Lionel Messi", "Athletes", 1987),
    ("Cristiano_Ronaldo", "Cristiano Ronaldo", "Athletes", 1985),
    ("Neymar", "Neymar", "Athletes", 1992),
]

LISTS = {
    "most-monitored": {
        "title": "Most monitored",
        "description": "Wikipedia pages with the most Mortivox subscribers.",
    },
    "oldest-living": {
        "title": "Long-lived public figures watchlist",
        "description": "A watchlist of older public figures. This is not a ranked biographical database; Mortivox status reflects only detections made by Mortivox.",
    },
    "actors": {
        "title": "Actors watchlist",
        "description": "Film and television figures with public Mortivox watch pages.",
    },
    "musicians": {
        "title": "Musicians watchlist",
        "description": "Music figures with public Mortivox watch pages.",
    },
}


def slugify(value: str) -> str:
    value = value.lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9-]+", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "person"


def title_to_slug(wiki_title: str) -> str:
    return slugify(wiki_title)


def _build_catalog():
    people = []
    for wiki_title, display_name, category, birth_year in RAW_CATALOG:
        people.append({
            "wiki_title": wiki_title,
            "display_name": display_name,
            "category": category,
            "birth_year": birth_year,
            "slug": title_to_slug(wiki_title),
        })
    return people


CATALOG = _build_catalog()
_BY_SLUG = {person["slug"]: person for person in CATALOG}
_BY_TITLE = {person["wiki_title"]: person for person in CATALOG}


def catalog_people() -> list[dict]:
    return list(CATALOG)


def find_catalog_person(slug_or_title: str) -> dict | None:
    return _BY_SLUG.get(slug_or_title) or _BY_TITLE.get(slug_or_title)


def get_list_people(list_slug: str) -> list[dict]:
    if list_slug == "actors":
        return [p for p in CATALOG if p["category"] == "Actors"]
    if list_slug == "musicians":
        return [p for p in CATALOG if p["category"] == "Musicians"]
    if list_slug == "oldest-living":
        return sorted([p for p in CATALOG if p.get("birth_year")], key=lambda p: p["birth_year"])
    return CATALOG
