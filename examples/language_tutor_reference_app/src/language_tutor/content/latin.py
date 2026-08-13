"""
Latin language content for drills and conversation.

Covers Classical Latin: irregular verbs (present/imperfect/perfect),
noun declensions (1st and 2nd), prepositions with case government,
and practice/listening sentences drawn from Caesar and Cicero.
"""

from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Irregular verb conjugations
# Tenses: present, imperfect, perfect
# Persons: 1s, 2s, 3s, 1pl, 2pl, 3pl
# ---------------------------------------------------------------------------

IRREGULAR_VERBS: Dict[str, Dict[str, Dict[str, str]]] = {
    "esse": {
        "present":   {"1s": "sum",   "2s": "es",    "3s": "est",
                      "1pl": "sumus", "2pl": "estis", "3pl": "sunt"},
        "imperfect": {"1s": "eram",  "2s": "eras",  "3s": "erat",
                      "1pl": "eramus","2pl": "eratis","3pl": "erant"},
        "perfect":   {"1s": "fui",   "2s": "fuisti","3s": "fuit",
                      "1pl": "fuimus","2pl": "fuistis","3pl": "fuerunt"},
    },
    "ire": {
        "present":   {"1s": "eo",    "2s": "is",    "3s": "it",
                      "1pl": "imus",  "2pl": "itis",  "3pl": "eunt"},
        "imperfect": {"1s": "ibam",  "2s": "ibas",  "3s": "ibat",
                      "1pl": "ibamus","2pl": "ibatis","3pl": "ibant"},
        "perfect":   {"1s": "ii",    "2s": "isti",  "3s": "iit",
                      "1pl": "iimus", "2pl": "istis", "3pl": "ierunt"},
    },
    "velle": {
        "present":   {"1s": "volo",  "2s": "vis",   "3s": "vult",
                      "1pl": "volumus","2pl": "vultis","3pl": "volunt"},
        "imperfect": {"1s": "volebam","2s": "volebas","3s": "volebat",
                      "1pl": "volebamus","2pl": "volebatis","3pl": "volebant"},
        "perfect":   {"1s": "volui", "2s": "voluisti","3s": "voluit",
                      "1pl": "voluimus","2pl": "voluistis","3pl": "voluerunt"},
    },
    "ferre": {
        "present":   {"1s": "fero",  "2s": "fers",  "3s": "fert",
                      "1pl": "ferimus","2pl": "fertis","3pl": "ferunt"},
        "imperfect": {"1s": "ferebam","2s": "ferebas","3s": "ferebat",
                      "1pl": "ferebamus","2pl": "ferebatis","3pl": "ferebant"},
        "perfect":   {"1s": "tuli",  "2s": "tulisti","3s": "tulit",
                      "1pl": "tulimus","2pl": "tulistis","3pl": "tulerunt"},
    },
    "posse": {
        "present":   {"1s": "possum","2s": "potes", "3s": "potest",
                      "1pl": "possumus","2pl": "potestis","3pl": "possunt"},
        "imperfect": {"1s": "poteram","2s": "poteras","3s": "poterat",
                      "1pl": "poteramus","2pl": "poteratis","3pl": "poterant"},
        "perfect":   {"1s": "potui", "2s": "potuisti","3s": "potuit",
                      "1pl": "potuimus","2pl": "potuistis","3pl": "potuerunt"},
    },
}

# ---------------------------------------------------------------------------
# Noun declensions (replaces reflexive verbs for Latin)
# 1st declension: puella (girl)
# 2nd declension m: servus (slave/servant)
# 2nd declension n: bellum (war)
# Cases: nominative, genitive, dative, accusative, ablative
# ---------------------------------------------------------------------------

