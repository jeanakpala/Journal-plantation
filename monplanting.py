import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from streamlit_calendar import calendar
import re

# Configuration SQLite
DB_FILE = "monplanting.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Creer les tables si elles n'existent pas
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        email TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS parcels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        parcel_name TEXT,
        UNIQUE(username, parcel_name)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        parcel TEXT,
        activity_type TEXT,
        date TEXT,
        note TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        parcel TEXT,
        last_watering TEXT,
        UNIQUE(username, parcel)
    )''')
    # Migration : ajouter la colonne email si elle n'existe pas
    try:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass  # La colonne existe deja
    conn.commit()
    conn.close()

# Initialiser la base de donnees
init_db()

# Fonction pour valider un email
def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None

# Fonction pour verifier le login
def check_login(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == password

# Fonction pour ajouter un utilisateur
def add_user(username, password, email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", (username, password, email))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Fonction pour recuperer l'email de l'utilisateur
def get_user_email(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# Fonction pour ajouter une parcelle
def add_parcel(username, parcel_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO parcels (username, parcel_name) VALUES (?, ?)", (username, parcel_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Fonction pour recuperer les parcelles
def get_parcels(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT parcel_name FROM parcels WHERE username = ?", (username,))
    parcels = [row[0] for row in c.fetchall()]
    conn.close()
    return parcels

# Fonction pour ajouter une activite
def add_activity(username, parcel, activity_type, date, note=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO activities (username, parcel, activity_type, date, note) VALUES (?, ?, ?, ?, ?)",
              (username, parcel, activity_type, date, note))
    if activity_type == "Arrosage":
        c.execute("INSERT OR REPLACE INTO reminders (username, parcel, last_watering) VALUES (?, ?, ?)",
                  (username, parcel, date))
    conn.commit()
    conn.close()

# Fonction pour recuperer les activites
def get_activities(username, parcel=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if parcel:
        c.execute("SELECT parcel, activity_type, date, note FROM activities WHERE username = ? AND parcel = ?",
                  (username, parcel))
    else:
        c.execute("SELECT parcel, activity_type, date, note FROM activities WHERE username = ?", (username,))
    df = pd.DataFrame(c.fetchall(), columns=["Parcelle", "Type_activite", "Date", "Notes"])
    conn.close()
    return df

# Fonction pour verifier les rappels
def check_reminders(username, parcel):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT last_watering FROM reminders WHERE username = ? AND parcel = ?", (username, parcel))
    result = c.fetchone()
    conn.close()
    if result:
        last_date = datetime.strptime(result[0], "%Y-%m-%d")
        if (datetime.now() - last_date).days > 3:
            return f"⚠️ Arrosage necessaire pour {parcel} ! Dernier arrosage : {result[0]}"
    return None

# Fonction pour recuperer tous les rappels
def get_all_reminders(username):
    parcels = get_parcels(username)
    reminders = []
    for parcel in parcels:
        reminder = check_reminders(username, parcel)
        if reminder:
            reminders.append(reminder)
    return reminders

# Fonction pour envoyer un email
def send_email(to_email, subject, body):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_user = st.secrets.get("SMTP_USER", "your_email@gmail.com")
    smtp_password = st.secrets.get("SMTP_PASSWORD", "your_app_password")
    
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'envoi de l'email : {e}")
        return False

# Fonction pour les stats
def get_stats(username):
    df = get_activities(username)
    if not df.empty:
        watering_stats = df[df["Type_activite"] == "Arrosage"].groupby("Parcelle").size().reset_index(name="Nombre_arrosages")
        return watering_stats
    return pd.DataFrame(columns=["Parcelle", "Nombre_arrosages"])

# Fonction pour generer les evenements du calendrier
def get_calendar_events(username):
    df = get_activities(username)
    events = []
    for _, row in df.iterrows():
        events.append({
            "title": f"{row['Parcelle']} - {row['Type_activite']}",
            "start": row["Date"],
            "end": row["Date"],
            "description": row["Notes"]
        })
    return events

# Interface principale
st.title("🌱 MonPlanting - Journal de Plantation Agricole")

# Initialisation de la session
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# Page de connexion/inscription
if not st.session_state.logged_in:
    st.subheader("Connexion / Inscription")
    action = st.radio("Choisir une action", ["Se connecter", "S'inscrire"])
    username = st.text_input("Nom d'utilisateur")
    password = st.text_input("Mot de passe", type="password")
    email = st.text_input("Adresse email (pour rappels)") if action == "S'inscrire" else None
    
    if st.button("Valider"):
        if action == "S'inscrire":
            if not email or not is_valid_email(email):
                st.error("Veuillez entrer une adresse email valide.")
            elif add_user(username, password, email):
                st.success("Inscription reussie ! Connectez-vous.")
            else:
                st.error("Utilisateur existe deja !")
        else:
            if check_login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Connexion reussie !")
                st.rerun()
            else:
                st.error("Nom d'utilisateur ou mot de passe incorrect.")
else:
    username = st.session_state.username
    st.subheader(f"Bienvenue, {username} !")
    
    # Menu principal
    menu = st.sidebar.selectbox("Menu", ["Tableau de bord", "Ajouter une parcelle", "Ajouter une activite", "Voir l'historique", "Calendrier", "Statistiques", "Deconnexion"], index=0)
    
    # Tableau de bord
    if menu == "Tableau de bord":
        st.subheader("Tableau de bord - Rappels")
        reminders = get_all_reminders(username)
        if reminders:
            st.write("### Alertes actives :")
            for reminder in reminders:
                st.error(reminder)  # Affichage en rouge pour les alertes
                user_email = get_user_email(username)
                if user_email:
                    send_email(user_email, "MonPlanting - Rappel d'arrosage", reminder)
                else:
                    st.warning("Aucun email associe pour envoyer le rappel.")
        else:
            st.success("Aucun rappel actif. Toutes les parcelles sont a jour !")
    
    # Ajouter une parcelle
    elif menu == "Ajouter une parcelle":
        st.subheader("Ajouter une parcelle")
        parcel_name = st.text_input("Nom de la parcelle")
        if st.button("Ajouter"):
            if parcel_name:
                if add_parcel(username, parcel_name):
                    st.success(f"Parcelle {parcel_name} ajoutee !")
                else:
                    st.error("Cette parcelle existe deja !")
    
    # Ajouter une activite
    elif menu == "Ajouter une activite":
        st.subheader("Ajouter une activite")
        parcels = get_parcels(username)
        if not parcels:
            st.warning("Aucune parcelle enregistree. Ajoutez une parcelle d'abord.")
        else:
            parcel = st.selectbox("Selectionner une parcelle", parcels)
            activity_type = st.selectbox("Type d'activite", ["Semis", "Arrosage", "Traitement", "Recolte"])
            date = st.date_input("Date de l'activite", datetime.now())
            note = st.text_area("Notes (optionnel)")
            if st.button("Enregistrer l'activite"):
                add_activity(username, parcel, activity_type, date.strftime("%Y-%m-%d"), note)
                st.success("Activite enregistree !")
                if activity_type == "Arrosage":
                    user_email = get_user_email(username)
                    if user_email:
                        send_email(user_email, 
                                  "MonPlanting - Nouvelle activite",
                                  f"Activite enregistree : {activity_type} pour {parcel} le {date.strftime('%Y-%m-%d')}.")
                    else:
                        st.warning("Aucun email associe a cet utilisateur.")
    
    # Historique des activites
    elif menu == "Voir l'historique":
        st.subheader("Historique des activites")
        parcels = get_parcels(username)
        if not parcels:
            st.warning("Aucune parcelle enregistree.")
        else:
            selected_parcel = st.selectbox("Filtrer par parcelle", ["Toutes"] + parcels)
            df = get_activities(username, selected_parcel if selected_parcel != "Toutes" else None)
            if not df.empty:
                st.dataframe(df)
            else:
                st.info("Aucune activite enregistree.")
            
            # Verification des rappels
            for parcel in parcels:
                reminder = check_reminders(username, parcel)
                if reminder:
                    st.error(reminder)
                    user_email = get_user_email(username)
                    if user_email:
                        send_email(user_email,
                                  "MonPlanting - Rappel d'arrosage",
                                  reminder)
                    else:
                        st.warning("Aucun email associe pour envoyer le rappel.")
    
    # Calendrier
    elif menu == "Calendrier":
        st.subheader("Calendrier des activites")
        events = get_calendar_events(username)
        options = {
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,timeGridDay"
            },
            "initialView": "dayGridMonth"
        }
        calendar(options=options, events=events)
    
    # Statistiques
    elif menu == "Statistiques":
        st.subheader("Statistiques")
        stats = get_stats(username)
        if not stats.empty:
            st.write("Nombre d'arrosages par parcelle :")
            st.dataframe(stats)
            st.bar_chart(stats.set_index("Parcelle")["Nombre_arrosages"])
        else:
            st.info("Aucune donnee d'arrosage disponible.")
    
    # Deconnexion
    elif menu == "Deconnexion":
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()