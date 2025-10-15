import streamlit as st
import requests
import os

QIF_API_URL = os.environ.get("QIF_API_URL", "http://qif-agent:8000")

st.set_page_config(page_title="Chat with My QIF Agent", page_icon="💸", layout="centered")
st.title("💸 Chat with My QIF Agent")
st.markdown("""
    Ask questions about your finances! 
    The agent is trained on your QIF files and can answer queries about transactions.
    The table fields are:
    - **date**: The date of the transaction
    - **payee**: The entity you paid or received money from
    - **category**: The category of the transaction
    - **memo**: Additional notes about the transaction
    - **amount**: The amount of money involved in the transaction

    
    You can ask about specific transactions, totals, or trends in your finances.
    - For example, what the sum total for all of 2018 where the category like Dues?
    - List all transaction from 2018 where category like Util or like Electric
    """)
if "history" not in st.session_state:
    st.session_state.history = []

user_input = st.chat_input("Ask about your finances, table fields are date, payee, category, memo, amount.")

if user_input:
    st.session_state.history.append({"role": "user", "content": user_input})
    # Call the QIF FastAPI agent
    try:
        resp = requests.post(f"{QIF_API_URL}/chat", json={"question": user_input}, timeout=60)
        answer = resp.json().get("answer", "No answer.")
    except Exception as e:
        answer = f"❌ Error: {e}"
    st.session_state.history.append({"role": "assistant", "content": answer})

for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        st.markdown(entry["content"])
