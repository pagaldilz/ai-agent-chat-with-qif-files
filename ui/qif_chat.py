import streamlit as st
import requests
import os
import pandas as pd
from datetime import datetime

QIF_API_URL = os.environ.get("QIF_API_URL", "http://qif-agent:8000")

st.set_page_config(page_title="QIF Agent", page_icon="", layout="centered")

# Sidebar navigation
page = st.sidebar.selectbox("Choose a page", ["Chat", "Recurring Analysis", "Merchant Analysis", "Anomaly Detection"])

if page == "Chat":
    st.title("Chat with My QIF Agent")
    st.markdown("""
        Ask questions about your finances! 
        The agent is trained on your QIF files and can answer queries about transactions.
        The table fields are:
        - **date**: The date of the transaction
        - **payee**: The entity you paid or received money from
        - **category**: The category of the transaction
        - **memo**: Additional notes about the transaction
        - **amount**: The amount of money involved in the transaction
        - **source_file**: The QIF file this transaction came from
        - **account_name**: The account name from the QIF file
        - **account_type**: The type of account (Bank, Credit Card, Investment, etc.)

        
        You can ask about specific transactions, totals, or trends in your finances.
        - For example, what the sum total for all of 2018 where the category like Dues?
        - List all transaction from 2018 where category like Util or like Electric
        """)
    
    if "history" not in st.session_state:
        st.session_state.history = []

    user_input = st.chat_input("Ask about your finances, table fields are date, payee, category, memo, amount, source_file, account_name, account_type.")

    if user_input:
        st.session_state.history.append({"role": "user", "content": user_input})
        # Call the QIF FastAPI agent
        try:
            resp = requests.post(f"{QIF_API_URL}/chat", json={"question": user_input}, timeout=60)
            if resp.status_code == 400:
                # Guardrail rejection or bad request
                err = resp.json().get("detail", "Your query was blocked by safety checks. Try rephrasing.")
                answer = f"Query blocked: {err}"
                st.session_state.history.append({"role": "assistant", "content": answer})
            else:
                data = resp.json()
                answer = data.get("answer", "No answer.")
                sql = data.get("sql", "")
                explanation = data.get("explanation", "")
                
                # Store the full response data for display
                st.session_state.history.append({
                    "role": "assistant", 
                    "content": answer,
                    "sql": sql,
                    "explanation": explanation
                })
        except Exception as e:
            answer = f"Error: {e}"
            st.session_state.history.append({"role": "assistant", "content": answer})

    for entry in st.session_state.history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            
            # Show SQL and explanation for assistant responses
            if entry["role"] == "assistant" and "sql" in entry and entry["sql"]:
                with st.expander("View SQL Query", expanded=False):
                    st.code(entry["sql"], language="sql")
                    if entry.get("explanation"):
                        st.markdown(f"**Explanation:** {entry['explanation']}")

