"""
Spanish language content for drills and conversation.

Ported from the standalone spanish_tutor project and extended for
integration with the language tutor's Engram-backed memory system.
"""

from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Irregular verb conjugations
# ---------------------------------------------------------------------------

IRREGULAR_VERBS: Dict[str, Dict[str, Dict[str, str]]] = {
    "ser": {
        "preterite": {"yo": "fui", "tú": "fuiste", "él": "fue", "nosotros": "fuimos", "ellos": "fueron"},
        "imperfect":  {"yo": "era", "tú": "eras",    "él": "era", "nosotros": "éramos",  "ellos": "eran"},
    },
    "estar": {
        "preterite": {"yo": "estuve",  "tú": "estuviste", "él": "estuvo",  "nosotros": "estuvimos",  "ellos": "estuvieron"},
        "imperfect":  {"yo": "estaba",  "tú": "estabas",   "él": "estaba",  "nosotros": "estábamos",  "ellos": "estaban"},
    },
    "ir": {
        "preterite": {"yo": "fui",  "tú": "fuiste", "él": "fue", "nosotros": "fuimos", "ellos": "fueron"},
        "imperfect":  {"yo": "iba",  "tú": "ibas",   "él": "iba", "nosotros": "íbamos", "ellos": "iban"},
    },
    "hacer": {
        "preterite": {"yo": "hice",  "tú": "hiciste", "él": "hizo",  "nosotros": "hicimos",  "ellos": "hicieron"},
        "imperfect":  {"yo": "hacía", "tú": "hacías",  "él": "hacía", "nosotros": "hacíamos", "ellos": "hacían"},
    },
    "tener": {
        "preterite": {"yo": "tuve",  "tú": "tuviste", "él": "tuvo",  "nosotros": "tuvimos",  "ellos": "tuvieron"},
        "imperfect":  {"yo": "tenía", "tú": "tenías",  "él": "tenía", "nosotros": "teníamos", "ellos": "tenían"},
    },
    "dar": {
        "preterite": {"yo": "di",   "tú": "diste", "él": "dio", "nosotros": "dimos",  "ellos": "dieron"},
        "imperfect":  {"yo": "daba", "tú": "dabas", "él": "daba","nosotros": "dábamos","ellos": "daban"},
    },
    "ver": {
        "preterite": {"yo": "vi",   "tú": "viste", "él": "vio", "nosotros": "vimos",  "ellos": "vieron"},
        "imperfect":  {"yo": "veía", "tú": "veías", "él": "veía","nosotros": "veíamos","ellos": "veían"},
    },
    "saber": {
        "preterite": {"yo": "supe",  "tú": "supiste", "él": "supo",  "nosotros": "supimos",  "ellos": "supieron"},
        "imperfect":  {"yo": "sabía", "tú": "sabías",  "él": "sabía", "nosotros": "sabíamos", "ellos": "sabían"},
    },
    "poder": {
        "preterite": {"yo": "pude",  "tú": "pudiste", "él": "pudo",  "nosotros": "pudimos",  "ellos": "pudieron"},
        "imperfect":  {"yo": "podía", "tú": "podías",  "él": "podía", "nosotros": "podíamos", "ellos": "podían"},
    },
    "querer": {
        "preterite": {"yo": "quise",  "tú": "quisiste", "él": "quiso",  "nosotros": "quisimos",  "ellos": "quisieron"},
        "imperfect":  {"yo": "quería", "tú": "querías",  "él": "quería", "nosotros": "queríamos", "ellos": "querían"},
    },
    "venir": {
        "preterite": {"yo": "vine",  "tú": "viniste", "él": "vino",  "nosotros": "vinimos",  "ellos": "vinieron"},
        "imperfect":  {"yo": "venía", "tú": "venías",  "él": "venía", "nosotros": "veníamos", "ellos": "venían"},
    },
    "decir": {
        "preterite": {"yo": "dije",  "tú": "dijiste", "él": "dijo",  "nosotros": "dijimos",  "ellos": "dijeron"},
        "imperfect":  {"yo": "decía", "tú": "decías",  "él": "decía", "nosotros": "decíamos", "ellos": "decían"},
    },
}

# ---------------------------------------------------------------------------
# Reflexive verbs
# ---------------------------------------------------------------------------

REFLEXIVE_VERBS: Dict[str, str] = {
    "levantarse":   "to get up",
    "ducharse":     "to shower",
    "despertarse":  "to wake up",
    "acostarse":    "to go to bed",
    "vestirse":     "to get dressed",
    "lavarse":      "to wash oneself",
    "peinarse":     "to comb one's hair",
    "sentarse":     "to sit down",
    "llamarse":     "to be called/named",
    "quedarse":     "to stay",
    "bañarse":      "to bathe",
    "afeitarse":    "to shave",
    "maquillarse":  "to put on makeup",
}

