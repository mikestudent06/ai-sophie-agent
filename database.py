# database.py

# On crée une structure de données simple (Dictionnaire) pour simuler une base de données
# Dans un vrai projet, ce serait une base de données SQL ou NoSQL.
MOCK_DATABASE = {
    "clients": {
        # Profil salarié avec plusieurs comptes
        "user_1": {
            "id": "user_1",
            "nom": "Alice Martin",
            "email": "alice.martin@example.com",
            "telephone": "+33 6 12 34 56 78",
            "conseiller": "Jean Pierre",
            "statut": "Client Premium",
            "comptes": [
                {
                    "type": "Compte courant",
                    "iban": "FR76 3000 4000 1234 5678 9012 345",
                    "solde": 2543.80,
                    "devise": "EUR",
                    "decouvert_autorise": 500.00,
                    "derniere_operation": "Carte - Supermarché Monoprix Paris - 86,20€"
                },
                {
                    "type": "Livret A",
                    "iban": "FR76 3000 4000 9876 5432 1098 765",
                    "solde": 8200.00,
                    "devise": "EUR",
                    "taux": 3.00,
                    "derniere_operation": "Virement automatique épargne - 200,00€"
                }
            ]
        },
        # Profil étudiant avec petit découvert
        "user_2": {
            "id": "user_2",
            "nom": "Bamba Traoré",
            "email": "bamba.traore@example.com",
            "telephone": "+33 7 98 76 54 32",
            "conseiller": "Sophie (IA)",
            "statut": "Étudiant",
            "comptes": [
                {
                    "type": "Compte courant",
                    "iban": "FR76 1020 7000 1111 2222 3333 444",
                    "solde": -45.30,
                    "devise": "EUR",
                    "decouvert_autorise": 200.00,
                    "derniere_operation": "Prélèvement - Abonnement streaming - 19,99€"
                }
            ]
        },
        # Profil entrepreneur avec compte pro
        "user_3": {
            "id": "user_3",
            "nom": "Carla Nguyen",
            "email": "carla.nguyen@example.com",
            "telephone": "+33 6 23 45 67 89",
            "conseiller": "Marc Dupuis",
            "statut": "Professionnel",
            "comptes": [
                {
                    "type": "Compte courant pro",
                    "iban": "FR76 2004 1010 0505 0001 3M02 606",
                    "solde": 42150.25,
                    "devise": "EUR",
                    "derniere_operation": "Virement client - Facture 2026-032 - 8 300,00€"
                },
                {
                    "type": "Compte TVA",
                    "iban": "FR76 2004 1010 0505 0001 3M02 607",
                    "solde": 6350.00,
                    "devise": "EUR",
                    "derniere_operation": "Virement interne vers compte courant pro - 2 000,00€"
                }
            ]
        },
        # Profil retraité avec revenus réguliers
        "user_4": {
            "id": "user_4",
            "nom": "Daniel Moreau",
            "email": "daniel.moreau@example.com",
            "telephone": "+33 6 45 67 89 01",
            "conseiller": "Sophie (IA)",
            "statut": "Retraité",
            "comptes": [
                {
                    "type": "Compte courant",
                    "iban": "FR76 3000 4000 5555 6666 7777 888",
                    "solde": 3120.40,
                    "devise": "EUR",
                    "derniere_operation": "Virement caisse de retraite - 1 620,00€"
                },
                {
                    "type": "Assurance vie",
                    "iban": "FR76 3000 4000 9999 8888 7777 666",
                    "solde": 45230.90,
                    "devise": "EUR",
                    "derniere_operation": "Versement programmé - 300,00€"
                }
            ]
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
    """Fonction spécifique pour le solde principal (très utile pour Sophie)"""
    client = get_customer_data(user_id)
    if isinstance(client, dict):  # On vérifie si on a bien trouvé un client
        comptes = client.get("comptes", [])
        if not comptes:
            return f"Le client {client.get('nom', user_id)} n'a aucun compte enregistré."

        compte_principal = comptes[0]
        return (
            f"Le solde du compte principal de {client['nom']} "
            f"({compte_principal.get('type', 'Compte')}) est de "
            f"{compte_principal['solde']} {compte_principal['devise']}."
        )
    return client