NOUN_DECLENSIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    "puella": {
        "meaning": "girl",
        "declension": "1st",
        "singular": {
            "nominative": "puella",
            "genitive":   "puellae",
            "dative":     "puellae",
            "accusative": "puellam",
            "ablative":   "puella",
        },
        "plural": {
            "nominative": "puellae",
            "genitive":   "puellarum",
            "dative":     "puellis",
            "accusative": "puellas",
            "ablative":   "puellis",
        },
    },
    "servus": {
        "meaning": "slave / servant",
        "declension": "2nd",
        "singular": {
            "nominative": "servus",
            "genitive":   "servi",
            "dative":     "servo",
            "accusative": "servum",
            "ablative":   "servo",
        },
        "plural": {
            "nominative": "servi",
            "genitive":   "servorum",
            "dative":     "servis",
            "accusative": "servos",
            "ablative":   "servis",
        },
    },
    "bellum": {
        "meaning": "war",
        "declension": "2nd neuter",
        "singular": {
            "nominative": "bellum",
            "genitive":   "belli",
            "dative":     "bello",
            "accusative": "bellum",
            "ablative":   "bello",
        },
        "plural": {
            "nominative": "bella",
            "genitive":   "bellorum",
            "dative":     "bellis",
            "accusative": "bella",
            "ablative":   "bellis",
        },
    },
}

# ---------------------------------------------------------------------------
# Preposition drills — Latin prepositions with case government
# ---------------------------------------------------------------------------

PREPOSITION_DRILLS: List[Dict[str, str]] = [
    {"prep": "in",  "case": "ablative",   "meaning": "in / on (location)",
     "example": "in foro",      "english": "in the forum"},
    {"prep": "in",  "case": "accusative", "meaning": "into / onto (motion)",
     "example": "in urbem",     "english": "into the city"},
    {"prep": "ad",  "case": "accusative", "meaning": "to / toward",
     "example": "ad Romam",     "english": "to Rome"},
    {"prep": "ex",  "case": "ablative",   "meaning": "out of / from",
     "example": "ex silva",     "english": "out of the forest"},
    {"prep": "e",   "case": "ablative",   "meaning": "out of / from (variant)",
     "example": "e castris",    "english": "out of the camp"},
    {"prep": "cum", "case": "ablative",   "meaning": "with",
     "example": "cum amicis",   "english": "with friends"},
    {"prep": "per", "case": "accusative", "meaning": "through / throughout",
     "example": "per vias",     "english": "through the streets"},
    {"prep": "sub", "case": "ablative",   "meaning": "under (position)",
     "example": "sub arbore",   "english": "under the tree"},
    {"prep": "sub", "case": "accusative", "meaning": "under (motion toward)",
     "example": "sub montem",   "english": "to the foot of the mountain"},
    {"prep": "de",  "case": "ablative",   "meaning": "down from / about",
     "example": "de bello",     "english": "about the war"},
    {"prep": "ante","case": "accusative", "meaning": "before / in front of",
     "example": "ante portas",  "english": "before the gates"},
    {"prep": "post","case": "accusative", "meaning": "after / behind",
     "example": "post proelium","english": "after the battle"},
]

# ---------------------------------------------------------------------------
# Practice sentences (Classical Latin, Caesar and Cicero)
# ---------------------------------------------------------------------------

PRACTICE_SENTENCES: List[Tuple[str, str]] = [
    ("Gallia est omnis divisa in partes tres",
     "All of Gaul is divided into three parts"),
    ("Veni, vidi, vici",
     "I came, I saw, I conquered"),
    ("Alea iacta est",
     "The die has been cast"),
    ("Dum spiro, spero",
     "While I breathe, I hope"),
    ("Omnia vincit amor",
     "Love conquers all"),
    ("Errare humanum est",
     "To err is human"),
    ("Caesar in Galliam cum exercitu contendit",
     "Caesar marched into Gaul with his army"),
    ("Puella aquam ad villam portat",
     "The girl carries water to the farmhouse"),
    ("Servi in agris laborant",
     "The slaves work in the fields"),
    ("Milites per silvam iter faciunt",
     "The soldiers make their way through the forest"),
    ("Senatus populusque Romanus",
     "The Senate and People of Rome"),
    ("Cogito, ergo sum",
     "I think, therefore I am"),
    ("In vino veritas",
     "In wine there is truth"),
    ("Dux exercitum ex castris eduxit",
     "The general led the army out of the camp"),
    ("Roma omnibus viis pervenitur",
     "Rome is reached by all roads"),
]