# Present-tense conjugations including stem-change verbs
REFLEXIVE_CONJUGATIONS: Dict[str, Dict[str, str]] = {
    "levantarse":  {"yo": "me levanto",  "tú": "te levantas",  "él": "se levanta"},
    "ducharse":    {"yo": "me ducho",    "tú": "te duchas",    "él": "se ducha"},
    "lavarse":     {"yo": "me lavo",     "tú": "te lavas",     "él": "se lava"},
    "sentarse":    {"yo": "me siento",   "tú": "te sientas",   "él": "se sienta"},   # e→ie
    "acostarse":   {"yo": "me acuesto",  "tú": "te acuestas",  "él": "se acuesta"},  # o→ue
    "vestirse":    {"yo": "me visto",    "tú": "te vistes",    "él": "se viste"},    # e→i
    "despertarse": {"yo": "me despierto","tú": "te despiertas","él": "se despierta"},# e→ie
    "llamarse":    {"yo": "me llamo",    "tú": "te llamas",    "él": "se llama"},
    "bañarse":     {"yo": "me baño",     "tú": "te bañas",     "él": "se baña"},
    "peinarse":    {"yo": "me peino",    "tú": "te peinas",    "él": "se peina"},
    "quedarse":    {"yo": "me quedo",    "tú": "te quedas",    "él": "se queda"},
    "afeitarse":   {"yo": "me afeito",   "tú": "te afeitas",   "él": "se afeita"},
    "maquillarse": {"yo": "me maquillo", "tú": "te maquillas", "él": "se maquilla"},
}

# ---------------------------------------------------------------------------
# Verb + preposition patterns
# ---------------------------------------------------------------------------

VERB_PREPOSITIONS: Dict[str, str] = {
    "acabar de":   "to have just (done something)",
    "tratar de":   "to try to",
    "dejar de":    "to stop (doing something)",
    "empezar a":   "to begin to",
    "aprender a":  "to learn to",
    "ayudar a":    "to help to",
    "soñar con":   "to dream about",
    "contar con":  "to count on",
    "tener que":   "to have to",
    "hay que":     "one must",
    "pensar en":   "to think about",
    "insistir en": "to insist on",
    "salir con":   "to go out with",
}

PREPOSITION_DRILLS: List[Dict[str, str]] = [
    {"verb": "ir",        "prep": "a",   "infinitive": "estudiar",  "english": "I'm going to study"},
    {"verb": "ir",        "prep": "a",   "infinitive": "trabajar",  "english": "I'm going to work"},
    {"verb": "empezar",   "prep": "a",   "infinitive": "llover",    "english": "It's starting to rain"},
    {"verb": "aprender",  "prep": "a",   "infinitive": "bailar",    "english": "I'm learning to dance"},
    {"verb": "pensar",    "prep": "en",  "infinitive": "ti",        "english": "I'm thinking of you"},
    {"verb": "soñar",     "prep": "con", "infinitive": "viajar",    "english": "I dream of traveling"},
    {"verb": "dejar",     "prep": "de",  "infinitive": "fumar",     "english": "Stop smoking"},
    {"verb": "tratar",    "prep": "de",  "infinitive": "ayudar",    "english": "Try to help"},
    {"verb": "hablar",    "prep": "de",  "infinitive": "política",  "english": "Talk about politics"},
    {"verb": "salir",     "prep": "con", "infinitive": "amigos",    "english": "Go out with friends"},
    {"verb": "insistir",  "prep": "en",  "infinitive": "pagar",     "english": "He insists on paying"},
    {"verb": "acabar",    "prep": "de",  "infinitive": "llegar",    "english": "I just arrived"},
]

# ---------------------------------------------------------------------------
# Practice sentences for dictation drills
# ---------------------------------------------------------------------------

PRACTICE_SENTENCES: List[Tuple[str, str]] = [
    ("Me levanto a las siete de la mañana", "I get up at 7 in the morning"),
    ("Me ducho y me visto rápidamente", "I shower and get dressed quickly"),
    ("Desayuno café con leche y tostadas", "I have coffee with milk and toast for breakfast"),
    ("Voy al trabajo en autobús", "I go to work by bus"),
    ("Me llamo Jeff y vivo en California", "My name is Jeff and I live in California"),
    ("Me acuesto a las once de la noche", "I go to bed at 11 at night"),
    ("Los fines de semana me despierto tarde", "On weekends I wake up late"),
    ("Me gusta estudiar español todos los días", "I like to study Spanish every day"),
    ("Ayer fui al supermercado con mi familia", "Yesterday I went to the supermarket with my family"),
    ("¿Puedes repetir eso más despacio, por favor?", "Can you repeat that more slowly, please?"),
    ("Tengo que terminar este trabajo antes del lunes", "I have to finish this work before Monday"),
    ("¿A qué hora empieza la película esta noche?", "What time does the movie start tonight?"),
]

# ---------------------------------------------------------------------------
# Listening comprehension sentences (Duolingo-style difficulty)
# ---------------------------------------------------------------------------

