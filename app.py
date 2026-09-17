import streamlit as st
import google.generativeai as genai
import pandas as pd
import requests
import io
import difflib
import re
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder

st.set_page_config(page_title="Il tuo professore Alessandro online", page_icon="😊")

# Funzione per pulire il testo da leggere a voce in modo fluido
def clean_text_for_speech(text):
    # Rimuove eventuali timestamp residui
    text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', text)
    # Rimuove markdown, parentesi e link
    text = re.sub(r'[*_#`~]', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    # Rimuove emoji e simboli insoliti
    text = re.sub(r'[^\w\s,;.?!:\'\-—àèéìòùÀÈÉÌÒÙ]', '', text)
    # Normalizza gli spazi
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# 1. Configurazione API
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error("Errore di sistema con la chiave API. Controlla i Secrets su Streamlit.")
    st.stop()

# 2. Caricamento Dati
CSV_URL = st.secrets.get(
    "SHEET_URL", 
    "https://docs.google.com/spreadsheets/d/1bEHnFNXYo5CGeDhHlKq23m8C8mDEW8s_TTZz7ZccjTk/export?format=csv"
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

st.title("😊 Il tuo professore Alessandro online")

# 3. Interfaccia Identificazione
student_name_input = st.text_input("Inserisci il tuo nome per iniziare:")
student_name = student_name_input.strip()

if student_name:
    if student_name in students_df.index:
        dati_studente = students_df.loc[student_name]
        
        # Gestione duplicati
        if isinstance(dati_studente, pd.DataFrame):
            st.warning(f"Attenzione: ho trovato più di un profilo con il nome {student_name}.")
            nazioni = dati_studente['Country of Residence'].tolist()
            scelta_nazione = st.selectbox(
                "Per identificarti, seleziona il tuo Paese di Residenza:",
                ["Seleziona..."] + nazioni
            )
            if scelta_nazione == "Seleziona...":
                st.stop()
            else:
                dati_studente = dati_studente[dati_studente['Country of Residence'] == scelta_nazione].iloc[0]
        
        # Gestione del Genere
        genere = dati_studente.get('Genere', 'M')
        if genere == 'F':
            st.success(f"Benvenuta, {student_name}! Pronta a fare pratica?")
        else:
            st.success(f"Benvenuto, {student_name}! Pronto a fare pratica?")

        # --- SELETTORE ATTIVITÀ / MODALITÀ ---
        # Permette di entrare o uscire dalla modalità vocale in modo trasparente
        if "modalita_attivita" not in st.session_state:
            st.session_state.modalita_attivita = "💬 1. Conversazione (con Voce)"

        attivita = st.radio(
            "Scegli cosa vuoi fare:",
            [
                "💬 1. Conversazione (con Voce)",
                "📚 2. Lezione / Grammatica (Solo Testo)",
                "🔄 3. Revisione (Solo Testo)",
                "🗣️ 4. Role-play (Solo Testo)",
                "✍️ Altro / Esercizi (Solo Testo)"
            ],
            horizontal=True
        )
        st.session_state.modalita_attivita = attivita
        is_voice_mode = "1. Conversazione" in attivita

        system_prompt = f"""
        # ITALIANO | TUTOR PERSONALE — ISTRUZIONI PRINCIPALI
        Ti chiami Alessandro. Sei il tutor personale di italiano e partner di conversazione dello studente {student_name}.
        
        [REGOLE FORMATTAZIONE RISPOSTA]
        - Non inserire MAI timestamp o marcatori orari (es. NON scrivere MAI "00:03", "00:06").
        - Scrivi risposte naturali, fluide ed empatiche, adatte alla conversazione parlata.
        
        [DATI DELLO STUDENTE DA NON INVENTARE]
        - Livello stimato: {dati_studente.get('Livello', 'Non specificato')}
        - Paese di origine / Residenza: {dati_studente.get('Country of Birth', '')} / {dati_studente.get('Country of Residence', '')}
        - Motivazione: {dati_studente.get('Reason to learn', 'Migliorare l italiano')}
        - Punti di miglioramento ed errori: {dati_studente.get('Punti di miglioramento', 'Nessuno specifico')}
        - Documento di teoria attuale: {dati_studente.get('Documento Teoria', 'Nessuno')}
        
        [IMPORTANTE: PROGRESSIONE DIDATTICA E SYLLABUS]
        I documenti di teoria del tuo corso sono numerati in ordine progressivo da 01 a 12. Il "Documento di teoria attuale" indicato qui sopra rappresenta il punto esatto a cui siete arrivati.
        Questo significa che lo studente ha già studiato, fatto esercizi e conosce gli argomenti di TUTTI i documenti precedenti. 
        Usa questa preziosa informazione per calibrare i vocaboli e la grammatica. Non usare MAI forme grammaticali di documenti successivi a quello attuale.
        
        INDICE DEL CORSO COMPLETO (Referenza per il Bot):
        Doc 01: Presentarsi, saluti formali/informali, nazionalità, aspetto fisico, professioni. Verbo Essere e Avere al Presente, Aggettivi possessivi.
        Doc 02: Routine quotidiana, casa, sport, giorni, stagioni. Numeri 0-20. Verbi regolari (-are, -ere, -ire), Verbi modali (volere, potere, dovere), verbi Andare/Fare al Presente. Verbi riflessivi, Frase negativa.
        Doc 03: Ordinare al bar/ristorante e/o indicazioni in città, acquisti, iscrizioni. Numeri 21-100. Articoli determinativi. Passato Prossimo (con Avere ed Essere), Participio Passato regolare e irregolare. Verbi a struttura invertita (es. Piacere, Mancare).
        Doc 04: Famiglia, amici, relazioni sociali e/o muoversi in città. Pronomi interrogativi, uso di "Che". Articoli indeterminativi. Condizionale Presente e Condizionale Passato.
        Doc 05: Chiacchierare (meteo, tempo), mesi dell'anno. Avverbi e Preposizioni di luogo. Futuro semplice e altre forme per il futuro (es. avere intenzione di, stare per).
        Doc 06: Programmi per uscire a divertirsi (locali, ballare). Articolo determinativo (ripasso), Preposizioni semplici e articolate. Imperativo (regolare e modale). Pronomi personali diretti.
        Doc 07: Avere una discussione (termini forti/calmi). Aggettivi qualificativi e dimostrativi. Articoli partitivi. Verbi in -isc.
        Doc 08: Chiedere aiuto (emergenza, malore, incidenti). Avverbi/Preposizioni di tempo. Particelle "ci" e "ne". Indicativo imperfetto.
        Doc 09: Passioni e hobby. Pronomi personali indiretti. Pronomi combinati. Presente progressivo. Gerundio. Struttura della frase italiana (posizione avverbi, pronomi, negazione).
        Doc 10: Raccontare esperienze personali (emozioni, viaggi, traumi). Congiuntivo presente. Congiuntivo passato. Comparativi e superlativi. Differenza tra migliore/meglio, peggiore/peggio.
        Doc 11: Dare la propria opinione (concordare/discordare). Congiuntivo imperfetto. Congiuntivo trapassato. Periodo ipotetico (1, 2, 3 tipo e misto). Verbi pronominali. Forma impersonale con "si".
        Doc 12: Avere un confronto culturale (lingua, abitudini). Indicativo trapassato prossimo. Forma Passiva. Aggettivi/Pronomi indefiniti. Avverbi rafforzativi. Connettivi logici (causa, conseguenza, contrasto).
        
        ## 1. IDENTITÀ E OBIETTIVO
        L'obiettivo principale è sviluppare la capacità dello studente di comprendere e comunicare in italiano reale, naturale e quotidiano, privilegiando conversazione, comprensione orale, spontaneità e vocabolario attivo.
        ## 2. LINGUA E STILE
        Usa l'italiano come lingua principale. Sii naturale, amichevole, paziente e stimolante. Mantieni le risposte concise per stimolare il dialogo.
        """
        
        model = genai.GenerativeModel(
            model_name='gemini-3.6-flash',
            system_instruction=system_prompt
        )

        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "last_audio_processed" not in st.session_state:
            st.session_state.last_audio_processed = None

        # Mostra la cronologia messaggi
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes") and is_voice_mode:
                    st.audio(msg["audio_bytes"], format="audio/mp3")

        # Gestione input: microfono solo se in modalità voce
        audio_bytes = None
        if is_voice_mode:
            st.write("---")
            st.caption("🎙️ Puoi parlare al microfono oppure scrivere qui sotto:")
            audio_bytes = audio_recorder(
                text="Premi per parlare",
                recording_color="#e74c3c",
                neutral_color="#2ecc71",
                icon_size="2x"
            )

        text_input = st.chat_input("Scrivi qui la tua risposta...")

        user_message_text = None

        # RISOLUZIONE BUG MICROFONO:
        # Controlliamo se c'è un nuovo audio diverso da quello già processato
        new_audio_detected = (
            audio_bytes is not None 
            and audio_bytes != st.session_state.last_audio_processed
        )

        if text_input:
            # Se l'utente scrive, ha sempre la precedenza sul vecchio audio rimasto in memoria
            user_message_text = text_input
        elif new_audio_detected:
            # Registriamo che questo audio è stato consumato
            st.session_state.last_audio_processed = audio_bytes
            with st.spinner("Ascolto la tua voce..."):
                try:
                    # Trascriviamo prima l'audio con Gemini per avere il vero testo in cronologia
                    transcribe_res = model.generate_content([
                        {"mime_type": "audio/wav", "data": audio_bytes},
                        "Trascrivi fedelmente solo le parole dette in italiano dall'utente in questo audio. Non aggiungere commenti."
                    ])
                    user_message_text = transcribe_res.text.strip()
                    if not user_message_text:
                        user_message_text = "(Audio registrato)"
                except Exception:
                    user_message_text = "(Audio registrato)"

        if user_message_text:
            st.session_state.messages.append({"role": "user", "content": user_message_text})
            with st.chat_message("user"):
                st.markdown(user_message_text)
                
            try:
                # Costruisce la conversazione completa
                contents = []
                for m in st.session_state.messages:
                    ruolo = "model" if m["role"] == "model" else "user"
                    contents.append({"role": ruolo, "parts": [m["content"]]})
                
                response = model.generate_content(contents)
                raw_text = response.text
                bot_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', raw_text).strip()

                bot_audio = None
                # Genera l'audio SOLO ed ESCLUSIVAMENTE se siamo in modalità conversazione vocale
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
        tutti_nomi = students_df.index.unique().dropna().astype(str).tolist()
        simili = difflib.get_close_matches(student_name, tutti_nomi, n=2, cutoff=0.6)
        if simili:
            st.warning(f"Nome non trovato. Forse intendevi: **{', '.join(simili)}**?")
        else:
            st.warning("Nome non trovato nel registro. Controlla come lo hai scritto o contatta il professore Alessandro!")
