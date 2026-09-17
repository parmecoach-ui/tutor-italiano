import streamlit as st
import google.generativeai as genai
import pandas as pd
import requests
import io
import difflib
import re
from datetime import datetime
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder

st.set_page_config(page_title="Il tuo professore Alessandro online", page_icon="😊")

def clean_text_for_speech(text):
    text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', text)
    text = re.sub(r'[*_#`~]', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'[^\w\s,;.?!:\'\-—àèéìòùÀÈÉÌÒÙ]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# Funzione per inviare i progressi a Google Sheets
def salva_sessione_su_sheet(student_name, message_count, activity, messages_list, model):
    apps_script_url = st.secrets.get("APPS_SCRIPT_URL", None)
    if not apps_script_url or message_count <= 0:
        return None

    # Chiede a Gemini una sintesi strutturata dei progressi didattici
    chat_transcript = "\n".join([f"{m['role']}: {m['content']}" for m in messages_list if "content" in m])
    prompt_sintesi = f"""
    Analizza brevemente questa conversazione didattica di italiano con lo studente {student_name}:
    {chat_transcript}
    
    Genera un riassunto di massimo 3 righe che sintetizzi:
    - Argomenti trattati
    - Errori ricorrenti emersi
    - Punti di forza dimostrati
    Usa uno stile conciso, chiaro e professionale per il registro del professore.
    """
    try:
        res = model.generate_content(prompt_sintesi)
        summary_text = res.text.strip()
    except Exception:
        summary_text = "Sessione svolta regolarmente."

    payload = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "student": student_name,
        "message_count": message_count,
        "activity": activity,
        "summary": summary_text
    }
    
    try:
        requests.post(apps_script_url, json=payload, timeout=8)
        return summary_text
    except Exception:
        return None

# 1. Configurazione API
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
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
        
        genere = dati_studente.get('Genere', 'M')
        if genere == 'F':
            st.success(f"Benvenuta, {student_name}! Pronta a fare pratica?")
        else:
            st.success(f"Benvenuto, {student_name}! Pronto a fare pratica?")

        # Scelta modalità
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
        - Non inserire MAI timestamp o riferimenti orari (es. NON scrivere MAI "00:03", "00:06").
        - Scrivi risposte fluide, naturali ed empatiche.
        
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
        Usa l'italiano come lingua principale. Sii naturale, amichevole, paziente e stimolante. Evita risposte eccessivamente lunghe.
        """
        
        model = genai.GenerativeModel(
            model_name='gemini-3.5-flash-lite',
            system_instruction=system_prompt
        )

        # Inizializzazione variabili sessione
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "last_interaction_time" not in st.session_state:
            st.session_state.last_interaction_time = datetime.now()
        if "session_message_count" not in st.session_state:
            st.session_state.session_message_count = 0
        if "last_audio_processed" not in st.session_state:
            st.session_state.last_audio_processed = None

        # Controllo inattività > 1 ora (3600 secondi)
        adesso = datetime.now()
        tempo_trascorso = (adesso - st.session_state.last_interaction_time).total_seconds()
        
        if tempo_trascorso > 3600 and st.session_state.session_message_count > 0:
            # Salva la vecchia sessione scaduta
            with st.spinner("Archivio la sessione precedente..."):
                salva_sessione_su_sheet(
                    student_name, 
                    st.session_state.session_message_count, 
                    st.session_state.modalita_attivita, 
                    st.session_state.messages, 
                    model
                )
            # Reset per la nuova sessione
            st.session_state.messages = []
            st.session_state.session_message_count = 0
            st.info("È trascorsa più di 1 ora dall'ultimo accesso: i progressi precedenti sono stati salvati su Fogli Google. Iniziamo una nuova sessione!")

        # Sidebar con statistiche e pulsante fine sessione
        with st.sidebar:
            st.header("📊 La tua sessione")
            st.metric("Messaggi inviati", st.session_state.session_message_count)
            if st.button("🏁 Termina sessione e salva"):
                if st.session_state.session_message_count > 0:
                    with st.spinner("Salvataggio su Google Sheets in corso..."):
                        sintesi = salva_sessione_su_sheet(
                            student_name, 
                            st.session_state.session_message_count, 
                            st.session_state.modalita_attivita, 
                            st.session_state.messages, 
                            model
                        )
                    st.success("Sessione salvata con successo nel registro del professor Alessandro!")
                    if sintesi:
                        st.info(f"**I tuoi progressi oggi:**\n\n{sintesi}")
                    st.session_state.messages = []
                    st.session_state.session_message_count = 0
                else:
                    st.warning("Non ci sono ancora messaggi scambiati in questa sessione.")

        # Visualizza messaggi della sessione corrente
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes") and is_voice_mode:
                    st.audio(msg["audio_bytes"], format="audio/mp3")

        audio_bytes = None
        if is_voice_mode:
            st.write("---")
            st.caption("🎙️ Parla con il microfono oppure scrivi sotto:")
            audio_bytes = audio_recorder(
                text="Premi per parlare",
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
            # Aggiornamento timestamp e contatore
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
        tutti_nomi = students_df.index.unique().dropna().astype(str).tolist()
        simili = difflib.get_close_matches(student_name, tutti_nomi, n=2, cutoff=0.6)
        if simili:
            st.warning(f"Nome non trovato. Forse intendevi: **{', '.join(simili)}**?")
        else:
            st.warning("Nome non trovato nel registro. Controlla come lo hai scritto o contatta il professore Alessandro!")
