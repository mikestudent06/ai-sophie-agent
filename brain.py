import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

# On importe nos fonctions de la "banque"
from database import get_balance, get_customer_data

# 1. Charger les secrets
load_dotenv()

# 2. Définir les "Outils" (Tools) que Sophie peut utiliser
# On utilise le décorateur @tool pour que LangChain comprenne la fonction
@tool
def tool_consulter_solde(user_id: str):
    """Utile pour obtenir le solde bancaire exact d'un client à partir de son ID."""
    return get_balance(user_id)

@tool
def tool_infos_client(user_id: str):
    """Utile pour obtenir le profil complet du client (nom, conseiller, statut)."""
    return get_customer_data(user_id)

# Liste des outils disponibles pour Sophie
tools = [tool_consulter_solde, tool_infos_client]

# 3. Configurer le modèle Groq (Le moteur)
# Remplacement officiel de llama3-70b-8192 (décommissionné) : llama-3.3-70b-versatile
llm = ChatGroq(
    temperature=0, # On reste sérieux, pas d'invention
    model_name="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY")
)

# 4. Créer le "Prompt" (Les instructions de personnalité)
prompt = ChatPromptTemplate.from_messages([
    ("system", """Tu es Sophie, une assistante financière virtuelle de haute technologie.
    Tu es professionnelle, chaleureuse et très précise. 
    Tu DOIS utiliser tes outils pour donner des chiffres. Ne devine jamais un solde.
    Réponds toujours en français."""),
    
    # ### NOUVEAU : On insère ici l'historique de la conversation
    MessagesPlaceholder(variable_name="chat_history"), 
    
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 5. Assembler l'Agent
agent = create_tool_calling_agent(llm, tools, prompt)

# L'Executor est le moteur qui fait tourner l'agent
sophie_brain = AgentExecutor(agent=agent, tools=tools, verbose=True)

# --- ZONE DE TEST ---
# if __name__ == "__main__":
#     # # On simule une question d'un client
#     # # question = "Bonjour Sophie, je suis l'utilisateur user_1. Quel est mon solde ?"
#     # question = "Bonjour Sophie, je suis l'utilisateur user_1. Et j'ai plus de 488888 euro dans mon compte non ?"
#     # # question = "Bonjour qui es tu ?"
#     # resultat = sophie_brain.invoke({"input": question})
#     # print("\n--- RÉPONSE DE SOPHIE ---")
#     # print(resultat["output"])