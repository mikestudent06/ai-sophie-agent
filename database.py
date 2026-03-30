# database.py

# On crée une structure de données simple (Dictionnaire) pour simuler une base de données
# Dans un vrai projet, ce serait une base de données SQL ou NoSQL.
MOCK_DATABASE = {
    "clients": {
        "user_1": {
            "nom": "Alice Martin",
            "solde": 2500.75,
            "devise": "EUR",
            "conseiller": "Jean Pierre",
            "derniere_operation": "Retrait distributeur - 50€"
        },
        "user_2": {
            "nom": "Bob Traoré",
            "solde": 150.00,
            "devise": "EUR",
            "conseiller": "Sophie (IA)",
            "derniere_operation": "Virement reçu - 1200€"
        }
    }
}

def get_customer_data(user_id: str):
    """
    Cette fonction simule une requête vers le Core Banking System (CBS).
    Elle prend un ID utilisateur et renvoie ses infos.
    """
    # On cherche l'utilisateur dans notre dictionnaire
    client = MOCK_DATABASE["clients"].get(user_id)
    
    if client:
        return client
    else:
        return "Erreur : Client introuvable dans le système."

def get_balance(user_id: str):
    """Fonction spécifique pour le solde (très utile pour Sophie)"""
    client = get_customer_data(user_id)
    if isinstance(client, dict): # On vérifie si on a bien trouvé un client
        return f"Le solde de {client['nom']} est de {client['solde']} {client['devise']}."
    return client