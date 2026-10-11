from handy_context.dictionary import Dictionary


def test_parse_words_and_replacements():
    d = Dictionary.parse(
        "# comment\n\nKubernetes\nmari gold => Marigold\nKubernetes\n  frobnicate_widget  \nbad =>\n"
    )
    assert d.words == ["Kubernetes", "Marigold", "frobnicate_widget"]
    assert d.replacements == [("mari gold", "Marigold")]


def test_apply_whole_words_any_case():
    d = Dictionary.parse("mari gold => Marigold\nk eights => k8s\n")
    assert d.apply("Ask Mari Gold about k eights.") == "Ask Marigold about k8s."
    assert d.apply("Mari-gold") == "Marigold"
    assert d.apply("amari gold") == "amari gold"


def test_capitals_heard_side_matches_capitals_only():
    d = Dictionary.parse("AIR => AYRE\n")
    assert d.apply("The AIR team needs fresh air. Air is free.") == "The AYRE team needs fresh air. Air is free."
    d = Dictionary.parse("A I R => AYRE\n")
    assert d.apply("at A I R and a i r") == "at AYRE and a i r"


def test_longest_replacement_first():
    d = Dictionary.parse("new york => NY\nnew york city => NYC\n")
    assert d.apply("in new york city today") == "in NYC today"


def test_replacement_with_regex_characters():
    d = Dictionary.parse("c plus plus => C++\n")
    assert d.apply("I write c plus plus") == "I write C++"


def test_load_creates_template(tmp_path):
    path = tmp_path / "sub" / "dictionary.txt"
    d = Dictionary.load(path)
    assert path.exists()
    assert d.words == [] and d.replacements == []


def test_load_reads_bom(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_bytes(b"\xef\xbb\xbfXylocarpa\n")
    assert Dictionary.load(path).words == ["Xylocarpa"]
