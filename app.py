import streamlit as st
import google.generativeai as genai
import pandas as pd
import requests
import io
import difflib
import re
import json
import base64
import asyncio
import edge_tts
from datetime import datetime
from audio_recorder_streamlit import audio_recorder

st.set_page_config(page_title="Il tuo professore Alessandro online 😊", page_icon="😊")

COUNTRY_TO_LANG = {
    "brazil": "Portoghese (Brasiliano)",
    "brasil": "Portoghese (Brasiliano)",
    "usa": "Inglese",
    "united states": "Inglese",
    "uk": "Inglese",
    "united kingdom": "Inglese",
    "spain": "Spagnolo",
    "españa": "Spagnolo",
    "argentina": "Spagnolo",
    "mexico": "Spagnolo",
    "colombia": "Spagnolo",
    "france": "Francese",
    "germany": "Tedesco",
    "deutschland": "Tedesco",
    "russia": "Russo",
    "china": "Cinese",
    "japan": "Giapponese",
    "netherlands": "Olandese"
}

def clean_text_for_speech(text):
    text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', text)
    text = re.sub(r'[*_#`~]', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'!{2,}', '.', text)
    text = re.sub(r'!\?', '?', text)
    text = re.sub(r'\n+', ', ', text)
    text = re.sub(r'[^\w\s,;.?!:\'\-—àèéìòùÀÈÉÌÒÙ]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

async def genera_audio_neurale(text):
    clean_txt = clean_text_for_speech(text)
    if not clean_txt:
        return None
    communicate = edge_tts.Communicate(
        clean_txt,
        voice="it-IT-GiuseppeNeural",
        rate="-3%",
        pitch="-4Hz"
    )
    audio_stream = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_stream.write(chunk["data"])
    audio_stream.seek(0)
    return audio_stream.read()

def sintetizza_voce(text):
    try:
        return asyncio.run(genera_audio_neurale(text))
    except Exception:
        return None

def render_autoplay_audio(audio_bytes):
    b64 = base64.b64encode(audio_bytes).decode()
    audio_html = f"""
        <audio autoplay controls style="width: 100%; margin-top: 8px;">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            Il tuo browser non supporta l'audio tag.
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

def get_native_language(country_name):
    if not country_name or country_name == "Non specificato":
        return "Inglese"
    norm = country_name.strip().lower()
    return COUNTRY_TO_LANG.get(norm, f"Lingua ufficiale di {country_name}")

def invia_rating_su_sheet(rating, comment):
    apps_script_url = st.secrets.get("APPS_SCRIPT_URL", None)
    if not apps_script_url:
        return
    payload = {
        "action": "submit_rating",
        "rating": rating,
        "comment": comment
    }
    try:
        requests.post(apps_script_url, json=payload, timeout=8)
    except Exception:
        pass

def salva_sessione_su_sheet(student_name, message_count, activity, messages_list, model, progressi_precedenti):
    apps_script_url = st.secrets.get("APPS_SCRIPT_URL", None)
    if not apps_script_url or message_count <= 0:
        return None, None

    chat_transcript = "\n".join([f"{m['role']}: {m['content']}" for m in messages_list if "content" in m])
    
    prompt_sintesi = f"""
    Sei un supervisore didattico esperto. Analizza questa sessione di studio dell'italiano con lo studente {student_name}:
    [STORICO PRECEDENTE]
    {progressi_precedenti}

    [TRASCRIZIONE SESSIONE]
    {chat_transcript}
    
    Genera due valutazioni distinte e restituiscile ESCLUSIVAMENTE in JSON valido:
    {{
      "excel_summary": "Giudizio clinico, sintetico (massimo 2-3 frasi) e diretto per il docente: argomenti visti, se lo studente recepisce le correzioni o se è piantato/bloccato sugli stessi errori.",
      "student_feedback": "Feedback per lo studente con METODO SANDWICH rigoroso e sobrio:\\n\\n🇮🇹 **Valutazione della sessione:**\\n- **Punto di forza:** ...\\n- **Aspetto da migliorare:** ...\\n- **Prossimo passo:** ...\\n\\n🇬🇧 **Session feedback:**\\n- **Strength:** ...\\n- **Area for improvement:** ...\\n- **Next step:** ..."
    }}
    """
    
    excel_note = "Sessione monitorata."
    student_display_text = "Sessione conclusa regolarmente."
    
    try:
        res = model.generate_content(prompt_sintesi)
        raw_res = res.text.strip()
        if raw_res.startswith("```json"):
            raw_res = raw_res[7:]
        if raw_res.startswith("```"):
            raw_res = raw_res[3:]
        if raw_res.endswith("```"):
            raw_res = raw_res[:-3]
            
        parsed = json.loads(raw_res.strip())
        excel_note = parsed.get("excel_summary", excel_note)
        student_display_text = parsed.get("student_feedback", student_display_text)
    except Exception:
        excel_note = f"Sessione di {message_count} interazioni ({activity})."
        student_display_text = "🇮🇹 **Sessione completata con successo.**"

    payload = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "student": student_name,
        "message_count": message_count,
        "activity": activity,
        "summary": excel_note
    }
    
    try:
        requests.post(apps_script_url, json=payload, timeout=8)
    except Exception:
        pass
        
    return excel_note, student_display_text

# 1. Configurazione API
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("Errore di sistema con la chiave API. Controlla i Secrets su Streamlit.")
    st.stop()

# 2. Caricamento Dati
CSV_URL = st.secrets.get(
    "SHEET_URL", 
    "[https://docs.google.com/spreadsheets/d/1bEHnFNXYo5CGeDhHlKq23m8C8mDEW8s_TTZz7ZccjTk/export?format=csv](https://docs.google.com/spreadsheets/d/1bEHnFNXYo5CGeDhHlKq23m8C8mDEW8s_TTZz7ZccjTk/export?format=csv)"
)

try:
    r = requests.get(CSV_URL)
    r.raise_for_status()
    students_df = pd.read_csv(io.StringIO(r.text), dtype=str)
    students_df.columns = students_df.columns.str.strip() 
    students_df.fillna("Non specificato", inplace=True)
    students_df.set_index('Student', inplace=True)
except Exception as e:
    st.error(f"Errore caricamento dati: {e}")
    st.stop()

st.title("Il tuo professore Alessandro online 😊")

# Gestione identificazione
if "confirmed_student_name" not in st.session_state:
    st.session_state.confirmed_student_name = ""
if "is_identified" not in st.session_state:
    st.session_state.is_identified = False

col_input, col_reset = st.columns([4, 1])
with col_input:
    student_name_input = st.text_input(
        "Inserisci il tuo nome per iniziare:",
        value=st.session_state.confirmed_student_name,
        disabled=st.session_state.is_identified
    )

if st.session_state.is_identified:
    with col_reset:
        st.write("")
        if st.button("🔄 Cambia", help="Cambia studente"):
            st.session_state.is_identified = False
            st.session_state.confirmed_student_name = ""
            st.session_state.session_started = False
            st.session_state.support_lang_choice = None
            st.session_state.messages = []
            st.session_state.session_message_count = 0
            st.session_state.feedback_to_show = None
            st.session_state.exercises_completed = False
            st.session_state.roleplay_options = []
            st.session_state.roleplay_chosen = False
            st.rerun()

student_name = student_name_input.strip()

if student_name:
    if student_name in students_df.index:
        st.session_state.confirmed_student_name = student_name
        st.session_state.is_identified = True
        dati_studente = students_df.loc[student_name]
        
        if isinstance(dati_studente, pd.DataFrame):
            st.warning(f"Trovati più profili con il nome {student_name}.")
            nazioni = dati_studente['Country of Residence'].tolist()
            scelta_nazione = st.selectbox(
                "Per identificarti, seleziona il tuo Paese di Residenza:",
                ["Seleziona..."] + nazioni
            )
            if scelta_nazione == "Seleziona...":
                st.stop()
            else:
                dati_studente = dati_studente[dati_studente['Country of Residence'] == scelta_nazione].iloc[0]
        
        genere = dati_studente.get('Genere', 'M')
        if genere == 'F':
            st.success(f"Benvenuta, {student_name}! Pronta a fare pratica?")
        else:
            st.success(f"Benvenuto, {student_name}! Pronto a fare pratica?")

        # Inizializzazioni
        if "session_started" not in st.session_state:
            st.session_state.session_started = False
        if "voice_active_locked" not in st.session_state:
            st.session_state.voice_active_locked = False
        if "selected_activity_locked" not in st.session_state:
            st.session_state.selected_activity_locked = None
        if "support_lang_choice" not in st.session_state:
            st.session_state.support_lang_choice = None
        if "grammar_phase" not in st.session_state:
            st.session_state.grammar_phase = "choose_topic"
        if "grammar_options" not in st.session_state:
            st.session_state.grammar_options = []
        if "roleplay_options" not in st.session_state:
            st.session_state.roleplay_options = []
        if "roleplay_chosen" not in st.session_state:
            st.session_state.roleplay_chosen = False
        if "feedback_to_show" not in st.session_state:
            st.session_state.feedback_to_show = None
        if "rating_submitted" not in st.session_state:
            st.session_state.rating_submitted = False
        if "exercises_completed" not in st.session_state:
            st.session_state.exercises_completed = False

        livello_studente = dati_studente.get('Livello', 'Non specificato')
        country_birth = dati_studente.get('Country of Birth', 'Non specificato')
        lingua_nativa = get_native_language(country_birth)
        progressi_passati = dati_studente.get('Ultimi Progressi', 'Nessuna sessione registrata finora')
        
        is_sub_or_equal_a2 = any(sub in livello_studente.upper() for sub in ["A0", "A1", "A2", "PRINCIPIANTE", "BASE", "BEGINNER"])

        # Lingua di supporto per <= A2
        if is_sub_or_equal_a2 and not st.session_state.support_lang_choice:
            st.info(f"💡 Il tuo livello è **{livello_studente}**. Scegli la lingua per chiarimenti e traduzioni:")
            if st.button("🇬🇧 Inglese (English)", use_container_width=True):
                st.session_state.support_lang_choice = "Inglese"
                st.rerun()
            if st.button(f"🌐 Lingua nativa ({lingua_nativa})", use_container_width=True):
                st.session_state.support_lang_choice = lingua_nativa
                st.rerun()
            st.stop()
        elif not is_sub_or_equal_a2:
            st.session_state.support_lang_choice = "Solo Italiano"

        system_prompt = f"""
        # ITALIANO | PROFESSOR ALESSANDRO — TUTOR PERSONALE DI CONVERSAZIONE
        Ti chiami Alessandro. Sei il tutor personale di italiano dello studente {student_name}. Sei nato a Padova e sei un millennial: simpatico, empatico, acuto, con tono rilassato e pacato.
        
        [REGOLE DI TONO E PUNTEGGIATURA]
        - Usa una punteggiatura regolare (virgole, punti fermi).
        - NON usare MAI punti esclamativi multipli ("!!", "!!!").

        [DATI DELLO STUDENTE]
        - Livello CEFR: {livello_studente}
        - Paese di nascita: {country_birth}
        - Lingua nativa: {lingua_nativa}
        - Lingua supporto: {st.session_state.support_lang_choice}
        - Punti di miglioramento: {dati_studente.get('Punti di miglioramento', 'Nessuno specifico')}
        - Documento di teoria attuale: {dati_studente.get('Documento Teoria', 'Nessuno')}
        - Storico ultima sessione: {progressi_passati}

        [REGOLE DI CORREZIONE]
        - Se la frase dello studente è CORRETTA: NON usare "❌ / ✅". Prosegui naturalmente.
        - Se c'è un VERO errore:
          ❌ [Frase errata]
          ✅ [Frase corretta]
          (Spiegazione chiara e tranquilla in 1 riga).

        [MODALITÀ GRAMMATICA ED ESERCIZI]
        1. Spiegazione chiara e completa (coniugazioni e forme principali). Termina chiedendo se ha dubbi.
        2. Se non ha capito, rispiega usando {lingua_nativa} o {st.session_state.support_lang_choice}.
        3. Solo dopo conferma, proponi 3 esercizi elaborati (scelta multipla, completamento, trasformazione).

        [MODALITÀ ROLE-PLAY]
        - Definisci chiaramente i ruoli (chi sei tu e chi è lo studente).
        - Rimani rigorosamente nel personaggio interpretando uno scenario realistico con un piccolo imprevisto.

        [MODALITÀ SFIDA (CHALLENGE SU ERRORI)]
        - È una prova formativa mirata a correggere gli errori tipici dello studente (basati sui Punti di miglioramento).
        - Proponi sfide tecniche come: "Caccia all'errore" (trovare e correggere lo sbaglio nascosto tra frasi), "Gira la frase" (trasformare al passato o al condizionale senza errori), o quiz a trabocchetto sulle sue debolezze.

        [MODALITÀ GIOCO (ATTIVITÀ LUDICA)]
        - È un'attività puramente ricreativa e rilassata per stimolare la spontaneità.
        - Proponi giochi divertenti come: "Due verità e una bugia" (lo studente racconta 3 fatti e tu indovini la bugia facendogli domande, poi invertite), o "Il Detective delle parole" (descrivere un oggetto/concetto senza nominarlo).
        """

        model = genai.GenerativeModel(
            model_name='gemini-3.5-flash-lite',
            system_instruction=system_prompt
        )

        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "last_interaction_time" not in st.session_state:
            st.session_state.last_interaction_time = datetime.now()
        if "session_message_count" not in st.session_state:
            st.session_state.session_message_count = 0
        if "last_audio_processed" not in st.session_state:
            st.session_state.last_audio_processed = None

        # --- SCHERMATA FINE SESSIONE ---
        if st.session_state.feedback_to_show:
            st.success("🎉 **Sessione completata con successo!**")
            
            with st.container():
                st.markdown("### 📝 Il tuo resoconto didattico")
                st.markdown(st.session_state.feedback_to_show)

            st.write("---")
            st.markdown("### ⭐️ Valuta la sessione di oggi con Alessandro")
            
            if not st.session_state.rating_submitted:
                with st.form("form_valutazione_sessione", clear_on_submit=False):
                    voto_scelto = st.radio(
                        "Come ti è sembrata la lezione?",
                        ["👍 Molto utile e piacevole", "👎 Si può migliorare"],
                        horizontal=True
                    )
                    commento_studente = st.text_area(
                        "Lascia un commento o suggerimento per il professore (Opzionale):",
                        placeholder="Scrivi qui eventuali note prima di inviare...",
                        height=100
                    )
                    pulsante_invio = st.form_submit_button("📤 Invia valutazione e commento", use_container_width=True)
                    
                    if pulsante_invio:
                        voto_stringa = "Positivo (👍)" if "Molto utile" in voto_scelto else "Negativo (👎)"
                        with st.spinner("Salvataggio valutazione in corso..."):
                            invia_rating_su_sheet(voto_stringa, commento_studente.strip())
                            st.session_state.rating_submitted = True
                            st.rerun()
            else:
                st.info("Grazie per il tuo feedback! È stato registrato nel foglio del professore Alessandro. 😊")

            st.write("---")
            if st.button("✨ Inizia una nuova sessione", use_container_width=True):
                st.session_state.feedback_to_show = None
                st.session_state.session_started = False
                st.session_state.rating_submitted = False
                st.session_state.messages = []
                st.session_state.session_message_count = 0
                st.session_state.exercises_completed = False
                st.session_state.roleplay_options = []
                st.session_state.roleplay_chosen = False
                st.rerun()

            st.stop()

        # Configurazione attività con Sfida e Gioco separati (Gioco per ultimo)
        if not st.session_state.session_started:
            attivita = st.radio(
                "Cosa ti piacerebbe fare oggi?",
                [
                    "💬 1. Conversazione",
                    "📚 2. Grammatica ed Esercizi",
                    "🗣️ 3. Role-play",
                    "🎯 4. Sfida (Errori e Quiz)",
                    "🎲 5. Gioco"
                ],
                index=None,
                horizontal=True
            )

            voice_choice = False
            if attivita in ["💬 1. Conversazione", "🗣️ 3. Role-play"]:
                voice_choice = st.checkbox("🎙️ Vuoi attivare la modalità vocale (parlare al microfono e ascoltare)?", value=True)
            elif attivita is not None:
                st.caption("ℹ️ Questa attività si svolgerà in modalità testo per garantire massima precisione.")

            if not attivita:
                st.info("👆 Seleziona un'attività qui sopra per impostare la lezione.")
                st.stop()

            st.write("---")
            if st.button("🚀 Inizia sessione con Alessandro", use_container_width=True):
                st.session_state.session_started = True
                st.session_state.selected_activity_locked = attivita
                st.session_state.voice_active_locked = voice_choice
                st.session_state.modalita_attivita = attivita
                st.session_state.grammar_phase = "choose_topic"
                st.session_state.grammar_options = []
                st.session_state.roleplay_options = []
                st.session_state.roleplay_chosen = False
                st.session_state.exercises_completed = False
                st.rerun()

            st.stop()

        attivita = st.session_state.selected_activity_locked
        is_voice_mode = st.session_state.voice_active_locked

        st.caption(f"Modalità: **{attivita}** | Audio: **{'Attivo (Autoplay)' if is_voice_mode else 'Disattivato'}**")

        # Sidebar
        with st.sidebar:
            st.header("📊 La tua sessione")
            st.metric("Messaggi scambiati", st.session_state.session_message_count)
            if st.button("🏁 Termina sessione e salva", use_container_width=True):
                if st.session_state.session_message_count > 0:
                    with st.spinner("⏳ Aspetta un attimo, sto preparando i tuoi risultati...\n\n⏳ Just a moment, preparing your session results..."):
                        _, feedback_studente = salva_sessione_su_sheet(
                            student_name, 
                            st.session_state.session_message_count, 
                            attivita, 
                            st.session_state.messages, 
                            model,
                            progressi_passati
                        )
                    st.session_state.feedback_to_show = feedback_studente
                    st.session_state.messages = []
                    st.session_state.session_message_count = 0
                    st.session_state.session_started = False
                    st.rerun()
                else:
                    st.warning("Nessun messaggio da salvare.")

        # Inizializzazione primo messaggio
        if len(st.session_state.messages) == 0:
            if attivita == "📚 2. Grammatica ed Esercizi":
                with st.spinner("Alessandro sta analizzando i tuoi punti di miglioramento..."):
                    prompt_opt = f"""
                    In base a Punti di miglioramento: '{dati_studente.get('Punti di miglioramento')}' e Storico: '{progressi_passati}', proponi esattamente 3 argomenti grammaticali brevi (2-4 parole).
                    Restituisci solo un JSON array di 3 stringhe.
                    """
                    try:
                        res_opt = model.generate_content(prompt_opt)
                        raw_opt = res_opt.text.strip()
                        if "```json" in raw_opt:
                            raw_opt = raw_opt.split("```json")[1].split("```")[0]
                        elif "```" in raw_opt:
                            raw_opt = raw_opt.split("```")[1].split("```")[0]
                        st.session_state.grammar_options = json.loads(raw_opt.strip())[:3]
                    except Exception:
                        st.session_state.grammar_options = ["Condizionale presente", "Preposizioni articolate", "Passato prossimo"]

                    init_msg = (
                        f"Ciao {student_name}. Oggi lavoriamo sulla grammatica pratica. "
                        f"Ho selezionato 3 argomenti utili per te: clicca su quello che vuoi ripassare "
                        f"oppure scrivimi direttamente un argomento a tua scelta nella chat."
                    )
                    st.session_state.messages.append({"role": "model", "content": init_msg, "audio_bytes": None})
                    st.session_state.grammar_phase = "choose_topic"
                    st.rerun()

            elif attivita == "🗣️ 3. Role-play":
                with st.spinner("Alessandro sta preparando le ambientazioni per il Role-play..."):
                    prompt_rp = f"""
                    Proponi esattamente 3 situazioni di Role-play realistiche, divertenti e comunicative per uno studente di livello {livello_studente}.
                    Per ogni opzione definisci brevemente i due ruoli in modo accattivante (massimo 8-10 parole per opzione).
                    Restituisci SOLO un JSON array valido di 3 stringhe.
                    """
                    try:
                        res_rp = model.generate_content(prompt_rp)
                        raw_rp = res_rp.text.strip()
                        if "```json" in raw_rp:
                            raw_rp = raw_rp.split("```json")[1].split("```")[0]
                        elif "```" in raw_rp:
                            raw_rp = raw_rp.split("```")[1].split("```")[0]
                        st.session_state.roleplay_options = json.loads(raw_rp.strip())[:3]
                    except Exception:
                        st.session_state.roleplay_options = [
                            "Al ristorante: Tu sei il cliente, io il cameriere",
                            "In hotel: Tu devi fare il check-in, io il receptionist",
                            "In negozio: Tu vuoi cambiare un acquisto, io il commesso"
                        ]

                    init_msg = (
                        f"Ciao {student_name}! Mettiamoci alla prova con un Role-play a ruoli precisi. "
                        f"Ecco 3 scenari pensati per te: puoi sceglierne uno premendo il bottone qui sotto, "
                        f"oppure inventare qualsiasi situazione scrivendola in chat!"
                    )
                    init_audio = sintetizza_voce(init_msg) if is_voice_mode else None
                    st.session_state.messages.append({"role": "model", "content": init_msg, "audio_bytes": init_audio})
                    st.session_state.roleplay_chosen = False
                    st.rerun()

            elif attivita == "🎯 4. Sfida (Errori e Quiz)":
                with st.spinner("Alessandro sta preparando la tua sfida su misura..."):
                    prompt_sfida = f"Sei Alessandro. Lo studente ha scelto 'Sfida'. Proponigli subito una sfida accattivante sui suoi errori tipici: {dati_studente.get('Punti di miglioramento')} (ad esempio una caccia all'errore o una frase trabocchetto da sistemare)."
                    res_sf = model.generate_content(prompt_sfida)
                    init_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', res_sf.text).strip()
                    st.session_state.messages.append({"role": "model", "content": init_text, "audio_bytes": None})
                    st.session_state.last_interaction_time = datetime.now()
                    st.rerun()

            elif attivita == "🎲 5. Gioco":
                with st.spinner("Alessandro sta preparando il gioco..."):
                    prompt_gioco = f"Sei Alessandro. Lo studente ha scelto 'Gioco'. Proponigli subito un gioco linguistico divertente (es. 'Due verità e una bugia' o 'Indovina la parola misteriosa') spiegando brevemente come iniziare."
                    res_g = model.generate_content(prompt_gioco)
                    init_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', res_g.text).strip()
                    st.session_state.messages.append({"role": "model", "content": init_text, "audio_bytes": None})
                    st.session_state.last_interaction_time = datetime.now()
                    st.rerun()

            else:
                with st.spinner("Alessandro sta preparando la sessione..."):
                    prompt_avvio = f"Lo studente ha scelto '{attivita}'. Avvia la sessione salutandolo in modo pacato, amichevole e naturale, e poni la prima domanda stimolante."
                    res_init = model.generate_content(prompt_avvio)
                    init_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', res_init.text).strip()
                    init_audio = sintetizza_voce(init_text) if is_voice_mode else None

                    st.session_state.messages.append({"role": "model", "content": init_text, "audio_bytes": init_audio})
                    st.session_state.last_interaction_time = datetime.now()
                    st.rerun()

        # Cronologia messaggi
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes") and is_voice_mode:
                    if idx == len(st.session_state.messages) - 1 and msg["role"] == "model":
                        render_autoplay_audio(msg["audio_bytes"])
                    else:
                        st.audio(msg["audio_bytes"], format="audio/mp3")

        selected_button_text = None

        # Bottoni interattivi: GRAMMATICA
        if attivita == "📚 2. Grammatica ed Esercizi":
            if st.session_state.grammar_phase == "choose_topic" and st.session_state.grammar_options:
                st.write("**Scegli l'argomento da ripassare:**")
                for idx, opt in enumerate(st.session_state.grammar_options):
                    if st.button(f"📌 {opt}", key=f"topic_btn_{idx}", use_container_width=True):
                        selected_button_text = (
                            f"Vorrei ripassare: {opt}. Spiegami la regola in modo chiaro e completo, includendo tutte le coniugazioni ed eccezioni. "
                            f"Poi chiedimi con calma se ho capito prima di passare alla batteria di 3 esercizi."
                        )
                        st.session_state.grammar_phase = "theory_check"
                        st.session_state.exercises_completed = False
                st.caption("Oppure digita l'argomento che preferisci nella casella in basso 👇")

            elif st.session_state.grammar_phase == "theory_check":
                st.write("**Hai capito la spiegazione di Alessandro?**")
                if st.button("✅ Ho capito, facciamo i 3 esercizi!", key="btn_understood", use_container_width=True):
                    selected_button_text = (
                        "Ho capito la regola. Ora proponimi subito una batteria di 3 esercizi diversi: "
                        "1) Scelta multipla con opzioni A, B, C; 2) Frase da completare; 3) Frase da trasformare o comporre."
                    )
                    st.session_state.grammar_phase = "exercise"
                if st.button("❓ Non ho capito bene...", key="btn_not_understood", use_container_width=True):
                    selected_button_text = (
                        f"Non ho capito bene la spiegazione. Chiedimi con calma nella mia lingua ({lingua_nativa} o {st.session_state.support_lang_choice}) "
                        f"cosa non mi è chiaro e rispiegamelo con altri esempi semplici."
                    )

            elif st.session_state.grammar_phase == "exercise" and st.session_state.exercises_completed:
                st.write("**Vuoi continuare a fare pratica?**")
                col_ex1, col_ex2 = st.columns(2)
                with col_ex1:
                    if st.button("🔄 Altri 3 esercizi su questo argomento", use_container_width=True):
                        selected_button_text = "Voglio fare altri 3 esercizi elaborati su questo stesso argomento!"
                        st.session_state.exercises_completed = False
                with col_ex2:
                    if st.button("📚 Cambia argomento", use_container_width=True):
                        st.session_state.grammar_phase = "choose_topic"
                        st.session_state.exercises_completed = False
                        st.session_state.messages.append({
                            "role": "model", 
                            "content": "Perfetto! Scegli un altro argomento dai bottoni qui sopra oppure scrivimi cosa vorresti ripassare.",
                            "audio_bytes": None
                        })
                        st.rerun()

        # Bottoni interattivi: ROLE-PLAY
        if attivita == "🗣️ 3. Role-play" and not st.session_state.roleplay_chosen and st.session_state.roleplay_options:
            st.write("**Scegli lo scenario da simulare:**")
            for idx, opt in enumerate(st.session_state.roleplay_options):
                if st.button(f"🎭 {opt}", key=f"rp_btn_{idx}", use_container_width=True):
                    selected_button_text = f"Ho scelto questo Role-play: {opt}. Inizia tu la scena recitando la tua prima battuta nel tuo ruolo!"
                    st.session_state.roleplay_chosen = True
            st.caption("💡 Oppure inventa tu una situazione e descrivi i ruoli nella chat in basso 👇")

        # Input audio / testo
        audio_bytes = None
        if is_voice_mode:
            st.write("---")
            st.caption("🎙️ Premi per parlare o scrivi sotto:")
            audio_bytes = audio_recorder(text="Parla", recording_color="#e74c3c", neutral_color="#2ecc71", icon_size="2x")

        text_input = st.chat_input("Scrivi qui la tua risposta...")

        new_audio = (audio_bytes is not None and audio_bytes != st.session_state.last_audio_processed)
        user_display = None
        payload_parts = None

        if selected_button_text:
            user_display = selected_button_text
            payload_parts = [selected_button_text]
        elif text_input:
            user_display = text_input
            payload_parts = [text_input]
            if attivita == "📚 2. Grammatica ed Esercizi":
                if st.session_state.grammar_phase == "choose_topic":
                    st.session_state.grammar_phase = "theory_check"
                elif st.session_state.grammar_phase == "exercise":
                    st.session_state.exercises_completed = True
            elif attivita == "🗣️ 3. Role-play":
                st.session_state.roleplay_chosen = True
        elif new_audio:
            st.session_state.last_audio_processed = audio_bytes
            user_display = "🎤 *Messaggio vocale inviato*"
            payload_parts = [
                {"mime_type": "audio/wav", "data": audio_bytes},
                "Ascolta questo audio e rispondi direttamente come tutor Alessandro con tono calmo. Non inserire timestamp."
            ]
            if attivita == "🗣️ 3. Role-play":
                st.session_state.roleplay_chosen = True

        if user_display and payload_parts:
            st.session_state.last_interaction_time = datetime.now()
            st.session_state.session_message_count += 1

            st.session_state.messages.append({"role": "user", "content": user_display})
            with st.chat_message("user"):
                st.markdown(user_display)
                
            try:
                contents = []
                for m in st.session_state.messages[:-1]:
                    ruolo = "model" if m["role"] == "model" else "user"
                    contents.append({"role": ruolo, "parts": [m["content"]]})
                
                contents.append({"role": "user", "parts": payload_parts})
                
                response = model.generate_content(contents)
                raw_text = response.text
                bot_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', raw_text).strip()

                bot_audio = sintetizza_voce(bot_text) if is_voice_mode else None

                st.session_state.messages.append({
                    "role": "model", 
                    "content": bot_text,
                    "audio_bytes": bot_audio
                })

                st.rerun()

            except Exception as e:
                st.error(f"Errore Tecnico API: {e}")
                st.session_state.messages.pop()

    else:
        st.session_state.is_identified = False
        tutti_nomi = students_df.index.unique().dropna().astype(str).tolist()
        simili = difflib.get_close_matches(student_name, tutti_nomi, n=3, cutoff=0.5)
        if simili:
            st.warning("Nome non trovato nel registro. Forse intendevi:")
            for idx, match in enumerate(simili):
                if st.button(f"👉 {match}", key=f"btn_match_{idx}", use_container_width=True):
                    st.session_state.confirmed_student_name = match
                    st.session_state.is_identified = True
                    st.rerun()
        else:
            st.warning("Nome non trovato nel registro. Controlla come lo hai scritto o contatta il professore Alessandro!")