# ---------------------------------------------------------------------------
# Listening comprehension sentences (slightly harder)
# ---------------------------------------------------------------------------

LISTENING_SENTENCES: List[Tuple[str, str]] = [
    ("Romani multas terras bello ceperunt",
     "The Romans captured many lands by war"),
    ("Cicero orationem in senatu habuit",
     "Cicero gave a speech in the Senate"),
    ("Puellae flores in horto legunt",
     "The girls gather flowers in the garden"),
    ("Miles gladium in manu tenet",
     "The soldier holds a sword in his hand"),
    ("Rex cum amicis ad urbem iter facit",
     "The king travels to the city with friends"),
    ("Puer libros in schola legit",
     "The boy reads books at school"),
    ("Feminae aquam de flumine portant",
     "The women carry water from the river"),
    ("Exercitus Romanus hostes vicit",
     "The Roman army defeated the enemy"),
    ("Poeta carmen de amore scripsit",
     "The poet wrote a song about love"),
    ("Senex in villa sua otium agebat",
     "The old man spent his leisure time in his country house"),
    ("Deus caelum terramque creavit",
     "God created heaven and earth"),
    ("Nuntius epistulam ad consulem tulit",
     "The messenger brought a letter to the consul"),
    ("Magistra discipulos litteras docet",
     "The teacher teaches the students letters"),
    ("Navis per mare magnum navigavit",
     "The ship sailed through the great sea"),
    ("Omnes cives legibus parent",
     "All citizens obey the laws"),
    ("Philosophi de natura rerum disputant",
     "The philosophers debate the nature of things"),
    ("Agricolae in agris per totum diem laborant",
     "The farmers work in the fields throughout the whole day"),
    ("Tempus fugit nec revocare potest",
     "Time flies and cannot be called back"),
    ("Veritas in luce apparet",
     "Truth appears in the light"),
    ("Amicus certus in re incerta cernitur",
     "A true friend is recognized in uncertain times"),
]

# ---------------------------------------------------------------------------
# Conversation starters (Latin warmup openers)
# ---------------------------------------------------------------------------

CONVERSATION_STARTERS: List[str] = [
    "Quid agis hodie?",
    "Valesne?",
    "Quid nomen tibi est?",
    "Unde venis?",
    "Quid fecisti heri?",
    "De quo loqui vis?",
    "Quid de historia Romana scis?",
    "Quot annos habes?",
    "Ubi habitas?",
    "Placetne tibi lingua Latina?",
    "Quid legis nunc?",
    "Habesne amicos qui Latine loquuntur?",
]

# ---------------------------------------------------------------------------
# Conversation prompts (structured practice)
# ---------------------------------------------------------------------------

CONVERSATION_PROMPTS: List[Tuple[str, str]] = [
    ("Quid heri fecisti?", "What did you do yesterday?"),
    ("Quid est nomen tuum?", "What is your name?"),
    ("Qua hora surrexi?", "At what hour did you rise?"),
    ("Ubi Roma sita est?", "Where is Rome situated?"),
    ("Quid Romani bello quaesiverunt?", "What did the Romans seek through war?"),
    ("Cur Latine discis?", "Why are you learning Latin?"),
    ("Quis est imperator Romanorum?", "Who is the commander of the Romans?"),
    ("Quid Cicero dixit?", "What did Cicero say?"),
]


def get_content() -> dict:
    """Return all Latin content as a single dict for DrillSystem."""
    return {
        "irregular_verbs":      IRREGULAR_VERBS,
        "noun_declensions":     NOUN_DECLENSIONS,
        "reflexive_verbs":      {},           # Not applicable in Latin
        "reflexive_conjugations": {},         # Not applicable in Latin
        "preposition_drills":   PREPOSITION_DRILLS,
        "practice_sentences":   PRACTICE_SENTENCES,
        "listening_sentences":  LISTENING_SENTENCES,
        "conversation_starters": CONVERSATION_STARTERS,
        "conversation_prompts": CONVERSATION_PROMPTS,
    }
