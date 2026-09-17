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

# Funzione per pulire il testo da leggere a voce (rimuove markdown, link ed emoji)
def clean_text_for_speech(text):
    text = re.sub(r'[*_#`~]', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    # Rimuove emoji comuni per non farle leggere dal TTS
    text = re.sub(r'[^\w\s,;.?!:\'\-—]', '', text)
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
        
        # System Prompt con Syllabus aggiornato
        system_prompt = f"""
        # ITALIANO | TUTOR PERSONALE — ISTRUZIONI PRINCIPALI
        Ti chiami Alessandro. Sei il tutor personale di italiano e partner di conversazione dello studente {student_name}.
        
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
        La grammatica è importante, ma è uno strumento al servizio della comunicazione, non il centro del percorso. Privilegia l'italiano contemporaneo e naturale. Quando utile, distingui: ❌ errato | ✅ corretto | 🇮🇹 più naturale/colloquiale.
        Principi: prima comunica, poi correggi; comunicazione prima della perfezione; naturalità prima della traduzione letterale.
        ## 2. LINGUA
        Usa l'italiano come lingua principale per conversazioni, spiegazioni, correzioni, istruzioni ed esercizi. Usa l’inglese solo quando lo studente lo richiede espressamente. Se non comprende, prova prima a riformulare in italiano più semplice e a fornire esempi. Riduci progressivamente la dipendenza dalla traduzione.
        ## 3. STILE
        Sii naturale, amichevole, paziente e stimolante. Fai domande, lascia spazio allo studente per parlare ed evita monologhi o spiegazioni inutilmente lunghe. Non elogiare artificialmente ogni risposta. Adatta progressivamente vocabolario, velocità e complessità al livello dimostrato.
        ## 4. AVVIO DELLA SESSIONE
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
        Può rispondere con numero, nome o richiesta libera. Non ripetere il menu durante una sessione già in corso.
        ## 5. CONVERSAZIONE E CORREZIONE
        La conversazione è centrale. Privilegia temi e situazioni reali e stimola risposte spontanee e progressivamente più elaborate.
        Usa correzione selettiva:
        * errore piccolo che non compromette la comunicazione → continua e correggi eventualmente dopo;
        * errore importante → correggi brevemente;
        * errore ricorrente → correggi, spiega semplicemente e riproponilo successivamente;
        * errore che cambia il significato → correggi subito.
        Formato preferito:
        Piccola correzione:
        ❌ forma usata
        ✅ forma corretta
        Breve spiegazione in italiano.
        🇮🇹 Più naturale: quando esiste una forma più comune.
        Poi riprendi subito il dialogo.
        ## 6. ROLE-PLAY, VOCABOLARIO E ADATTAMENTO
        Adatta sempre vocabolario e complessità al livello dimostrato. Porta progressivamente lo studente a comprendere, pensare e comunicare in italiano senza dipendere dalla traduzione mentale in inglese.
        """
        
        model = genai.GenerativeModel(
            model_name='gemini-3.6-flash',
            system_instruction=system_prompt
        )

        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Mostra cronologia messaggi e relativo audio se presente
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("audio_bytes"):
                    st.audio(msg["audio_bytes"], format="audio/mp3")

        # Sezione Input: microfono e tastiera
        st.write("---")
        col_mic, col_txt = st.columns([1, 5])
        
        with col_mic:
            audio_bytes = audio_recorder(
                text="Parla",
                recording_color="#e74c3c",
                neutral_color="#2ecc71",
                icon_size="2x"
            )

        text_input = st.chat_input("Scrivi qui oppure usa il microfono sopra...")

        # Rileva se lo studente ha scritto o registrato un audio
        prompt_content = None
        if audio_bytes:
            # Se ha registrato l'audio, passiamo l'audio a Gemini
            prompt_content = {
                "parts": [
                    {"mime_type": "audio/wav", "data": audio_bytes},
                    "Rispondi a quanto detto dall'utente in questo audio, mantenendo il tuo ruolo di tutor Alessandro."
                ]
            }
            user_display = "🎤 *Messaggio vocale inviato*"
        elif text_input:
            prompt_content = text_input
            user_display = text_input

        if prompt_content:
            st.session_state.messages.append({"role": "user", "content": user_display})
            with st.chat_message("user"):
                st.markdown(user_display)
                
            try:
                # Costruisce la conversazione per Gemini
                contents = []
                for m in st.session_state.messages[:-1]:
                    ruolo = "model" if m["role"] == "model" else "user"
                    contents.append({"role": ruolo, "parts": [m["content"]]})
                
                if isinstance(prompt_content, dict):
                    contents.append({"role": "user", "parts": prompt_content["parts"]})
                else:
                    contents.append({"role": "user", "parts": [prompt_content]})
                    
                response = model.generate_content(contents)
                bot_text = response.text

                # Generazione Audio della risposta (Text-to-Speech)
                clean_text = clean_text_for_speech(bot_text)
                audio_buffer = io.BytesIO()
                if clean_text:
                    tts = gTTS(text=clean_text, lang='it')
                    tts.write_to_fp(audio_buffer)
                    audio_buffer.seek(0)
                    bot_audio = audio_buffer.read()
                else:
                    bot_audio = None

                st.session_state.messages.append({
                    "role": "model", 
                    "content": bot_text,
                    "audio_bytes": bot_audio
                })

                with st.chat_message("model"):
                    st.markdown(bot_text)
                    if bot_audio:
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
