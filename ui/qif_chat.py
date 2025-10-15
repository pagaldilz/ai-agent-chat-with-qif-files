import streamlit as st
import requests
import os
import pandas as pd
from datetime import datetime

QIF_API_URL = os.environ.get("QIF_API_URL", "http://qif-agent:8000")

st.set_page_config(page_title="QIF Agent", page_icon="", layout="centered")

# Sidebar navigation
page = st.sidebar.selectbox("Choose a page", ["Chat", "Recurring Analysis", "Merchant Analysis", "Anomaly Detection", "Cash Flow Forecast", "Investment Portfolio"])

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

elif page == "Cash Flow Forecast":
    st.title("Cash Flow Forecast")
    
    # Forecast controls
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        forecast_days = st.selectbox("Forecast Period", [30, 60, 90], index=0)
    
    with col2:
        if st.button("Generate Forecast", type="primary"):
            st.rerun()
    
    with col3:
        show_trends = st.checkbox("Show Trends", value=True)
    
    # Get forecast data
    try:
        # Get overall forecast
        resp = requests.get(f"{QIF_API_URL}/forecast/{forecast_days}", timeout=30)
        if resp.status_code == 200:
            forecast = resp.json()
            
            # Display key metrics
            st.subheader("Forecast Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Current Balance", f"${forecast['current_balance']:,.2f}")
            with col2:
                st.metric("Projected Balance", f"${forecast['projected_balance']:,.2f}")
            with col3:
                st.metric("Projected Income", f"${forecast['projected_income']:,.2f}")
            with col4:
                st.metric("Projected Expenses", f"${forecast['projected_expenses']:,.2f}")
            
            # Safe to spend amount
            st.subheader("Safe to Spend")
            safe_amount = forecast['safe_to_spend']
            if safe_amount > 0:
                st.success(f"**${safe_amount:,.2f}** available for discretionary spending")
            else:
                st.warning(f"**${abs(safe_amount):,.2f}** projected shortfall - consider reducing expenses")
            
            # Upcoming bills
            if forecast['upcoming_bills']:
                st.subheader("Upcoming Bills")
                bills_df = pd.DataFrame(forecast['upcoming_bills'])
                display_bills = bills_df[['merchant', 'amount', 'due_date', 'frequency', 'confidence']].copy()
                display_bills.columns = ['Merchant', 'Amount', 'Due Date', 'Frequency', 'Confidence']
                display_bills['Amount'] = display_bills['Amount'].apply(lambda x: f"${x:,.2f}")
                display_bills['Confidence'] = display_bills['Confidence'].apply(lambda x: f"{x:.1%}")
                
                st.dataframe(display_bills, use_container_width=True)
            
            # Daily forecast chart
            if forecast['daily_forecast']:
                st.subheader("Daily Balance Projection")
                daily_df = pd.DataFrame(forecast['daily_forecast'])
                daily_df['date'] = pd.to_datetime(daily_df['date'])
                
                # Create a simple line chart
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(daily_df['date'], daily_df['projected_balance'], linewidth=2)
                ax.set_title('Projected Balance Over Time')
                ax.set_xlabel('Date')
                ax.set_ylabel('Balance ($)')
                ax.grid(True, alpha=0.3)
                
                # Format y-axis as currency
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
                
                # Rotate x-axis labels
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)
            
            # Spending trends
            if show_trends:
                try:
                    trends_resp = requests.get(f"{QIF_API_URL}/forecast/trends", timeout=30)
                    if trends_resp.status_code == 200:
                        trends = trends_resp.json()
                        
                        if trends['trends']:
                            st.subheader("Historical Spending Trends")
                            trends_df = pd.DataFrame(trends['trends'])
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Avg Monthly Income", f"${trends['avg_monthly_income']:,.2f}")
                            with col2:
                                st.metric("Avg Monthly Expenses", f"${trends['avg_monthly_expenses']:,.2f}")
                            
                            # Display trends table
                            display_trends = trends_df[['month', 'income', 'expenses', 'transaction_count']].copy()
                            display_trends.columns = ['Month', 'Income', 'Expenses', 'Transactions']
                            display_trends['Income'] = display_trends['Income'].apply(lambda x: f"${x:,.2f}")
                            display_trends['Expenses'] = display_trends['Expenses'].apply(lambda x: f"${x:,.2f}")
                            
                            st.dataframe(display_trends, use_container_width=True)
                except Exception as e:
                    st.warning(f"Could not load spending trends: {e}")
        else:
            st.error(f"Failed to load forecast: {resp.text}")
    except Exception as e:
        st.error(f"Error loading forecast: {e}")

