from app.db import init_db, add_watched

INITIAL_PEOPLE = [
    ("Paul_McCartney",  "Paul McCartney",  "Musicians",   1942),
    ("Mick_Jagger",     "Mick Jagger",     "Musicians",   1943),
    ("Willie_Nelson",   "Willie Nelson",   "Musicians",   1933),
    ("Clint_Eastwood",  "Clint Eastwood",  "Actors",      1930),
    ("Jane_Fonda",      "Jane Fonda",      "Actors",      1937),
    ("Al_Pacino",       "Al Pacino",       "Actors",      1940),
    ("Dick_Van_Dyke",   "Dick Van Dyke",   "Actors",      1925),
    ("Dolly_Parton",    "Dolly Parton",    "Musicians",   1946),
]

if __name__ == '__main__':
    init_db()
    for wiki_title, display_name, category, birth_year in INITIAL_PEOPLE:
        if add_watched(wiki_title, display_name, category, birth_year):
            print(f'  Added: {display_name}')
        else:
            print(f'  Already watching: {display_name}')
    print('Done!')
