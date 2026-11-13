"""Which function the assistant reaches how (plan werkzeug-abdeckung.md, Dominik 2026-10-13: „überprüfe ob es für
alle Dienste und Infos Werkzeuge gibt“; the reMarkable's morning sheet could not be sent again, no tool had it).

Every function in features.FEATURES stands here exactly once (built from steckbrief.py):
  TOOLS    its tools for the language model (internal names, werkzeuge.NAMES gives the readable ones);
  RULES    the panel's fixed rule that answers it without the model choosing (a sentence the panel recognizes);
  WITHOUT  why there is nothing to ask for: a setting of how answers come about, something the Spark does by itself,
           a channel or device, or deliberately not by voice (secrets, security, undoing the Notaus).
A function may have tools and a rule at once; WITHOUT stands alone.

tests/test_werkzeug_abdeckung.py checks: every function is here, every tool named here exists and every tool of the
chat sits in a group of the Weiche (intent.GROUPS), is always kept (intent.NARROW_KEEP) or kept when the person names
it (BY_WORD), and SENTENCES leads each grouped tool's typical request to its group. Since V01.1.406 all of
it comes from each function's Steckbrief (steckbrief.py); a new function names it there (guideline part 1, row 29)."""
import steckbrief

TOOLS = steckbrief.abdeckung()   # every function's tools stand in its Steckbrief (steckbrief.py)
RULES = steckbrief.ohne_werkzeug("regel")   # functions the panel answers by a fixed rule
WITHOUT = steckbrief.ohne_werkzeug("ohne")   # functions the model answers without a tool

# the panel's own steps under a tool's name, never offered to the model (lokal.py's quick look)
PANEL_STEPS = {"local_search"}

# tools a module offers only when the person's own words name it: the Weiche keeps them (extras "keep")
BY_WORD = steckbrief.nur_eigenes_wort()   # from each function's Steckbrief (steckbrief.py)

# one typical request per tool of a Weiche group, German and English: it must reach that group
# (tests/test_werkzeug_abdeckung.py). The one list of example sentences: „Das kannst du auch sagen“ (saetze.py) shows
# them too, so each is a plain request a person could say as it stands
SENTENCES = steckbrief.saetze()   # from each function's Steckbrief (steckbrief.py)