elif page == "Investment Portfolio":
    st.title("Investment Portfolio")
    
    # Portfolio controls
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("Parse Investments", type="primary"):
            with st.spinner("Parsing investment data..."):
                try:
                    resp = requests.post(f"{QIF_API_URL}/admin/parse-investments", timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('status') == 'success':
                            st.success(f"Parsed {data.get('transactions_count', 0)} investment transactions!")
                        else:
                            st.warning(f"Parsing result: {data.get('message', 'Unknown status')}")
                        st.rerun()
                    else:
                        st.error(f"Parsing failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Get portfolio data
    try:
        # Portfolio summary
        resp = requests.get(f"{QIF_API_URL}/investments/portfolio", timeout=30)
        if resp.status_code == 200:
            portfolio = resp.json()
            
            if portfolio.get('holdings'):
                # Display portfolio metrics
                st.subheader("Portfolio Summary")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Value", f"${portfolio['total_value']:,.2f}")
                with col2:
                    st.metric("Total Invested", f"${portfolio['total_invested']:,.2f}")
                with col3:
                    st.metric("Gain/Loss", f"${portfolio['total_gain_loss']:,.2f}")
                with col4:
                    st.metric("Return %", f"{portfolio['overall_return']:.2f}%")
                
                # Holdings table
                st.subheader("Current Holdings")
                holdings_df = pd.DataFrame(portfolio['holdings'])
                display_holdings = holdings_df[['security', 'total_quantity', 'avg_price', 'current_value', 'unrealized_gain_loss', 'return_percentage']].copy()
                display_holdings.columns = ['Security', 'Quantity', 'Avg Price', 'Current Value', 'Gain/Loss', 'Return %']
                display_holdings['Current Value'] = display_holdings['Current Value'].apply(lambda x: f"${x:,.2f}")
                display_holdings['Gain/Loss'] = display_holdings['Gain/Loss'].apply(lambda x: f"${x:,.2f}")
                display_holdings['Return %'] = display_holdings['Return %'].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(display_holdings, use_container_width=True)
                
                # Asset allocation
                try:
                    allocation_resp = requests.get(f"{QIF_API_URL}/investments/allocation", timeout=30)
                    if allocation_resp.status_code == 200:
                        allocation = allocation_resp.json()
                        
                        if allocation.get('allocation'):
                            st.subheader("Asset Allocation")
                            allocation_df = pd.DataFrame(allocation['allocation'])
                            
                            # Create pie chart
                            import matplotlib.pyplot as plt
                            fig, ax = plt.subplots(figsize=(10, 8))
                            
                            # Filter out small allocations for cleaner chart
                            min_allocation = 2.0  # 2% minimum
                            filtered_allocation = allocation_df[allocation_df['allocation_percentage'] >= min_allocation]
                            others = allocation_df[allocation_df['allocation_percentage'] < min_allocation]['allocation_percentage'].sum()
                            
                            if others > 0:
                                filtered_allocation = pd.concat([filtered_allocation, pd.DataFrame([{
                                    'security': 'Others',
                                    'allocation_percentage': others
                                }])])
                            
                            ax.pie(filtered_allocation['allocation_percentage'], 
                                  labels=filtered_allocation['security'],
                                  autopct='%1.1f%%',
                                  startangle=90)
                            ax.set_title('Asset Allocation')
                            st.pyplot(fig)
            else:
                st.info("No investment data available. Click 'Parse Investments' to load investment data from QIF files.")
        else:
            st.error(f"Failed to load portfolio: {resp.text}")
    except Exception as e:
        st.error(f"Error loading portfolio: {e}")
    
    # Performance analysis
    try:
        perf_resp = requests.get(f"{QIF_API_URL}/investments/performance", timeout=30)
        if perf_resp.status_code == 200:
            performance = perf_resp.json()
            
            if performance.get('monthly_performance'):
                st.subheader("Monthly Performance")
                perf_df = pd.DataFrame(performance['monthly_performance'])
                display_perf = perf_df[['month', 'total_amount', 'transaction_count']].copy()
                display_perf.columns = ['Month', 'Total Amount', 'Transactions']
                display_perf['Total Amount'] = display_perf['Total Amount'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(display_perf, use_container_width=True)
            
            if performance.get('action_breakdown'):
                st.subheader("Transaction Types")
                action_df = pd.DataFrame(performance['action_breakdown'])
                display_action = action_df[['action', 'total_amount', 'transaction_count']].copy()
                display_action.columns = ['Action', 'Total Amount', 'Count']
                display_action['Total Amount'] = display_action['Total Amount'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(display_action, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load performance data: {e}")
    
    # Recent transactions
    try:
        trans_resp = requests.get(f"{QIF_API_URL}/investments/transactions", timeout=30)
        if trans_resp.status_code == 200:
            transactions = trans_resp.json().get('transactions', [])
            
            if transactions:
                st.subheader("Recent Transactions")
                trans_df = pd.DataFrame(transactions)
                display_trans = trans_df[['date', 'security', 'action', 'quantity', 'price', 'amount']].copy()
                display_trans.columns = ['Date', 'Security', 'Action', 'Quantity', 'Price', 'Amount']
                display_trans['Price'] = display_trans['Price'].apply(lambda x: f"${x:,.2f}")
                display_trans['Amount'] = display_trans['Amount'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(display_trans, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load transaction history: {e}")
