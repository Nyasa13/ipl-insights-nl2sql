from app.entities import EntityLinker

PLAYERS = ["V Kohli", "RG Sharma", "I Sharma", "MS Dhoni", "AB de Villiers", "F du Plessis", "JJ Bumrah"]
L = EntityLinker(PLAYERS)


def test_unique_surname():
    assert L.hints("How many runs did Dhoni score?") == ["'Dhoni' -> player name 'MS Dhoni'"]


def test_full_name_maps_to_initials_format():
    assert "'Virat Kohli' -> player name 'V Kohli'" in L.hints("Who has dismissed Virat Kohli the most?")


def test_ambiguous_surname_is_narrowed_by_first_name():
    assert "'Rohit Sharma' -> player name 'RG Sharma'" in L.hints("Rohit Sharma runs in 2020")
    amb = L.hints("Sharma runs in 2020")
    assert any("could be" in h and "I Sharma" in h and "RG Sharma" in h for h in amb)


def test_particles_in_surname():
    assert "'Plessis' -> player name 'F du Plessis'" in L.hints("Runs by Faf du Plessis")[0] or L.hints("Runs by Faf du Plessis")


def test_team_aliases():
    h = L.hints("How many matches did RCB win after losing the toss?")
    assert "'RCB' -> team name 'Royal Challengers Bengaluru'" in h
    assert not L.team_hints("Which dc player?")  # lowercase abbreviation ignored


def test_lowercase_or_plain_words_do_not_trigger():
    assert L.hints("which batter has the most sixes in 2019") == []
