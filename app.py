import streamlit as st
import google.generativeai as genai
import pandas as pd
import requests
import io
import difflib
import re
import json
from datetime import datetime
from gtts import gTTS
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
    text = re.sub(r'[^\w\s,;.?!:\'\-—àèéìòùÀÈÉÌÒÙ]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_native_language(country_name):
    if not country_name or country_name == "Non specificato":
        return "Inglese"
    norm = country_name.strip().lower()
    return COUNTRY_TO_LANG.get(norm, f"Lingua ufficiale di {country_name}")

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
      "student_feedback": "Feedback per lo studente con METODO SANDWICH rigoroso e sobrio (senza enfasi eccessiva):\\n\\n🇮🇹 **Valutazione della sessione:**\\n- **Punto di forza:** ...\\n- **Aspetto da migliorare:** ...\\n- **Prossimo passo:** ...\\n\\n🇬🇧 **Session feedback:**\\n- **Strength:** ...\\n- **Area for improvement:** ...\\n- **Next step:** ..."
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

if "confirmed_student_name" not in st.session_state:
    st.session_state.confirmed_student_name = ""

student_name_input = st.text_input(
    "Inserisci il tuo nome per iniziare:",
    value=st.session_state.confirmed_student_name
)
student_name = student_name_input.strip()

if student_name:
    if student_name in students_df.index:
        st.session_state.confirmed_student_name = student_name
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

        # Inizializzazioni di sessione
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

        livello_studente = dati_studente.get('Livello', 'Non specificato')
        country_birth = dati_studente.get('Country of Birth', 'Non specificato')
        lingua_nativa = get_native_language(country_birth)
        
        is_sub_or_equal_a2 = any(sub in livello_studente.upper() for sub in ["A0", "A1", "A2", "PRINCIPIANTE", "BASE", "BEGINNER"])

        # Selezione lingua di supporto per <= A2 (uno sotto l'altro)
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

        # Configurazione attività
        if not st.session_state.session_started:
            attivita = st.radio(
                "Cosa ti piacerebbe fare oggi?",
                [
                    "💬 1. Conversazione",
                    "📚 2. Grammatica ed Esercizi",
                    "🗣️ 3. Role-play",
                    "🎯 4. Sfida & Giochi"
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
                st.rerun()

            st.stop()

        attivita = st.session_state.selected_activity_locked
        is_voice_mode = st.session_state.voice_active_locked
        chosen_support_lang = st.session_state.support_lang_choice

        st.caption(f"Modalità: **{attivita}** | Audio: **{'Attivo' if is_voice_mode else 'Disattivato'}** | Lingua supporto: **{chosen_support_lang}**")

        progressi_passati = dati_studente.get('Ultimi Progressi', 'Nessuna sessione registrata finora')

        system_prompt = f"""
        # ITALIANO | PROFESSOR ALESSANDRO — TUTOR PERSONALE DI CONVERSAZIONE

        Ti chiami Alessandro. Sei il tutor personale di italiano dello studente {student_name}. Sei nato a Padova e sei un millennial: simpatico, empatico, brillante e acuto. Correggi con precisione per far migliorare realmente i tuoi studenti.
        Il tuo obiettivo è portare lo studente a comunicare con naturalezza e padronanza.

        [DATI DELLO STUDENTE]
        - Livello CEFR stimato: {livello_studente}
        - Paese di nascita: {country_birth}
        - Lingua nativa desunta: {lingua_nativa}
        - Lingua di supporto concordata: {chosen_support_lang}
        - Motivazione: {dati_studente.get('Reason to learn', 'Migliorare l italiano')}
        - Punti di miglioramento ed errori ricorrenti: {dati_studente.get('Punti di miglioramento', 'Nessuno specifico')}
        - Documento di teoria attuale nel corso: {dati_studente.get('Documento Teoria', 'Nessuno')}
        - Storico ultima sessione: {progressi_passati}

        [REGOLA SULLA LINGUA E LIVELLO QCER/CEFR]
        - Se il livello è pari o inferiore ad A2 (A0, A1, A2): usa l'italiano chiaro, ma affianca spiegazioni ed esempi nella lingua di supporto scelta: {chosen_support_lang}.
        - Se lo studente dice di NON aver capito, intervieni con cura rispiegando e chiedendo chiarimenti nella sua lingua nativa ({lingua_nativa}).
        - Se il livello è superiore ad A2 (B1+), usa esclusivamente l'italiano.

        [PROGRESSIONE DIDATTICA E SYLLABUS (Doc 01 - 12)]
        Non superare mai il documento attuale: {dati_studente.get('Documento Teoria', 'Nessuno')}.
        Doc 01: Presentarsi, Essere/Avere presente, aggettivi possessivi.
        Doc 02: Routine, verbi regolari, modali, Andare/Fare, riflessivi, negazione.
        Doc 03: Bar/ristorante, indicazioni. Passato Prossimo, verbi invertiti (Piacere).
        Doc 04: Famiglia, Condizionale presente e passato, pronomi interrogativi.
        Doc 05: Meteo, tempo, futuro semplice e perifrasi future.
        Doc 06: Uscite, imperativo, pronomi diretti, preposizioni articolate.
        Doc 07: Discussioni, dimostrativi, partitivi, verbi in -isc.
        Doc 08: Emergenze, imperfetto, particelle ci e ne.
        Doc 09: Passioni, pronomi indiretti e combinati, stare + gerundio.
        Doc 10: Esperienze, congiuntivo presente e passato, comparativi/superlativi.
        Doc 11: Opinioni, congiuntivo imperfetto/trapassato, periodo ipotetico.
        Doc 12: Confronto culturale, trapassato prossimo, passivo, connettivi logici.

        [MODALITÀ GRAMMATICA ED ESERCIZI — REGOLE SPIEGAZIONE ED ESERCIZI]
        Quando lo studente sceglie un argomento grammaticale:
        1. FORNISCI UNA SPIEGAZIONE BREVE MA COMPLETA:
           - Spiega la regola senza giri di parole inutili, ma INCLUDI LO SCHEMA COMPLETO (es. se è un tempo verbale, metti la coniugazione per tutte le persone: io, tu, lui/lei, noi, voi, loro).
           - Menziona chiaramente le eccezioni o le forme irregolari principali più frequenti.
           - Fornisci 1-2 frasi di esempio concrete.
           - NON inviare subito gli esercizi: termina il messaggio chiedendo se la spiegazione è chiara e se ha dubbi.
        2. Se lo studente dice di non aver capito, rispiega il passaggio critico usando {lingua_nativa} o {chosen_support_lang} e chiedigli esattamente cosa non torna.
        3. Solo quando lo studente conferma di aver capito ("Ho capito, facciamo gli esercizi!"), proponi 2-3 esercizi pratici mirati (scelta multipla o completamento frase).

        [STILE DI CORREZIONE]
        - Schema sobrio: ❌ Forma usata | ✅ Forma corretta | Spiegazione chiara.
        - Non inserire mai timestamp o riferimenti orari nel testo.
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
        if "feedback_to_show" not in st.session_state:
            st.session_state.feedback_to_show = None

        # Controllo inattività > 1 ora
        adesso = datetime.now()
        tempo_trascorso = (adesso - st.session_state.last_interaction_time).total_seconds()
        
        if tempo_trascorso > 3600 and st.session_state.session_message_count > 0:
            with st.spinner("Archivio sessione precedente..."):
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
            st.info("È trascorsa più di 1 ora dall'ultimo accesso: sessione precedente archiviata.")

        # Sidebar
        with st.sidebar:
            st.header("📊 La tua sessione")
            st.metric("Messaggi scambiati", st.session_state.session_message_count)
            if st.button("🏁 Termina sessione e salva", use_container_width=True):
                if st.session_state.session_message_count > 0:
                    with st.spinner("Salvataggio su Google Sheets in corso..."):
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

        # Schermata feedback finale
        if st.session_state.feedback_to_show:
            st.success("Sessione completata e registrata!")
            with st.expander("📝 Resoconto didattico di Alessandro", expanded=True):
                st.markdown(st.session_state.feedback_to_show)
            if st.button("✨ Nuova sessione", use_container_width=True):
                st.session_state.feedback_to_show = None
                st.session_state.session_started = False
                st.session_state.support_lang_choice = None
                st.rerun()

        # Avvio della sessione (primo turno)
        if len(st.session_state.messages) == 0 and not st.session_state.feedback_to_show:
            if attivita == "📚 2. Grammatica ed Esercizi":
                with st.spinner("Alessandro sta analizzando i tuoi punti di miglioramento..."):
                    prompt_opt = f"""
                    In base a Punti di miglioramento: '{dati_studente.get('Punti di miglioramento')}' e Storico: '{progressi_passati}', proponi esattamente 3 argomenti grammaticali da ripassare.
                    REGOLA TESTO CORTO: Ogni argomento deve essere brevissimo (massimo 2-4 parole, es: "Condizionale presente", "Preposizioni articolate", "Passato prossimo").
                    Restituiscili SOLO come JSON array di 3 stringhe brevi, es: ["Condizionale presente", "Preposizioni articolate", "Verbi riflessivi"]
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
                        st.session_state.grammar_options = [
                            "Condizionale presente",
                            "Preposizioni articolate",
                            "Passato prossimo"
                        ]

                    init_msg = (
                        f"Ciao {student_name}! Oggi lavoriamo sulla grammatica pratica. "
                        f"Ho selezionato per te 3 argomenti su cui possiamo concentrarci: clicca su quello che vuoi ripassare "
                        f"oppure scrivimi direttamente un argomento a tua scelta nella chat!"
                    )
                    st.session_state.messages.append({"role": "model", "content": init_msg, "audio_bytes": None})
                    st.session_state.grammar_phase = "choose_topic"
                    st.rerun()
            else:
                with st.spinner("Alessandro sta preparando la sessione..."):
                    prompt_avvio = f"Lo studente ha scelto '{attivita}'. Avvia la sessione salutandolo in modo brillante e proponi la prima domanda stimolante."
                    res_init = model.generate_content(prompt_avvio)
                    init_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', res_init.text).strip()

                    init_audio = None
                    if is_voice_mode:
                        clean_text = clean_text_for_speech(init_text)
                        if clean_text:
                            buf = io.BytesIO()
                            tts = gTTS(text=clean_text, lang='it', slow=False)
                            tts.write_to_fp(buf)
                            buf.seek(0)
                            init_audio = buf.read()

                    st.session_state.messages.append({"role": "model", "content": init_text, "audio_bytes": init_audio})
                    st.session_state.last_interaction_time = datetime.now()
                    st.rerun()

        # Visualizzazione cronologia messaggi
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes") and is_voice_mode:
                    st.audio(msg["audio_bytes"], format="audio/mp3")

        # Bottoni interattivi disposti verticalmente per evitare tagli di testo
        selected_button_text = None
        if attivita == "📚 2. Grammatica ed Esercizi":
            if st.session_state.grammar_phase == "choose_topic" and st.session_state.grammar_options:
                st.write("**Scegli l'argomento da ripassare:**")
                for idx, opt in enumerate(st.session_state.grammar_options):
                    if st.button(f"📌 {opt}", key=f"topic_btn_{idx}", use_container_width=True):
                        selected_button_text = (
                            f"Vorrei ripassare: {opt}. Spiegami la regola in modo chiaro e sintetico, includendo tutte le coniugazioni/forme ed eventuali eccezioni importanti. "
                            f"Poi chiedimi se ho capito prima di passare agli esercizi."
                        )
                        st.session_state.grammar_phase = "theory_check"
                st.caption("Oppure digita l'argomento che preferisci nella casella in basso 👇")

            elif st.session_state.grammar_phase == "theory_check":
                st.write("**Hai capito la spiegazione di Alessandro?**")
                if st.button("✅ Ho capito, facciamo gli esercizi!", key="btn_understood", use_container_width=True):
                    selected_button_text = "Ho capito la regola! Ora fammi fare subito degli esercizi pratici ed efficaci per verificare."
                    st.session_state.grammar_phase = "exercise"
                if st.button("❓ Non ho capito bene...", key="btn_not_understood", use_container_width=True):
                    selected_button_text = (
                        f"Non ho capito bene la spiegazione. Chiedimi con empatia nella mia lingua ({lingua_nativa} o {chosen_support_lang}) "
                        f"cosa non mi è chiaro e rispiegamelo con altri esempi semplici."
                    )

        # Gestione Input
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
            if attivita == "📚 2. Grammatica ed Esercizi" and st.session_state.grammar_phase == "choose_topic":
                st.session_state.grammar_phase = "theory_check"
        elif new_audio:
            st.session_state.last_audio_processed = audio_bytes
            user_display = "🎤 *Messaggio vocale inviato*"
            payload_parts = [
                {"mime_type": "audio/wav", "data": audio_bytes},
                "Ascolta questo audio e rispondi direttamente come tutor Alessandro. Non inserire timestamp."
            ]

        if user_display and payload_parts:
            st.session_state.feedback_to_show = None
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

                bot_audio = None
                if is_voice_mode:
                    clean_text = clean_text_for_speech(bot_text)
                    if clean_text:
                        buf = io.BytesIO()
                        tts = gTTS(text=clean_text, lang='it', slow=False)
                        tts.write_to_fp(buf)
                        buf.seek(0)
                        bot_audio = buf.read()

                st.session_state.messages.append({
                    "role": "model", 
                    "content": bot_text,
                    "audio_bytes": bot_audio
                })

                with st.chat_message("model"):
                    st.markdown(bot_text)
                    if bot_audio and is_voice_mode:
                        st.audio(bot_audio, format="audio/mp3")

                st.rerun()

            except Exception as e:
                st.error(f"Errore Tecnico API: {e}")
                st.session_state.messages.pop()

    else:
        tutti_nomi = students_df.index.unique().dropna().astype(str).tolist()
        simili = difflib.get_close_matches(student_name, tutti_nomi, n=3, cutoff=0.5)
        if simili:
            st.warning("Nome non trovato nel registro. Forse intendevi:")
            for idx, match in enumerate(simili):
                if st.button(f"👉 {match}", key=f"btn_match_{idx}", use_container_width=True):
                    st.session_state.confirmed_student_name = match
                    st.rerun()
        else:
            st.warning("Nome non trovato nel registro. Controlla come lo hai scritto o contatta il professore Alessandro!")
