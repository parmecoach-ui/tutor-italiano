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

# Funzione per rimuovere timestamp (es. 00:03, 01:20)
def remove_timestamps(text):
    return re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', '', text)

# Funzione per pulire il testo prima di passarlo alla voce
def clean_text_for_speech(text):
    text = remove_timestamps(text)
    text = re.sub(r'[*_#`~]', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'[^\w\s,;.?!:\'\-—]', '', text)
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
        
        # Genere
        genere = dati_studente.get('Genere', 'M')
        if genere == 'F':
            st.success(f"Benvenuta, {student_name}! Pronta a fare pratica?")
        else:
            st.success(f"Benvenuto, {student_name}! Pronto a fare pratica?")
        
        # Stato per abilitare la modalità voce/conversazione
        if "modalita_voce" not in st.session_state:
            st.session_state.modalita_voce = False

        system_prompt = f"""
        # ITALIANO | TUTOR PERSONALE — ISTRUZIONI PRINCIPALI
        Ti chiami Alessandro. Sei il tutor personale di italiano e partner di conversazione dello studente {student_name}.
        
        [REGOLE FORMATTAZIONE RISPOSTA]
        - Non inserire MAI timestamp o riferimenti orari ai secondi dell'audio (es. NON scrivere MAI "00:03", "00:06", ecc.).
        - Scrivi risposte fluide, naturali ed empatiche, adatte a essere lette o ascoltate.
        
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
        Usa l'italiano come lingua principale. Sii naturale, amichevole, paziente e stimolante. Evita monologhi lunghi.
        ## 3. AVVIO DELLA SESSIONE
        Quando lo studente dice “Buongiorno, cominciamo!”, “Cominciamo!”, “Iniziamo!” o equivalente, presenta:
        Cosa ti piacerebbe fare oggi?
        1. 💬 Conversazione
        2. 📚 Lezione
        3. 🔄 Revisione
        4. 🗣️ Role-play
        5. 🧠 Vocabolario
        6. ✍️ Correzione
        7. 🎧 Ascolto
        8. 🎯 Sfida
        9. 🎲 Scegli tu!
        """
        
        model = genai.GenerativeModel(
            model_name='gemini-3.6-flash',
            system_instruction=system_prompt
        )

        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Mostra cronologia messaggi
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes"):
                    st.audio(msg["audio_bytes"], format="audio/mp3")

        # Se la modalità voce è attiva, mostriamo il microfono e un badge informativo
        audio_bytes = None
        if st.session_state.modalita_voce:
            st.info("🎙️ **Modalità Conversazione Vocale Attiva**: puoi parlare con il microfono o scrivere. Scrivi *'stop voce'* per disattivare l'audio.")
            col_mic, col_vuota = st.columns([1, 4])
            with col_mic:
                audio_bytes = audio_recorder(
                    text="Premi per parlare",
                    recording_color="#e74c3c",
                    neutral_color="#2ecc71",
                    icon_size="2x"
                )

        text_input = st.chat_input("Scrivi qui...")

        # Rileva input (voce o testo)
        prompt_content = None
        user_display = None

        if audio_bytes:
            prompt_content = {
                "parts": [
                    {"mime_type": "audio/wav", "data": audio_bytes},
                    "Rispondi a questo audio dello studente in modo colloquiale come tutor Alessandro. NON usare timestamp tipo 00:03."
                ]
            }
            user_display = "🎤 *Messaggio vocale inviato*"
        elif text_input:
            prompt_content = text_input
            user_display = text_input
            
            # Controllo per attivare o disattivare la modalità voce
            testo_norm = text_input.lower().strip()
            if testo_norm in ["1", "conversazione", "1. conversazione", "parliamo", "voglio fare conversazione", "conversare"]:
                st.session_state.modalita_voce = True
            elif testo_norm in ["stop voce", "basta voce", "disattiva voce", "solo testo"]:
                st.session_state.modalita_voce = False
                st.info("Modalità audio disattivata.")

        if prompt_content:
            st.session_state.messages.append({"role": "user", "content": user_display})
            with st.chat_message("user"):
                st.markdown(user_display)
                
            try:
                contents = []
                for m in st.session_state.messages[:-1]:
                    ruolo = "model" if m["role"] == "model" else "user"
                    contents.append({"role": ruolo, "parts": [m["content"]]})
                
                if isinstance(prompt_content, dict):
                    contents.append({"role": "user", "parts": prompt_content["parts"]})
                else:
                    contents.append({"role": "user", "parts": [prompt_content]})
                    
                response = model.generate_content(contents)
                bot_text = remove_timestamps(response.text).strip()

                # Genera l'audio SOLO se la modalità voce è attiva
                bot_audio = None
                if st.session_state.modalita_voce:
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
                    if bot_audio:
                        st.audio(bot_audio, format="audio/mp3")
                
                # Se è appena stata attivata la modalità voce, ricarichiamo per mostrare subito il microfono
                if st.session_state.modalita_voce and not audio_bytes and testo_norm in ["1", "conversazione", "1. conversazione"]:
                    st.rerun()

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