LISTENING_SENTENCES: List[Tuple[str, str]] = [
    ("¿Quién vendrá a reparar la lavadora?", "Who will come to repair the washing machine?"),
    ("Cuando llegué al supermercado, llamé a mi mamá", "When I got to the supermarket, I called my mom"),
    ("Cuando llegué a mi cuarto, encendí la radio", "When I got to my room, I turned on the radio"),
    ("Al entrar al banco, ¿hablaste con el policía?", "Upon entering the bank, did you speak with the police officer?"),
    ("¿Estos son tus zapatos deportivos?", "Are these your sneakers?"),
    ("Empiezan el día en la playa", "They start the day on the beach"),
    ("¿Tú te encuentras con Sofía hoy?", "Are you meeting with Sofia today?"),
    ("¿Está nevando allí?", "Is it snowing there?"),
    ("Aquí hay mucha lluvia", "There is a lot of rain here"),
    ("Pedro corrió cerca del río con su perro", "Pedro ran near the river with his dog"),
    ("¿Qué pasó?", "What happened?"),
    ("Sofía, asa la carne y el pollo", "Sofia, grill the meat and the chicken"),
    ("Ese actor famoso es rico", "That famous actor is rich"),
    ("¡Que tengas buen fin de semana!", "Have a good weekend!"),
    ("A ella le gusta ir a conciertos de rock", "She likes going to rock concerts"),
    ("Le estoy dando un reloj de plata", "I'm giving her a silver watch"),
    ("El arroz amarillo que cocinamos es delicioso", "The yellow rice we cooked is delicious"),
    ("¿A él le compras ropa nueva pero a mí no?", "You buy him new clothes but not me?"),
    ("¿Por qué le das un reloj de oro?", "Why are you giving him a gold watch?"),
    ("Le gusta el chocolate blanco", "He/She likes white chocolate"),
    ("Te gustan las flores blancas, pero a ella no", "You like white flowers, but she doesn't"),
    ("No me gustan las chaquetas de cuero", "I don't like leather jackets"),
    ("Los muchachos pudieron hablar veinte idiomas", "The young boys were able to speak twenty languages"),
    ("Suponemos que eso no es verdad", "We suppose that's not true"),
    ("El oso lleva puesta una chaqueta negra", "The bear is wearing a black jacket"),
    ("Llego temprano igual que tú", "I arrive early just like you do"),
    ("Nuestras mascotas nunca se odiaron", "Our pets never hated each other"),
    ("¿Cuánto tiempo llevas estudiando español?", "How long have you been studying Spanish?"),
    ("Hay que practicar todos los días para mejorar", "You have to practice every day to improve"),
    ("Me parece que ya hemos hablado de esto antes", "It seems to me we've talked about this before"),
]

# ---------------------------------------------------------------------------
# Conversation starters
# ---------------------------------------------------------------------------

CONVERSATION_STARTERS: List[str] = [
    "¿Cómo estás hoy?",
    "¿Qué hiciste este fin de semana?",
    "¿Cuál es tu comida favorita?",
    "¿Tienes planes para hoy?",
    "¿Qué te gusta hacer en tu tiempo libre?",
    "¿Has viajado recientemente?",
    "¿Qué estudiaste en la universidad?",
    "¿Tienes hermanos o hermanas?",
    "¿Cuál es tu película favorita?",
    "¿Practicas algún deporte?",
    "¿Qué música te gusta escuchar?",
    "¿Dónde creciste?",
    "¿Cuál es tu estación del año favorita?",
    "¿Tienes mascotas?",
    "¿Qué haces para relajarte?",
    "¿Qué hiciste ayer por la tarde?",
    "¿Cuál es tu libro favorito?",
    "¿Qué deportes te gustan?",
]

# ---------------------------------------------------------------------------
# Conversation prompts (for structured practice)
# ---------------------------------------------------------------------------

CONVERSATION_PROMPTS: List[Tuple[str, str]] = [
    ("¿Qué hiciste ayer?", "What did you do yesterday?"),
    ("¿Cuál es tu comida favorita?", "What is your favorite food?"),
    ("¿A qué hora te despiertas normalmente?", "What time do you normally wake up?"),
    ("¿Qué te gusta hacer los fines de semana?", "What do you like to do on weekends?"),
    ("¿Tienes mascotas?", "Do you have pets?"),
    ("¿Cuál es tu lugar favorito para visitar?", "What is your favorite place to visit?"),
    ("¿Qué tipo de música escuchas?", "What kind of music do you listen to?"),
    ("¿Qué comiste hoy?", "What did you eat today?"),
]


def get_content() -> dict:
    """Return all Spanish content as a single dict for DrillSystem."""
    return {
        "irregular_verbs":         IRREGULAR_VERBS,
        "reflexive_verbs":         REFLEXIVE_VERBS,
        "reflexive_conjugations":  REFLEXIVE_CONJUGATIONS,
        "verb_prepositions":       VERB_PREPOSITIONS,
        "preposition_drills":      PREPOSITION_DRILLS,
        "practice_sentences":      PRACTICE_SENTENCES,
        "listening_sentences":     LISTENING_SENTENCES,
        "conversation_starters":   CONVERSATION_STARTERS,
        "conversation_prompts":    CONVERSATION_PROMPTS,
    }