elif page == "Recurring Analysis":
    st.title("Recurring Transaction Analysis")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Analyze Recurring Patterns", type="primary"):
            with st.spinner("Analyzing recurring patterns..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/analyze/recurring", timeout=120)
                    if resp.status_code == 200:
                        st.success("Analysis complete!")
                        st.rerun()
                    else:
                        st.error(f"Analysis failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get and display recurring patterns
    try:
        resp = requests.get(f"{QIF_API_URL}/recurring", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            patterns = data.get('patterns', [])
            projections = data.get('projections', {})
            
            if patterns:
                # Display projections
                st.subheader("Monthly Spending Projections")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Monthly", f"${projections.get('monthly_projection', 0):,.2f}")
                with col2:
                    st.metric("Weekly", f"${projections.get('weekly_projection', 0):,.2f}")
                with col3:
                    st.metric("Quarterly", f"${projections.get('quarterly_projection', 0):,.2f}")
                with col4:
                    st.metric("Yearly", f"${projections.get('yearly_projection', 0):,.2f}")
                
                # Display patterns table
                st.subheader("Detected Recurring Patterns")
                df = pd.DataFrame(patterns)
                
                # Format the dataframe for display
                display_df = df[['merchant_pattern', 'amount_avg', 'frequency_category', 
                                'confidence_score', 'transaction_count', 'next_expected']].copy()
                display_df.columns = ['Merchant', 'Avg Amount', 'Frequency', 'Confidence', 'Count', 'Next Expected']
                display_df['Avg Amount'] = display_df['Avg Amount'].apply(lambda x: f"${x:,.2f}")
                display_df['Confidence'] = display_df['Confidence'].apply(lambda x: f"{x:.1%}")
                
                st.dataframe(display_df, use_container_width=True)
                
                # Show detailed view for selected pattern
                if len(patterns) > 0:
                    st.subheader("Pattern Details")
                    selected_idx = st.selectbox("Select a pattern to view details:", 
                                              range(len(patterns)),
                                              format_func=lambda x: f"{patterns[x]['merchant_pattern']} - {patterns[x]['frequency_category']}")
                    
                    if selected_idx is not None:
                        pattern = patterns[selected_idx]
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Merchant:** {pattern['merchant_pattern']}")
                            st.write(f"**Average Amount:** ${pattern['amount_avg']:,.2f}")
                            st.write(f"**Frequency:** {pattern['frequency_category']} (every {pattern['frequency_days']:.1f} days)")
                            st.write(f"**Confidence:** {pattern['confidence_score']:.1%}")
                            
                        with col2:
                            st.write(f"**Last Seen:** {pattern['last_seen']}")
                            st.write(f"**Next Expected:** {pattern['next_expected']}")
                            st.write(f"**Transaction Count:** {pattern['transaction_count']}")
                            st.write(f"**Category:** {pattern['category']}")
            else:
                st.info("No recurring patterns detected. Click 'Analyze Recurring Patterns' to run the analysis.")
                
        else:
            st.error(f"Failed to load recurring patterns: {resp.text}")
    except Exception as e:
        st.error(f"Error loading recurring patterns: {e}")

elif page == "Merchant Analysis":
    st.title("Merchant Analysis")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Normalize Merchants", type="primary"):
            with st.spinner("Normalizing merchant names..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/admin/normalize-merchants", timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.success(f"Normalized {len(data.get('mappings', {}))} merchants!")
                        st.rerun()
                    else:
                        st.error(f"Normalization failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get and display merchant data
    try:
        resp = requests.get(f"{QIF_API_URL}/merchants", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            statistics = data.get('statistics', {})
            top_merchants = data.get('top_merchants', [])
            
            if statistics:
                # Display statistics
                st.subheader("Merchant Statistics")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Merchants", statistics.get('total_merchants', 0))
                with col2:
                    st.metric("Canonical Names", statistics.get('canonical_merchants', 0))
                with col3:
                    st.metric("Avg Transactions", f"{statistics.get('avg_transactions_per_merchant', 0):.1f}")
                with col4:
                    st.metric("Max Transactions", statistics.get('max_transactions', 0))
                
                # Display top merchants
                if top_merchants:
                    st.subheader("Top Merchants by Transaction Count")
                    df = pd.DataFrame(top_merchants)
                    display_df = df[['canonical_name', 'transaction_count', 'original_name']].copy()
                    display_df.columns = ['Canonical Name', 'Transaction Count', 'Original Name']
                    
                    st.dataframe(display_df, use_container_width=True)
                else:
                    st.info("No merchant data available. Click 'Normalize Merchants' to run the analysis.")
            else:
                st.info("No merchant statistics available. Click 'Normalize Merchants' to run the analysis.")
                
        else:
            st.error(f"Failed to load merchant data: {resp.text}")
    except Exception as e:
        st.error(f"Error loading merchant data: {e}")

elif page == "Anomaly Detection":
    st.title("Anomaly Detection")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Analyze Anomalies", type="primary"):
            with st.spinner("Analyzing anomalies..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/analyze/anomalies", timeout=120)
                    if resp.status_code == 200:
                        st.success("Anomaly analysis complete!")
                        st.rerun()
                    else:
                        st.error(f"Analysis failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get and display anomalies
    try:
        resp = requests.get(f"{QIF_API_URL}/anomalies", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            anomalies = data.get('anomalies', [])
            summary = data.get('summary', {})
            
            if anomalies:
                # Display summary
                if summary:
                    st.subheader("Anomaly Summary")
                    for anomaly_type, stats in summary.items():
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric(f"{anomaly_type.replace('_', ' ').title()} Count", stats['count'])
                        with col2:
                            st.metric("Avg Score", f"{stats['avg_score']:.2f}")
                        with col3:
                            st.metric("Max Score", f"{stats['max_score']:.2f}")
                
                # Display anomalies table
                st.subheader("Detected Anomalies")
                df = pd.DataFrame(anomalies)
                
                # Format the dataframe for display
                display_df = df[['date', 'payee', 'amount', 'anomaly_type', 'score', 'explanation']].copy()
                display_df.columns = ['Date', 'Merchant', 'Amount', 'Type', 'Score', 'Explanation']
                display_df['Amount'] = display_df['Amount'].apply(lambda x: f"${x:,.2f}")
                display_df['Score'] = display_df['Score'].apply(lambda x: f"{x:.2f}")
                
                st.dataframe(display_df, use_container_width=True)
                
                # Show detailed view for selected anomaly
                if len(anomalies) > 0:
                    st.subheader("Anomaly Details")
                    selected_idx = st.selectbox("Select an anomaly to view details:", 
                                              range(len(anomalies)),
                                              format_func=lambda x: f"{anomalies[x]['payee']} - {anomalies[x]['anomaly_type']} (Score: {anomalies[x]['score']:.2f})")
                    
                    if selected_idx is not None:
                        anomaly = anomalies[selected_idx]
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Date:** {anomaly['date']}")
                            st.write(f"**Merchant:** {anomaly['payee']}")
                            st.write(f"**Amount:** ${anomaly['amount']:,.2f}")
                            st.write(f"**Type:** {anomaly['anomaly_type']}")
                            
                        with col2:
                            st.write(f"**Score:** {anomaly['score']:.2f}")
                            st.write(f"**Category:** {anomaly['category']}")
                            st.write(f"**Account:** {anomaly['account_name']}")
                            st.write(f"**Explanation:** {anomaly['explanation']}")
            else:
                st.info("No anomalies detected. Click 'Analyze Anomalies' to run the analysis.")
                
        else:
            st.error(f"Failed to load anomalies: {resp.text}")
    except Exception as e:
        st.error(f"Error loading anomalies: {e}")
