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

def clean_text_for_speech(text):
    text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', text)
    text = re.sub(r'[*_#`~]', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'[^\w\s,;.?!:\'\-—àèéìòùÀÈÉÌÒÙ]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def salva_sessione_su_sheet(student_name, message_count, activity, messages_list, model, progressi_precedenti):
    apps_script_url = st.secrets.get("APPS_SCRIPT_URL", None)
    if not apps_script_url or message_count <= 0:
        return None, None

    chat_transcript = "\n".join([f"{m['role']}: {m['content']}" for m in messages_list if "content" in m])
    
    prompt_sintesi = f"""
    Sei un supervisore didattico esperto. Analizza questa sessione di studio della lingua italiana tra il tutor Alessandro e lo studente {student_name}:
    [STORICO PRECEDENTE DELLO STUDENTE]
    {progressi_precedenti}

    [TRASCRIZIONE SESSIONE ATTUALE]
    {chat_transcript}
    
    Genera due valutazioni distinte e restituiscile ESCLUSIVAMENTE come JSON valido:
    {{
      "excel_summary": "Giudizio clinico, sintetico (massimo 2-3 frasi) e diretto per il registro privato del docente. Niente convenevoli. Valuta esplicitamente la traiettoria: lo studente recepisce le correzioni e le applica o è piantato/bloccato sugli stessi errori? Specifica chiaramente gli argomenti e le strutture grammaticali/lessicali su cui inciampa o eccelle.",
      "student_feedback": "Feedback per lo studente con METODOLOGIA SANDWICH rigorosa. Tono pacato, sobrio, equilibrato e non enfatico (evita eccessi di entusiasmo, punti esclamativi forzati e complimenti artificiali).\\n\\nStruttura richiesta esatta:\\n\\n🇮🇹 **Valutazione della sessione:**\\n- **Punto di forza:** Un aspetto specifico che ha gestito bene o un'espressione usata correttamente.\\n- **Aspetto da migliorare:** Un errore chiaro, una lacuna grammaticale o un'abitudine linguistica da correggere.\\n- **Prossimo passo:** Un consiglio pratico e costruttivo per la prossima volta.\\n\\n🇬🇧 **Session feedback:**\\n- **Strength:** (Traduzione fedele del punto di forza)\\n- **Area for improvement:** (Traduzione fedele dell'aspetto da migliorare)\\n- **Next step:** (Traduzione fedele del consiglio pratico)"
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
        excel_note = f"Sessione di {message_count} interazioni ({activity}). Necessaria revisione manuale."
        student_display_text = "🇮🇹 **Valutazione della sessione:**\n- **Punto di forza:** Partecipazione attiva.\n- **Aspetto da migliorare:** Verifica dell'accuratezza verbale.\n- **Prossimo passo:** Rivedere le strutture affrontate oggi.\n\n🇬🇧 **Session feedback:**\n- **Strength:** Active engagement.\n- **Area for improvement:** Check verbal accuracy.\n- **Next step:** Review the structures covered today."

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
    if "<html" in r.text.lower():
        st.error("Google sta bloccando il file.")
        st.stop()
        
    students_df = pd.read_csv(io.StringIO(r.text), dtype=str)
    students_df.columns = students_df.columns.str.strip() 
    students_df.fillna("Non specificato", inplace=True)
    students_df.set_index('Student', inplace=True)
except Exception as e:
    st.error(f"Errore caricamento dati: {e}")
    st.stop()

st.title("Il tuo professore Alessandro online 😊")

# Gestione nome in session_state per supportare il click rapido del suggerimento
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
        
        # Gestione omonimi
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

        # Stato della sessione
        if "session_started" not in st.session_state:
            st.session_state.session_started = False
        if "voice_active_locked" not in st.session_state:
            st.session_state.voice_active_locked = False
        if "selected_activity_locked" not in st.session_state:
            st.session_state.selected_activity_locked = None

        # Configurazione prima dell'avvio
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

            # Opzione vocale solo per Conversazione e Role-play
            voice_choice = False
            if attivita in ["💬 1. Conversazione", "🗣️ 3. Role-play"]:
                voice_choice = st.checkbox("🎙️ Vuoi attivare la modalità vocale (parlare al microfono e ascoltare)?", value=True)
            elif attivita is not None:
                st.caption("ℹ️ Questa attività si svolgerà in modalità solo testo.")

            if not attivita:
                st.info("👆 Seleziona un'attività qui sopra per impostare la lezione.")
                st.stop()

            st.write("---")
            if st.button("🚀 Inizia sessione con Alessandro"):
                st.session_state.session_started = True
                st.session_state.selected_activity_locked = attivita
                st.session_state.voice_active_locked = voice_choice
                st.session_state.modalita_attivita = attivita
                st.rerun()

            st.stop()

        # Sessione in corso (scelte bloccate)
        attivita = st.session_state.selected_activity_locked
        is_voice_mode = st.session_state.voice_active_locked

        st.caption(f"Modalità attiva: **{attivita}** | Audio: **{'Attivo' if is_voice_mode else 'Disattivato'}**")

        progressi_passati = dati_studente.get('Ultimi Progressi', 'Nessuna sessione registrata finora')
        livello_studente = dati_studente.get('Livello', 'Non specificato')

        system_prompt = f"""
        # ITALIANO | PROFESSOR ALESSANDRO — TUTOR PERSONALE DI CONVERSAZIONE

        Ti chiami Alessandro. Sei il tutor personale di italiano dello studente {student_name}. Sei nato a Padova e sei un millennial: sei simpatico, empatico, ma molto acuto. Hai la battuta pronta, sai far ridere, ma correggi con precisione per far migliorare realmente i tuoi studenti.
        Il tuo obiettivo è portare lo studente a comunicare con naturalezza e autonomia, eliminando la traduzione mentale.

        [DATI DELLO STUDENTE]
        - Livello CEFR stimato: {livello_studente}
        - Paese di origine / Residenza: {dati_studente.get('Country of Birth', '')} / {dati_studente.get('Country of Residence', '')}
        - Motivazione: {dati_studente.get('Reason to learn', 'Migliorare l italiano')}
        - Punti di miglioramento ed errori ricorrenti: {dati_studente.get('Punti di miglioramento', 'Nessuno specifico')}
        - Documento di teoria attuale nel corso: {dati_studente.get('Documento Teoria', 'Nessuno')}
        - Storico ultima sessione: {progressi_passati}

        [REGOLA SULLA LINGUA E LIVELLO QCER/CEFR]
        1. Se il livello è INFERIORE ad A2 (A0, A1, Principiante assoluto):
           - Usa un italiano semplice, chiaro e ad alta frequenza.
           - Fornisci le istruzioni delle attività e le spiegazioni grammaticali affiancando SEMPRE una spiegazione o traduzione sintetica in INGLESE.
        2. Se il livello è A2 o SUPERIORE:
           - Usa ESCLUSIVAMENTE l'italiano per dialogare, spiegare, correggere ed esercitare.
           - Ricorri all'inglese solo se lo studente dichiara esplicitamente di non comprendere dopo una riformulazione in italiano.

        [PROGRESSIONE DIDATTICA E SYLLABUS (Doc 01 - 12)]
        Il "Documento di teoria attuale" indica il confine massimo di apprendimento. Lo studente conosce i documenti precedenti. Non usare MAI strutture grammaticali o lessico specialistico appartenenti a documenti successivi.
        - Doc 01: Presentarsi, saluti, nazionalità, professioni. Essere/Avere presente, aggettivi possessivi.
        - Doc 02: Routine, casa, sport, giorni, stagioni. Numeri 0-20. Verbi regolari (-are, -ere, -ire), modali, Andare/Fare presente, riflessivi, negazione.
        - Doc 03: Ordinare al bar/ristorante, indicazioni in città, acquisti e iscrizioni. Numeri 21-100. Articoli determinativi. Passato Prossimo (Avere/Essere), participi regolari/irregolari. Verbi invertiti (Piacere, Mancare).
        - Doc 04: Famiglia, amici, relazioni sociali, muoversi in città. Pronomi interrogativi, uso di "Che". Indeterminativi. Condizionale presente e passato.
        - Doc 05: Meteo, tempo, mesi. Preposizioni/avverbi di luogo. Futuro semplice, perifrasi future.
        - Doc 06: Uscite e locali. Preposizioni articolate. Imperativo. Pronomi diretti.
        - Doc 07: Discussioni ed emozioni forti/calme. Dimostrativi, partitivi, verbi in -isc.
        - Doc 08: Emergenze e soccorso. Preposizioni di tempo. Particelle "ci" e "ne". Indicativo imperfetto.
        - Doc 09: Hobby e passioni. Pronomi indiretti e combinati. Gerundio e stare + gerundio. Struttura della frase complessa.
        - Doc 10: Esperienze e viaggi. Congiuntivo presente e passato. Comparativi e superlativi.
        - Doc 11: Opinioni e dibattito. Congiuntivo imperfetto e trapassato. Periodo ipotetico. Verbi pronominali. Si impersonale.
        - Doc 12: Confronto culturale. Trapassato prossimo. Forma passiva. Indefiniti, rafforzativi, connettivi complessi.

        [MODALITÀ ATTIVA: {attivita}]
        Adatta la risposta in base all'attività scelta:
        1. 💬 Conversazione:
           - Dialogo amichevole e stimolante su temi quotidiani, calibrato al livello. Fai una domanda alla volta.
        2. 📚 Grammatica ed Esercizi:
           - Chiedi quale argomento desidera approfondire. Se non specificato, seleziona un punto critico incrociando [Storico ultima sessione: {progressi_passati}], [Punti di miglioramento] e [Documento di teoria attuale].
           - STRUTTURA: 1) Brevissima spiegazione teorica (massimo 2 frasi + esempio); 2) Subito un micro-esercizio (scelta multipla, completamento o trasformazione) da risolvere subito.
        3. 🗣️ Role-play:
           - Chiedi quale situazione reale desidera simulare. Se non sceglie, proponila tu con un piccolo imprevisto realistico. Rimani nel personaggio.
        4. 🎯 Sfida & Giochi:
           - Proponi attività ludiche mirate (es. "Due verità e una bugia", "Caccia all'errore" sui suoi tipici sbagli, o "Il Detective delle parole").

        [STILE DI CORREZIONE]
        - Quando correggi, usa questo schema sobrio:
          ❌ Forma usata
          ✅ Forma corretta
          (Spiegazione rapida del perché, in inglese se livello < A2, altrimenti in italiano).
        - Niente complimenti forzati. Sii autentico, caloroso e concreto.
        - Non generare timestamp o riferimenti orari nel testo.
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
            with st.spinner("Archivio la sessione precedente..."):
                _, feedback_studente = salva_sessione_su_sheet(
                    student_name, 
                    st.session_state.session_message_count, 
                    st.session_state.selected_activity_locked, 
                    st.session_state.messages, 
                    model,
                    progressi_passati
                )
            st.session_state.feedback_to_show = feedback_studente
            st.session_state.messages = []
            st.session_state.session_message_count = 0
            st.session_state.session_started = False
            st.info("È trascorsa più di 1 ora dall'ultimo accesso: sessione salvata.")

        # Sidebar
        with st.sidebar:
            st.header("📊 La tua sessione")
            st.metric("Messaggi scambiati", st.session_state.session_message_count)
            if st.button("🏁 Termina sessione e salva"):
                if st.session_state.session_message_count > 0:
                    with st.spinner("Analisi e salvataggio in corso..."):
                        _, feedback_studente = salva_sessione_su_sheet(
                            student_name, 
                            st.session_state.session_message_count, 
                            st.session_state.selected_activity_locked, 
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
                    st.warning("Non ci sono messaggi scambiati in questa sessione.")

        # Schermata di feedback di fine sessione
        if st.session_state.feedback_to_show:
            st.success("Sessione completata e registrata.")
            with st.expander("📝 Resoconto didattico di Alessandro", expanded=True):
                st.markdown(st.session_state.feedback_to_show)
            if st.button("✨ Nuova sessione"):
                st.session_state.feedback_to_show = None
                st.rerun()

        # Generazione della prima battuta di Alessandro
        if len(st.session_state.messages) == 0 and not st.session_state.feedback_to_show:
            with st.spinner("Alessandro sta preparando la sessione..."):
                prompt_avvio = f"Lo studente ha scelto '{attivita}'. Avvia la sessione salutandolo in modo naturale e proponendo subito la prima battuta o domanda stimolante adatta alla modalità e al suo livello."
                res_init = model.generate_content(prompt_avvio)
                init_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', res_init.text).strip()

                init_audio = None
                if is_voice_mode:
                    clean_text = clean_text_for_speech(init_text)
                    if clean_text:
                        audio_buffer = io.BytesIO()
                        tts = gTTS(text=clean_text, lang='it', slow=False)
                        tts.write_to_fp(audio_buffer)
                        audio_buffer.seek(0)
                        init_audio = audio_buffer.read()

                st.session_state.messages.append({
                    "role": "model",
                    "content": init_text,
                    "audio_bytes": init_audio
                })
                st.session_state.last_interaction_time = datetime.now()
                st.rerun()

        # Visualizzazione cronologia messaggi
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes") and is_voice_mode:
                    st.audio(msg["audio_bytes"], format="audio/mp3")

        # Sezione input
        audio_bytes = None
        if is_voice_mode:
            st.write("---")
            st.caption("🎙️ Premi per parlare o scrivi nella casella sottostante:")
            audio_bytes = audio_recorder(
                text="Parla",
                recording_color="#e74c3c",
                neutral_color="#2ecc71",
                icon_size="2x"
            )

        text_input = st.chat_input("Scrivi qui la tua risposta...")

        new_audio = (audio_bytes is not None and audio_bytes != st.session_state.last_audio_processed)
        user_display = None
        payload_parts = None

        if text_input:
            user_display = text_input
            payload_parts = [text_input]
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
                        audio_buffer = io.BytesIO()
                        tts = gTTS(text=clean_text, lang='it', slow=False)
                        tts.write_to_fp(audio_buffer)
                        audio_buffer.seek(0)
                        bot_audio = audio_buffer.read()

                st.session_state.messages.append({
                    "role": "model", 
                    "content": bot_text,
                    "audio_bytes": bot_audio
                })

                with st.chat_message("model"):
                    st.markdown(bot_text)
                    if bot_audio and is_voice_mode:
                        st.audio(bot_audio, format="audio/mp3")

            except Exception as e:
                st.error(f"Errore Tecnico API: {e}")
                st.session_state.messages.pop()

    else:
        # Ricerca del nome più simile con pulsante rapido di correzione
        tutti_nomi = students_df.index.unique().dropna().astype(str).tolist()
        simili = difflib.get_close_matches(student_name, tutti_nomi, n=3, cutoff=0.5)
        if simili:
            st.warning("Nome non trovato nel registro. Forse intendevi:")
            cols = st.columns(len(simili))
            for i, match in enumerate(simili):
                if cols[i].button(f"👉 {match}", key=f"btn_match_{i}"):
                    st.session_state.confirmed_student_name = match
                    st.rerun()
        else:
            st.warning("Nome non trovato nel registro. Controlla come lo hai scritto o contatta il professore Alessandro!")
